
# update_readme.py
# -*- coding: utf-8 -*-
"""
Auto-rotate a banner image in README.md.

Key features:
- Stateless rotation: detects the current <img src=".../assets/..."> and picks the NEXT file
  using natural ordering (1.gif, 2.gif, 10.gif, ...). No .banner_state is required.
- Works with both relative and raw URLs; always writes a raw.githubusercontent.com URL
  with a cache-buster (?t=...) to avoid GitHub's image caching.
- Caption "Banner X/Y" is kept in sync. If the filename starts with a number (e.g. 6.gif),
  we prefer that number for X; otherwise we fall back to the 1-based index in the sorted list.
- Environment variable BANNER_MODE: "sequential" (default) or "random".

Expected repo layout:
  README.md
  assets/
    1.gif, 2.gif, 10.gif, ...

This script updates:
  - The banner block delimited by <!-- BANNER:START --> ... <!-- BANNER:END -->
  - The "Last updated:" line
  - The "🔥 MLOps Insight:" line
"""

from __future__ import annotations

import os
import re
import datetime
import random
from pathlib import Path
from typing import List, Tuple, Optional

# -------- Config --------
README_FILE = "README.md"
ASSETS = Path("assets")
MAX_MB = 10
EXTS = {".gif", ".webp", ".png", ".jpg", ".jpeg"}

# Banner selection mode: "sequential" | "random"
BANNER_MODE = os.getenv("BANNER_MODE", "sequential").strip().lower()


# -------- Utils --------
def _natkey(p: Path) -> List[object]:
    """
    Natural sort key so that 2.gif < 10.gif.
    Splits the filename into digit/non-digit chunks and converts digits to int.
    """
    s = p.name.lower()
    return [(int(t) if t.isdigit() else t) for t in re.findall(r"\d+|\D+", s)]


def _list_assets() -> List[Path]:
    """
    Return valid asset files (filtered by extension & size), naturally sorted.
    Hidden files (starting with ".") are skipped.
    """
    files: List[Path] = []
    if not ASSETS.exists():
        return files
    for p in ASSETS.iterdir():
        if not p.is_file():
            continue
        if p.suffix.lower() not in EXTS:
            continue
        if p.name.startswith("."):
            continue
        if p.stat().st_size > MAX_MB * 1024 * 1024:
            continue
        files.append(p)
    return sorted(files, key=_natkey)


def _to_raw_url(rel_path: str) -> str:
    """
    Build a raw GitHub URL for this repo/branch.
    Works locally (after push) and inside GitHub Actions.
    """
    repo = os.getenv("GITHUB_REPOSITORY", "evgeniimatveev/evgeniimatveev")
    branch = os.getenv("GITHUB_REF_NAME", "main")
    return f"https://raw.githubusercontent.com/{repo}/{branch}/{rel_path}"


def _extract_current_asset_from_md(md_text: str) -> Optional[str]:
    """
    Find the current <img src=".../assets/<file>"> in README (prefer the banner block).
    Returns a relative 'assets/<file>' path or None if not found.
    Handles raw URLs and strips query strings.
    """
    # Prefer within explicit banner block
    block_pat = r"(<!-- BANNER:START -->)(.*?)(<!-- BANNER:END -->)"
    m = re.search(block_pat, md_text, flags=re.S)
    scope = m.group(2) if m else md_text

    m2 = re.search(r'src="([^"]*?/assets/[^"?"]+)', scope, flags=re.I)
    if not m2:
        return None

    url = m2.group(1)  # could be 'assets/6.gif' or 'https://.../assets/6.gif'
    tail = re.search(r'/assets/([^/]+)$', url)
    if tail:
        return f'assets/{tail.group(1)}'
    if url.startswith("assets/"):
        return url
    return None


def _pick_next_asset(md_text: str, files: List[Path]) -> Tuple[str, int]:
    """
    Stateless choice of the next banner.
    - If BANNER_MODE == 'random': pick a random file, avoid current when possible.
    - Else (sequential): find the current in README and advance to the next (wrap).
    Returns (relative_path 'assets/..', index_1based_in_sorted_list).
    """
    if not files:
        raise RuntimeError("No valid assets found in 'assets/'.")

    paths = [f.as_posix() for f in files]  # e.g. 'assets/6.gif'
    current = _extract_current_asset_from_md(md_text)

    if BANNER_MODE == "random":
        candidates = paths.copy()
        if current in candidates and len(candidates) > 1:
            candidates.remove(current)
        choice = random.choice(candidates)
        return choice, paths.index(choice) + 1

    # sequential
    if current in paths:
        i = paths.index(current)
        nxt = paths[(i + 1) % len(paths)]
    else:
        nxt = paths[0]

    return nxt, paths.index(nxt) + 1


# -------- Banner rotation --------
def rotate_banner_in_md(md_text: str) -> str:
    """
    Stateless banner rotation:
    - Detect the current <img src=".../assets/..."> and pick the NEXT asset.
    - Write a raw.githubusercontent.com URL with cache-buster.
    - Keep/update the caption "Banner X/Y" (emoji preserved/added).
    - If the block is missing, prepend a fresh one at the top.
    """
    files = _list_assets()
    if not files:
        return md_text

    # Choose next asset
    next_rel, idx_fallback = _pick_next_asset(md_text, files)

    # Build cache-busted raw URL
    bust = int(datetime.datetime.utcnow().timestamp())
    img_src = f'{_to_raw_url(next_rel)}?t={bust}'

    # Derive X from filename if it starts with digits (e.g. "6.gif"); else use fallback index
    base = os.path.basename(next_rel)
    mnum = re.match(r'(\d+)', base)
    x_num = int(mnum.group(1)) if mnum else idx_fallback

    total = len(files)
    caption_text = f'Banner {x_num}/{total}'
    caption_html = f'<p align="center"><sub>🖼️ {caption_text}</sub></p>\n'

    # Fresh inner HTML we can fall back to
    new_inner = (
        f'\n<p align="center">\n'
        f'  <img src="{img_src}" alt="Banner" width="960">\n'
        f'</p>\n' + caption_html
    )

    # Try to patch an existing banner block first
    block_pat = r"(<!-- BANNER:START -->)(.*?)(<!-- BANNER:END -->)"
    mblock = re.search(block_pat, md_text, flags=re.S)

    if mblock:
        inner = mblock.group(2)

        # 1) Update <img src=".../assets/...">
        inner_patched = re.sub(
            r'src="[^"]*?/assets/[^"?"]+[^"]*"',
            f'src="{img_src}"',
            inner,
            flags=re.I
        )

        # 2) Update caption "Banner X/Y" (with or without emoji)
        inner_patched2 = re.sub(
            r'(?:🖼️\s*)?Banner\s+\d+/\d+',
            f'🖼️ {caption_text}',
            inner_patched,
            flags=re.I
        )

        # 3) If no caption existed at all, append it after the image block
        if 'Banner' not in inner_patched2:
            after_img = re.sub(r'(</p>\s*)$', r'\1' + caption_html, inner_patched2, count=1)
            if after_img == inner_patched2:
                inner_patched2 = inner_patched2 + caption_html

        # If something changed, return the patched block
        if inner_patched2 != inner:
            return md_text[:mblock.start(2)] + inner_patched2 + md_text[mblock.end(2):]

        # If we couldn’t safely patch, overwrite inner completely
        return md_text[:mblock.start(2)] + new_inner + md_text[mblock.end(2):]

    # No banner block yet — prepend a fresh one
    banner_block = f'<!-- BANNER:START -->{new_inner}<!-- BANNER:END -->\n'
    return banner_block + md_text


# Season + Day-of-week + Random vibe (keeps your 24h cron fresh without extra state

# Morning
MORNING_QUOTES = [
    "Time for some coffee and MLOps ☕",
    "Start your morning with automation! 🛠️",
    "Good morning! Let's optimize ML experiments! 🎯",
    "Kick off with clean pipelines and clear metrics 📊",
    "Bootstrap your day with reproducible runs 🔁",
    "Ship small, ship early, measure always 📈",
    "Warm up the DAGs and run smoke tests 🌅",
    "Start with data quality, end with insights ✅",
    "One small PR before breakfast 🍳",
    "Spin up environments, hydrate the features 💧",
]

# Afternoon
AFTERNOON_QUOTES = [
    "Keep pushing your MLOps pipeline forward! 🔧",
    "Perfect time for CI/CD magic ⚡",
    "Optimize, deploy, repeat! 🔄",
    "Measure → iterate → ship 🚀",
    "Refactor the DAGs, simplify the flows 🧩",
    "Guardrails on, feature flags ready 🧯",
    "Profile the hotspots, cache the wins 🧠",
    "Review metrics, cut toil, add value 📉→📈",
    "Monitor, alert, respond — calmly 🧭",
    "Make it boring: stable, predictable releases 🫡",
]

# Evening
EVENING_QUOTES = [
    "Evening is the best time to track ML experiments 🌙",
    "Relax and let automation handle your work 🤖",
    "Wrap up the day with some Bayesian tuning 🎯",
    "Document results, queue tomorrow's jobs 📝",
    "Small wins today, big gains tomorrow 📈",
    "Close issues, open insights ✅",
    "Archive artifacts, tag the best runs 🏷️",
    "Cool down the cluster, warm up ideas ❄️💡",
    "Write the changelog you wish you had 📓",
    "Reflect, refactor, and rest 🌌",
]

# Day-of-week booster
DAY_OF_WEEK_QUOTES = {
    "Monday": "Start your week strong! 🚀",
    "Tuesday": "Keep up the momentum! 🔥",
    "Wednesday": "Halfway there — keep automating! 🛠️",
    "Thursday": "Test, iterate, deploy! 🚀",
    "Friday": "Wrap it up like a pro! ⚡",
    "Saturday": "Weekend automation vibes! 🎉",
    "Sunday": "Prep for an MLOps-filled week! ⏳",
}

# Seasonal tones
SEASON_QUOTES = {
    "Spring": [
        "Fresh start — time to grow 🌸",
        "Refactor and bloom 🌼",
        "Spring into automation! 🪴",
        "Plant ideas, water pipelines 🌱",
        "Rebuild with lighter dependencies 🌿",
        "Nurture data quality from the root 🌷",
    ],
    "Summer": [
        "Keep shining and shipping ☀️",
        "Hot pipelines, cool results 🔥",
        "Sunny mindset, clean commits 😎",
        "Scale up smart, throttle costs 🏖️",
        "Ship value before the sunset 🌇",
        "Heat-proof your infra with tests 🔥🧪",
    ],
    "Autumn": [
        "Reflect, refine, retrain 🍂",
        "Collect insights like golden leaves 🍁",
        "Harvest your best MLOps ideas 🌾",
        "Prune legacy, keep essentials ✂️",
        "Tune models, store wisdom 📦",
        "Backtest decisions, bank learnings 🏦",
    ],
    "Winter": [
        "Deep focus and model tuning ❄️",
        "Hibernate and optimize 🧊",
        "Great time for infra upgrades 🛠️",
        "Keep the core warm and robust 🔧",
        "Reduce noise, raise signal 📡",
        "Plan roadmaps with calm clarity 🧭",
    ],
}

EXTRA_EMOJIS = [
    # Core MLOps / Engineering energy
    "🚀", "⚡", "🔥", "💡", "🎯", "🔄", "📈", "🛠️", "🧠", "🤖",
    "🧪", "✅", "📊", "🧭", "🧱", "🧰", "🧹", "🛰️",

    # Data / tracking / monitoring vibes
    "📡", "📂", "💾", "📁", "📋", "🧾", "📅", "🗂️", "📇", "📜",
    "🕹️", "🎮", "🎛️", "🎚️", "🎯", "📍", "📶", "⏱️", "⏳", "⌛",

    # Network / code / IP / log vibes
    "🖥️", "💻", "🧮", "📡", "🧩", "🧷", "🔌", "🪛", "🧰", "⚙️",
    "🌐", "🪩", "🧱", "🪄", "🪐", "🔭", "🧬", "📡", "💿", "🪙",

    # Creative / seasonal spark
    "🌅", "🌇", "🌙", "❄️", "🍁", "☀️", "🌸", "🌾", "🌈", "🌊",
]

HEADLINE_TEMPLATES = [
    "MLOPS DAILY",
    "BUILD • MEASURE • LEARN",
    "AUTOMATE EVERYTHING",
    "SHIP SMALL, SHIP OFTEN",
    "EXPERIMENT → INSIGHT → DEPLOY",
    "DATA • CODE • IMPACT",
    "TRACK • TUNE • TRUST",
    "REPRODUCIBILITY FIRST",
    "OBSERVE • ALERT • IMPROVE",
    "LOW TOIL, HIGH LEVERAGE",
    "METRICS OVER MYTHS",
    "PIPELINES, NOT FIRE-DRILLS",
]

def _get_season_by_month(m: int) -> str:
    if m in (3, 4, 5):
        return "Spring"
    if m in (6, 7, 8):
        return "Summer"
    if m in (9, 10, 11):
        return "Autumn"
    return "Winter"

def _style_text(text: str) -> str:
    """Randomly format text as UPPER (30%), Title Case (30%) or leave as is (40%)."""
    r = random.random()
    if r < 0.30:
        return text.upper()
    if r < 0.60:
        # Title case but keep emojis & ALL-CAPS tokens intact
        parts = []
        for token in text.split(" "):
            if any(ch for ch in token if ch.isalpha()) and not token.isupper() and not token.startswith(("🧪","🚀","⚡","🔥","💡","🎯","🔄","📈","🛠️","🧠","🤖","❄️","☀️","🍁","🌸","😎","🌙","📝","✅")):
                parts.append(token[:1].upper() + token[1:].lower())
            else:
                parts.append(token)
        return " ".join(parts)
    return text

def get_dynamic_quote() -> str:
    """
    Seasonal + day-of-week + time-of-day + headline.
    Keeps the same return contract: a single formatted string.
    """
    now = datetime.datetime.utcnow()
    day = now.strftime("%A")
    hour = now.hour
    season = _get_season_by_month(now.month)

    # Pick time-of-day vibe
    if 6 <= hour < 12:
        vibe = random.choice(MORNING_QUOTES)
    elif 12 <= hour < 18:
        vibe = random.choice(AFTERNOON_QUOTES)
    else:
        vibe = random.choice(EVENING_QUOTES)

    season_line = random.choice(SEASON_QUOTES[season])
    day_line = DAY_OF_WEEK_QUOTES.get(day, "")
    tail_emoji = random.choice(EXTRA_EMOJIS)

    # Optional: include short run marker if we’re inside Actions
    run_no = os.getenv("GITHUB_RUN_NUMBER")
    run_tag = f" • RUN #{run_no}" if run_no else ""

    # Headline (occasionally in all caps)
    headline = random.choice(HEADLINE_TEMPLATES)
    headline = _style_text(headline)

    # Compose: HEADLINE · Season | Day | Vibe + emoji (+ optional run tag)
    core = f"{season_line} | {day_line} {vibe} {tail_emoji}"
    core = _style_text(core)  # maybe UPPER / Title Case for variety

    return f"{headline}{run_tag} — {core}"
# -------- Main driver --------
def generate_new_readme() -> None:
    md_path = Path(README_FILE)
    md = md_path.read_text(encoding="utf-8")

    # 1) Rotate the banner (stateless)
    md = rotate_banner_in_md(md)

    # 2) Update timestamp and insight line
    now = datetime.datetime.utcnow()
    dynamic_quote = get_dynamic_quote()

    lines = md.splitlines(keepends=True)
    updated: List[str] = []
    saw_updated = False
    saw_insight = False

    for line in lines:
        if line.startswith("Last updated:"):
            updated.append(f"Last updated: {now} UTC\n")
            saw_updated = True
        elif line.startswith("🔥 MLOps Insight:"):
            updated.append(f"🔥 MLOps Insight: 💡 {dynamic_quote}\n")
            saw_insight = True
        else:
            updated.append(line)

    if not saw_updated:
        updated.append(f"\nLast updated: {now} UTC\n")
    if not saw_insight:
        updated.append(f"\n🔥 MLOps Insight: 💡 {dynamic_quote}\n")

  # --- Heartbeat / build card (compact status in CI logs) ---
    # Pull metadata from the Actions environment (fallbacks keep it safe locally).
    run_no    = os.getenv("GITHUB_RUN_NUMBER", "?")
    short_sha = os.getenv("GITHUB_SHA", "")[:7]
    schedule  = os.getenv("SCHEDULE_BADGE", "24h_5m")

    # For a daily schedule, the next rotation is now + 24h (UTC).
    next_eta = (now + datetime.timedelta(days=1)).strftime("%Y-%m-%d %H:%M UTC")

    # Pretty separator to make the block easy to spot in Actions logs.
    bar = "─" * 72
    print("\n" + bar)
    print(f"✅ README updated: {now:%Y-%m-%d %H:%M:%S} UTC")
    print(f"🖼️ Banner mode: {BANNER_MODE}   🔢 Run: #{run_no}   🔗 SHA: {short_sha}")
    print(f"💬 Insight: {dynamic_quote}")
    print(f"⏱️ Schedule: {schedule}   ▶️ Next ETA: {next_eta}")
    print(bar + "\n")


if __name__ == "__main__":
    generate_new_readme()
