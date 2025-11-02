# update_readme.py
# -*- coding: utf-8 -*-
"""
Auto-rotate a banner in README.md + append runtime metadata.

Adds/updates:
- Banner block between <!-- BANNER:START --> ... <!-- BANNER:END -->
- "Last updated: <UTC>" line
- "🔥 MLOps Insight: 💡 ..." line
- RUNMETA block between <!-- RUNMETA:START --> ... <!-- RUNMETA:END -->

Environment knobs:
- BANNER_MODE = "sequential" | "random"     (default: sequential)
- SCHEDULE_BADGE (e.g., "24h_5m")           (default: 24h_5m)

Reads standard GitHub Actions env when running in CI:
GITHUB_REPOSITORY, GITHUB_REF_NAME, GITHUB_RUN_NUMBER, GITHUB_RUN_ID,
GITHUB_SHA, GITHUB_WORKFLOW, GITHUB_EVENT_NAME, GITHUB_ACTOR, GITHUB_JOB.

Optionally pass custom env from workflow (they are shown if present):
RUN_OS, PY_VERSION
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
    """Natural sort key so that 2.gif < 10.gif."""
    s = p.name.lower()
    return [(int(t) if t.isdigit() else t) for t in re.findall(r"\d+|\D+", s)]


def _list_assets() -> List[Path]:
    """Return valid assets (by ext & size), naturally sorted."""
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
    """Build a raw GitHub URL for this repo/branch."""
    repo = os.getenv("GITHUB_REPOSITORY", "evgeniimatveev/evgeniimatveev")
    branch = os.getenv("GITHUB_REF_NAME", "main")
    return f"https://raw.githubusercontent.com/{repo}/{branch}/{rel_path}"


def _extract_current_asset_from_md(md_text: str) -> Optional[str]:
    """
    Find current <img src=".../assets/<file>"> (prefer banner block).
    Return 'assets/<file>' or None.
    """
    block_pat = r"(<!-- BANNER:START -->)(.*?)(<!-- BANNER:END -->)"
    m = re.search(block_pat, md_text, flags=re.S)
    scope = m.group(2) if m else md_text

    m2 = re.search(r'src="([^"]*?/assets/[^"?"]+)', scope, flags=re.I)
    if not m2:
        return None

    url = m2.group(1)
    tail = re.search(r'/assets/([^/]+)$', url)
    if tail:
        return f'assets/{tail.group(1)}'
    if url.startswith("assets/"):
        return url
    return None


def _pick_next_asset(md_text: str, files: List[Path]) -> Tuple[str, int]:
    """
    Stateless next banner:
    - random mode avoids the current when possible
    - sequential moves to next (wrap-around)
    Returns (rel_path, index_1based_in_sorted_list).
    """
    if not files:
        raise RuntimeError("No valid assets found in 'assets/'.")

    paths = [f.as_posix() for f in files]
    current = _extract_current_asset_from_md(md_text)

    if BANNER_MODE == "random":
        candidates = paths.copy()
        if current in candidates and len(candidates) > 1:
            candidates.remove(current)
        choice = random.choice(candidates)
        return choice, paths.index(choice) + 1

    if current in paths:
        i = paths.index(current)
        nxt = paths[(i + 1) % len(paths)]
    else:
        nxt = paths[0]
    return nxt, paths.index(nxt) + 1


# -------- Banner rotation --------
def rotate_banner_in_md(md_text: str) -> str:
    """
    Statelessly rotate the banner and keep a centered caption:
    - raw.githubusercontent.com URL with cache-buster (?t=<unix>)
    - caption "🖼️ Banner X/Y" (X prefers numeric prefix in filename)
    """
    files = _list_assets()
    if not files:
        return md_text

    next_rel, idx_fallback = _pick_next_asset(md_text, files)

    bust = int(datetime.datetime.utcnow().timestamp())
    img_src = f'{_to_raw_url(next_rel)}?t={bust}'

    base = os.path.basename(next_rel)
    mnum = re.match(r'(\d+)', base)
    x_num = int(mnum.group(1)) if mnum else idx_fallback

    total = len(files)
    caption_text = f'Banner {x_num}/{total}'
    caption_html = f'<p align="center"><sub>🖼️ {caption_text}</sub></p>\n'

    new_inner = (
        f'\n<p align="center">\n'
        f'  <img src="{img_src}" alt="Banner" width="960">\n'
        f'</p>\n' + caption_html
    )

    block_pat = r"(<!-- BANNER:START -->)(.*?)(<!-- BANNER:END -->)"
    mblock = re.search(block_pat, md_text, flags=re.S)

    if mblock:
        inner = mblock.group(2)

        inner_patched = re.sub(
            r'src="[^"]*?/assets/[^"?"]+[^"]*"',
            f'src="{img_src}"',
            inner,
            flags=re.I
        )

        inner_patched2 = re.sub(
            r'(?:🖼️\s*)?Banner\s+\d+/\d+',
            f'🖼️ {caption_text}',
            inner_patched,
            flags=re.I
        )

        if 'Banner' not in inner_patched2:
            after_img = re.sub(r'(</p>\s*)$', r'\1' + caption_html, inner_patched2, count=1)
            if after_img == inner_patched2:
                inner_patched2 = inner_patched2 + caption_html

        if inner_patched2 != inner:
            return md_text[:mblock.start(2)] + inner_patched2 + md_text[mblock.end(2):]
        return md_text[:mblock.start(2)] + new_inner + md_text[mblock.end(2):]

    # No banner block yet — prepend a fresh one
    banner_block = f'<!-- BANNER:START -->{new_inner}<!-- BANNER:END -->\n'
    return banner_block + md_text


# -------- Insight generation --------
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
DAY_OF_WEEK_QUOTES = {
    "Monday": "Start your week strong! 🚀",
    "Tuesday": "Keep up the momentum! 🔥",
    "Wednesday": "Halfway there — keep automating! 🛠️",
    "Thursday": "Test, iterate, deploy! 🚀",
    "Friday": "Wrap it up like a pro! ⚡",
    "Saturday": "Weekend automation vibes! 🎉",
    "Sunday": "Prep for an MLOps-filled week! ⏳",
}
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
    "🚀","⚡","🔥","💡","🎯","🔄","📈","🛠️","🧠","🤖","🧪","✅","📊","🧭","🛰️",
    "📡","📂","💾","📅","⏱️","⏳","⌛","🌅","🌇","🌙","❄️","🍁","☀️","🌸","🌾","🌈","🌊",
]
HEADLINE_TEMPLATES = [
    "MLOPS DAILY","BUILD • MEASURE • LEARN","AUTOMATE EVERYTHING","SHIP SMALL, SHIP OFTEN",
    "EXPERIMENT → INSIGHT → DEPLOY","DATA • CODE • IMPACT","TRACK • TUNE • TRUST",
    "REPRODUCIBILITY FIRST","OBSERVE • ALERT • IMPROVE","LOW TOIL, HIGH LEVERAGE",
    "METRICS OVER MYTHS","PIPELINES, NOT FIRE-DRILLS",
]

def _get_season_by_month(m: int) -> str:
    if m in (3, 4, 5): return "Spring"
    if m in (6, 7, 8): return "Summer"
    if m in (9, 10, 11): return "Autumn"
    return "Winter"

def _style_text(text: str) -> str:
    """Randomly upper/title/keep (30/30/40)."""
    r = random.random()
    if r < 0.30:
        return text.upper()
    if r < 0.60:
        parts = []
        for token in text.split(" "):
            if any(ch.isalpha() for ch in token) and not token.isupper() and not token.startswith(
                ("🧪","🚀","⚡","🔥","💡","🎯","🔄","📈","🛠️","🧠","🤖","❄️","☀️","🍁","🌸","😎","🌙","📝","✅")
            ):
                parts.append(token[:1].upper() + token[1:].lower())
            else:
                parts.append(token)
        return " ".join(parts)
    return text

def get_dynamic_quote() -> str:
    """Seasonal + day-of-week + time-of-day + headline (+ RUN # in CI)."""
    now = datetime.datetime.utcnow()
    day = now.strftime("%A")
    hour = now.hour
    season = _get_season_by_month(now.month)

    vibe = (
        random.choice(MORNING_QUOTES) if 6 <= hour < 12 else
        random.choice(AFTERNOON_QUOTES) if 12 <= hour < 18 else
        random.choice(EVENING_QUOTES)
    )
    season_line = random.choice(SEASON_QUOTES[season])
    day_line = DAY_OF_WEEK_QUOTES.get(day, "")
    tail_emoji = random.choice(EXTRA_EMOJIS)

    run_no = os.getenv("GITHUB_RUN_NUMBER")
    run_tag = f" • RUN #{run_no}" if run_no else ""

    headline = _style_text(random.choice(HEADLINE_TEMPLATES))
    core = _style_text(f"{season_line} | {day_line} {vibe} {tail_emoji}")
    return f"{headline}{run_tag} — {core}"


# -------- RUNMETA block --------
def _extract_banner_numbers(md_text: str) -> Optional[Tuple[int, int]]:
    """Try to read '🖼️ Banner X/Y' from the README (after rotation)."""
    m = re.search(r'Banner\s+(\d+)\s*/\s*(\d+)', md_text, flags=re.I)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None

def _render_runmeta_block(now_utc: datetime.datetime, next_eta_utc_str: str) -> str:
    """Render the collapsible RUNMETA block with links & optional extras."""
    repo      = os.getenv("GITHUB_REPOSITORY", "evgeniimatveev/evgeniimatveev")
    branch    = os.getenv("GITHUB_REF_NAME", "main")
    run_no    = os.getenv("GITHUB_RUN_NUMBER", "—")
    run_id    = os.getenv("GITHUB_RUN_ID")
    sha       = os.getenv("GITHUB_SHA", "")
    short_sha = sha[:7] if sha else "—"
    workflow  = os.getenv("GITHUB_WORKFLOW", "—")
    event     = os.getenv("GITHUB_EVENT_NAME", "—")
    actor     = os.getenv("GITHUB_ACTOR")
    job       = os.getenv("GITHUB_JOB")

    run_url   = f"https://github.com/{repo}/actions/runs/{run_id}" if run_id else None
    commit_url= f"https://github.com/{repo}/commit/{sha}" if sha else None

    schedule  = os.getenv("SCHEDULE_BADGE", "24h_5m")
    run_os    = os.getenv("RUN_OS")
    py_ver    = os.getenv("PY_VERSION")

    # Optional embedded banner info (read back from README after rotation)
    banner_info = ""  # added by caller if available

    lines = []
    lines.append("\n---")
    lines.append("<!-- RUNMETA:START -->")
    lines.append("<details>")
    lines.append("<summary>📄 Run Meta (click to expand)</summary>\n")
    lines.append(f"- 🕒 Updated (UTC): {now_utc:%Y-%m-%d %H:%M}")
    lines.append(f"- 🔢 Run: #{run_no}" + (f"  —  ▶️ [open run]({run_url})" if run_url else ""))
    lines.append(f"- 🔗 Commit: {short_sha}" + (f"  —  📘 [open commit]({commit_url})" if commit_url else ""))
    lines.append(f"- ⚙️ Workflow: {workflow}" + (f"  ·  Job: {job}" if job else ""))
    lines.append(f"- 🧨 Event: {event}" + (f"  ·  👤 Actor: {actor}" if actor else ""))
    lines.append(f"- ⏳ Schedule: {schedule}")
    if run_os or py_ver:
        extras = "  ·  ".join([x for x in [f"OS: {run_os}" if run_os else "", f"Python: {py_ver}" if py_ver else ""] if x])
        lines.append(f"- 🧰 {extras}")
    if banner_info:
        lines.append(banner_info)
    lines.append(f"- ▶️ Next ETA (UTC): {next_eta_utc_str}\n")
    lines.append("</details>")
    lines.append("<!-- RUNMETA:END -->")
    lines.append("---\n")
    return "\n".join(lines)

def _upsert_runmeta(md_text: str, now_utc: datetime.datetime) -> str:
    """Insert or replace the RUNMETA block; place it after the banner if possible."""
    # Compute Next ETA (simple +24h model; keep UTC)
    next_eta = (now_utc + datetime.timedelta(days=1)).strftime("%Y-%m-%d %H:%M")

    block = _render_runmeta_block(now_utc, next_eta)

    # If we can read banner X/Y, inject one line into block
    banner_nums = _extract_banner_numbers(md_text)
    if banner_nums:
        x, y = banner_nums
        inject = f"- 🖼️ Banner: {x}/{y}"
        block = block.replace("<!-- RUNMETA:START -->",
                              "<!-- RUNMETA:START -->", 1)\
                     .replace("- ▶️ Next ETA", f"{inject}\n- ▶️ Next ETA")

    pat = re.compile(r"<!-- RUNMETA:START -->(.*?)<!-- RUNMETA:END -->", re.S)
    if pat.search(md_text):
        # Replace existing block
        new_md = pat.sub(block.strip(), md_text)
    else:
        # Insert after banner block if present; otherwise append at end
        banner_pat = re.compile(r"(<!-- BANNER:END -->)", re.S)
        if banner_pat.search(md_text):
            new_md = banner_pat.sub(r"\1\n" + block, md_text, count=1)
        else:
            new_md = md_text.rstrip() + "\n" + block
    return new_md


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

    md = "".join(updated)

    # 3) Upsert RUNMETA block (after banner if present)
    md = _upsert_runmeta(md, now)

    # 4) Write back to disk
    md_path.write_text(md, encoding="utf-8")

    # 5) Heartbeat logs for Actions
    run_no    = os.getenv("GITHUB_RUN_NUMBER", "?")
    short_sha = os.getenv("GITHUB_SHA", "")[:7]
    schedule  = os.getenv("SCHEDULE_BADGE", "24h_5m")
    next_eta  = (now + datetime.timedelta(days=1)).strftime("%Y-%m-%d %H:%M UTC")

    bar = "─" * 72
    print("\n" + bar)
    print(f"✅ README updated: {now:%Y-%m-%d %H:%M:%S} UTC")
    print(f"🖼️ Banner mode: {BANNER_MODE}   🔢 Run: #{run_no}   🔗 SHA: {short_sha}")
    print(f"💬 Insight: {dynamic_quote}")
    print(f"⏱️ Schedule: {schedule}   ▶️ Next ETA: {next_eta}")
    print(bar + "\n")


if __name__ == "__main__":
    generate_new_readme()
