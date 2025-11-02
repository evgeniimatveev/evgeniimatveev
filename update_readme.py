# update_readme.py
# -*- coding: utf-8 -*-
"""
Auto-rotate a banner image in README.md and inject a daily dynamic message.

Key improvements in this version:
- Daily-stable message generator (same text for the whole day), composed from:
  season (winter/spring/summer/autumn) + weekday + a day-part that cycles by day-of-year.
- Optional "calendar index" banner selection to avoid drift if some runs are skipped.
  Enable via env: BANNER_CALENDAR_MODE=true
- Clean English comments throughout.

Expected repo layout:
  README.md
  assets/
    1.gif, 2.gif, 10.gif, ... (or any names; natural sort applied)

This script updates:
  - The banner block delimited by <!-- BANNER:START --> ... <!-- BANNER:END -->
  - The "Last updated:" line
  - The "🔥 MLOps Insight:" line
"""

from __future__ import annotations

import os
import re
import datetime as dt
from zoneinfo import ZoneInfo
import random
from pathlib import Path
from typing import List, Tuple, Optional

# ----------------------------- Config ---------------------------------
README_FILE = "README.md"
ASSETS = Path("assets")
MAX_MB = 10
EXTS = {".gif", ".webp", ".png", ".jpg", ".jpeg"}

# Banner selection modes:
# - "sequential": next file in natural order (default)
# - "random":     random file (will try to avoid repeating the current one)
BANNER_MODE = os.getenv("BANNER_MODE", "sequential").strip().lower()

# Optional calendar indexing to avoid drift:
# If true, we choose the banner by day-of-year instead of "next file".
# This keeps day N always mapped to the same index even if a run is skipped.
BANNER_CALENDAR_MODE = os.getenv("BANNER_CALENDAR_MODE", "false").lower() in {"1", "true", "yes"}

# Timezone used to anchor "today" for message composition (and optional gating if you want it here).
LOCAL_TZ = ZoneInfo("America/Los_Angeles")

# If you prefer meteorological seasons (by months) keep True;
# if you want exactly 4 acts (4 * ~91 days) switch to False.
USE_METEOROLOGICAL_SEASONS = True

# ----------------------------- Utilities ------------------------------
def _natkey(p: Path) -> List[object]:
    """Natural sort key so that '2.gif' < '10.gif'."""
    s = p.name.lower()
    return [(int(t) if t.isdigit() else t) for t in re.findall(r"\d+|\D+", s)]

def _list_assets() -> List[Path]:
    """Return valid asset files (filtered by extension & size), naturally sorted."""
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
    """Build a raw GitHub URL for this repo/branch (works locally and in Actions)."""
    repo = os.getenv("GITHUB_REPOSITORY", "evgeniimatveev/evgeniimatveev")
    branch = os.getenv("GITHUB_REF_NAME", "main")
    return f"https://raw.githubusercontent.com/{repo}/{branch}/{rel_path}"

def _extract_current_asset_from_md(md_text: str) -> Optional[str]:
    """
    Find the current <img src=".../assets/<file>"> in README (prefer the banner block).
    Returns a relative 'assets/<file>' path or None if not found.
    Handles raw URLs and strips query strings.
    """
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
    Choose the next banner asset and return (relative_path, 1-based index_in_sorted_list).
    Behavior depends on:
      - BANNER_CALENDAR_MODE (if true, day-of-year selects the index)
      - BANNER_MODE ('sequential' or 'random')
    """
    if not files:
        raise RuntimeError("No valid assets found in 'assets/'.")

    paths = [f.as_posix() for f in files]  # e.g., 'assets/6.gif'

    # Calendar mode: pick based on day-of-year (stable mapping)
    if BANNER_CALENDAR_MODE:
        doy = dt.datetime.now(dt.timezone.utc).timetuple().tm_yday
        idx0 = (doy - 1) % len(paths)
        choice = paths[idx0]
        return choice, idx0 + 1

    current = _extract_current_asset_from_md(md_text)

    if BANNER_MODE == "random":
        candidates = paths.copy()
        if current in candidates and len(candidates) > 1:
            candidates.remove(current)
        choice = random.choice(candidates)
        return choice, paths.index(choice) + 1

    # Default: sequential (advance one step; wrap at the end)
    if current in paths:
        i = paths.index(current)
        nxt = paths[(i + 1) % len(paths)]
    else:
        nxt = paths[0]
    return nxt, paths.index(nxt) + 1

# ------------------------- Banner rotation ----------------------------
def rotate_banner_in_md(md_text: str) -> str:
    """
    Stateless banner rotation:
    - Detect the current <img src=".../assets/..."> and pick the NEXT asset (or calendar index).
    - Write a raw.githubusercontent.com URL with a cache-buster (?t=...).
    - Keep/update the caption "Banner X/Y" (emoji preserved/added).
    - If the block is missing, prepend a fresh one at the top.
    """
    files = _list_assets()
    if not files:
        return md_text

    # Choose next asset
    next_rel, idx_fallback = _pick_next_asset(md_text, files)

    # Build cache-busted raw URL
    bust = int(dt.datetime.utcnow().timestamp())
    img_src = f'{_to_raw_url(next_rel)}?t={bust}'

    # Derive X from filename if it starts with digits; else use fallback index
    base = os.path.basename(next_rel)
    mnum = re.match(r'(\d+)', base)
    x_num = int(mnum.group(1)) if mnum else idx_fallback

    total = len(files)
    caption_text = f'Banner {x_num}/{total}'
    caption_html = f'<p align="center"><sub>🖼️ {caption_text}</sub></p>\n'

    # Fresh inner HTML
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

        # 2) Update caption "Banner X/Y"
        inner_patched2 = re.sub(
            r'(?:🖼️\s*)?Banner\s+\d+/\d+',
            f'🖼️ {caption_text}',
            inner_patched,
            flags=re.I
        )

        # 3) If no caption existed, append it
        if 'Banner' not in inner_patched2:
            after_img = re.sub(r'(</p>\s*)$', r'\1' + caption_html, inner_patched2, count=1)
            if after_img == inner_patched2:
                inner_patched2 = inner_patched2 + caption_html

        # Return patched block (or overwrite if nothing changed)
        if inner_patched2 != inner:
            return md_text[:mblock.start(2)] + inner_patched2 + md_text[mblock.end(2):]
        return md_text[:mblock.start(2)] + new_inner + md_text[mblock.end(2):]

    # No banner block yet — prepend a fresh one
    banner_block = f'<!-- BANNER:START -->{new_inner}<!-- BANNER:END -->\n'
    return banner_block + md_text

# ------------------------- Daily dynamic message ----------------------
WEEKDAY_LINES = {
    "Monday":    "Start your week strong! 🚀",
    "Tuesday":   "Keep up the momentum! 🔥",
    "Wednesday": "Halfway there—keep automating! 🛠️",
    "Thursday":  "Test, iterate, deploy! 🚀",
    "Friday":    "Wrap it up like a pro! 🎯",
    "Saturday":  "Weekend automation vibes! 🎉",
    "Sunday":    "Recharge and prep the pipelines! ⏳",
}

DAYPARTS = ["morning", "noon", "evening", "night"]
DAYPART_QUOTES = {
    "morning": [
        "Time for some coffee and MLOps ☕",
        "Start your morning with automation! 🛠️",
        "Good morning! Let's optimize ML experiments! 🎯",
    ],
    "noon": [
        "Keep pushing your MLOps pipeline forward! 🔧",
        "Optimize, deploy, repeat! 🔄",
        "Perfect time for CI/CD magic! ⚡",
    ],
    "evening": [
        "Evening is perfect for experiment tracking 🌙",
        "Relax and let automation do the work 🤖",
        "Wrap up the day with smart tuning 🎯",
    ],
    "night": [
        "Night shift: logs, metrics, and calm lights 🌌",
        "Quiet hours, clean deploys 🌙",
        "Ship safely while the city sleeps ✨",
    ],
}

SEASON_TAGLINES = {
    "winter": [
        "Cozy commits under snowy lights ❄️",
        "Warm coffee, cold rooftops ☕❄️",
        "Quiet nights, bright dashboards ✨",
    ],
    "spring": [
        "Fresh runs, blooming graphs 🌸",
        "New metrics sprouting everywhere 🌱",
        "Clean configs, clear skies ☀️",
    ],
    "summer": [
        "Neon nights and quick deploys 🌆",
        "Hotfixes in warm sunsets 🌇",
        "Bright builds, lighter vibes 🌞",
    ],
    "autumn": [
        "Amber lights, steady pipelines 🍁",
        "Calm refactors and rainy windows 🌧️",
        "Soft glow, sharp insights 🔶",
    ],
}

EXTRA_EMOJIS = ["🚀", "⚡", "🔥", "💡", "🎯", "🔄", "📈", "🛠️"]

def _season_for(day: dt.date) -> str:
    """Determine season by month (meteorological) or by 4 equal acts."""
    if USE_METEOROLOGICAL_SEASONS:
        m = day.month
        if m in (12, 1, 2):  return "winter"
        if m in (3, 4, 5):   return "spring"
        if m in (6, 7, 8):   return "summer"
        return "autumn"
    else:
        doy = day.timetuple().tm_yday
        if doy <= 91:    return "winter"
        if doy <= 182:   return "spring"
        if doy <= 273:   return "summer"
        return "autumn"

def get_daily_quote(today: dt.date | None = None) -> str:
    """
    Return ONE stable message for the day (anchored to LOCAL_TZ).
    Composition:
      base = random( daypart bucket )    # daypart cycles by day-of-year
      weekday_line = fixed by weekday
      season_line  = random( season bucket )
      + one extra emoji
    """
    now_local = dt.datetime.now(LOCAL_TZ)
    if today is None:
        today = now_local.date()

    season = _season_for(today)
    weekday = today.strftime("%A")
    doy = today.timetuple().tm_yday

    # Cycle daypart by day-of-year instead of using current hour
    daypart = DAYPARTS[(doy - 1) % 4]

    # Deterministic seed per day → stable choice for the whole day
    seed = int(today.strftime("%Y%m%d"))
    rnd = random.Random(seed)

    base = rnd.choice(DAYPART_QUOTES[daypart])
    season_line = rnd.choice(SEASON_TAGLINES[season])
    tail = rnd.choice(EXTRA_EMOJIS)

    msg = f"{base} | {weekday}: {WEEKDAY_LINES[weekday]} • {season_line} {tail}"
    return msg

# ---------------------------- Main driver -----------------------------
def generate_new_readme() -> None:
    md_path = Path(README_FILE)
    md = md_path.read_text(encoding="utf-8")

    # 1) Rotate the banner
    md = rotate_banner_in_md(md)

    # 2) Update timestamp and the daily message
    now_utc = dt.datetime.utcnow()
    daily_msg = get_daily_quote()

    lines = md.splitlines(keepends=True)
    updated: List[str] = []
    saw_updated = False
    saw_insight = False

    for line in lines:
        if line.startswith("Last updated:"):
            updated.append(f"Last updated: {now_utc} UTC\n")
            saw_updated = True
        elif line.startswith("🔥 MLOps Insight:"):
            updated.append(f"🔥 MLOps Insight: 💡 {daily_msg}\n")
            saw_insight = True
        else:
            updated.append(line)

    if not saw_updated:
        updated.append(f"\nLast updated: {now_utc} UTC\n")
    if not saw_insight:
        updated.append(f"\n🔥 MLOps Insight: 💡 {daily_msg}\n")

    md_path.write_text("".join(updated), encoding="utf-8")
    print(f"✅ README updated at {now_utc} UTC")
    print(f"🖼️ Banner mode: {BANNER_MODE} | Calendar mode: {BANNER_CALENDAR_MODE}")
    print(f"📝 Daily message: {daily_msg}")

if __name__ == "__main__":
    generate_new_readme()
