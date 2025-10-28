# update_readme.py
# -*- coding: utf-8 -*-

import os
import re
import datetime
import random
from pathlib import Path

README_FILE = "README.md"

# ============ ROTATING BANNER SETTINGS ============
ASSETS = Path("assets")
MAX_MB = 10
EXTS = {".gif", ".webp", ".png", ".jpg", ".jpeg"}

# Banner selection mode: "sequential" | "random"
# Can be overridden from GitHub Actions via env BANNER_MODE
BANNER_MODE = os.getenv("BANNER_MODE", "sequential").strip().lower()


# ---------- utils ----------
def _natkey(p: Path):
    """
    Natural sort key: ensures 2.gif < 10.gif.
    Splits string into digit/non-digit chunks and converts digits to int.
    """
    s = p.name.lower()
    return [(int(t) if t.isdigit() else t) for t in re.findall(r"\d+|\D+", s)]


def _list_assets():
    """
    Return valid asset files (size + extension), naturally sorted.
    Hidden files (starting with ".") are skipped.
    """
    files = []
    if not ASSETS.exists():
        return files
    for p in ASSETS.iterdir():
        if p.is_file() and p.suffix.lower() in EXTS and not p.name.startswith("."):
            if p.stat().st_size <= MAX_MB * 1024 * 1024:
                files.append(p)
    return sorted(files, key=_natkey)


def _to_raw_url(rel_path: str) -> str:
    """
    Build a raw GitHub URL for this repo's current branch.
    Works inside Actions; locally it will still produce a valid URL once pushed.
    """
    repo = os.getenv("GITHUB_REPOSITORY", "evgeniimatveev/evgeniimatveev")
    # In Actions this is set; locally fallback to 'main'
    branch = os.getenv("GITHUB_REF_NAME", "main")
    return f"https://raw.githubusercontent.com/{repo}/{branch}/{rel_path}"


def _extract_current_asset_from_md(md_text: str) -> str | None:
    """
    Try to find current <img src=".../assets/<file>"> inside the BANNER block (or anywhere).
    Returns a relative 'assets/<file>' path or None if not found.
    Handles raw URLs and query strings (?t=...).
    """
    # 1) Prefer within explicit banner block
    block_pat = r"(<!-- BANNER:START -->)(.*?)(<!-- BANNER:END -->)"
    m = re.search(block_pat, md_text, flags=re.S)
    scope = m.group(2) if m else md_text

    # 2) Extract src that contains '/assets/' (raw URL or relative)
    m2 = re.search(r'src="([^"]*?/assets/[^"?"]+)', scope, flags=re.I)
    if not m2:
        return None

    url = m2.group(1)  # could be 'assets/1.gif' or 'https://.../assets/1.gif'
    # Normalize to 'assets/<file>'
    tail_match = re.search(r'/assets/([^/]+)$', url)
    if tail_match:
        return f'assets/{tail_match.group(1)}'

    # or relative already
    if url.startswith("assets/"):
        return url

    return None


def _pick_next_asset(md_text: str, files: list[Path]) -> tuple[str, int]:
    """
    Stateless choice of next banner:
    - If BANNER_MODE=='random': pick random, avoid current when possible.
    - Else: sequential — find current in README and advance to next (wrap).
    Returns (asset_rel_path, index_1based).
    """
    if not files:
        raise RuntimeError("No valid assets found in 'assets/'.")

    paths = [f.as_posix() for f in files]  # e.g. 'assets/1.gif'
    current = _extract_current_asset_from_md(md_text)

    if BANNER_MODE == "random":
        candidates = paths.copy()
        if current in candidates and len(candidates) > 1:
            candidates.remove(current)
        choice = random.choice(candidates)
        idx = paths.index(choice) + 1
        return choice, idx

    # sequential
    if current in paths:
        i = paths.index(current)
        nxt = paths[(i + 1) % len(paths)]
    else:
        nxt = paths[0]
    idx = paths.index(nxt) + 1
    return nxt, idx


# ---------------------------

def rotate_banner_in_md(md_text: str) -> str:
    """
    Stateless banner rotation:
    - Detect the current <img src=".../assets/.."> in README (inside the banner block if present),
      pick the *next* file from assets using natural ordering, and update the block.
    - Uses raw.githubusercontent.com + cache-buster (?t=...) to avoid GitHub caching issues.
    - Caption prefers the number parsed from the filename (e.g., '4.gif' -> 'Banner 4/Y').
      If no number is found, falls back to the index in natural ordering (1-based).
    - If the banner block is missing, a fresh one is prepended at the top.

    Requirements:
      - Helpers expected to exist in the module:
        _list_assets()              -> List[Path]   # valid assets, naturally sorted
        _pick_next_asset(md, files) -> (str, int)   # returns (relative_path 'assets/..', index_1based)
        _to_raw_url(rel_path)       -> str          # raw github URL
    """
    files = _list_assets()
    if not files:
        return md_text

    # Choose the next asset (stateless: based on what's currently in README)
    next_rel, idx_fallback = _pick_next_asset(md_text, files)

    # Build a cache-busted raw URL
    bust = int(datetime.datetime.utcnow().timestamp())
    img_src = f'{_to_raw_url(next_rel)}?t={bust}'

    # --- Derive caption number from the filename when possible ---
    # e.g., 'assets/4.gif' -> 4; 'assets/07.webp' -> 7
    import os as _os
    import re as _re
    base = _os.path.basename(next_rel)
    mnum = _re.match(r'(\d+)', base)  # leading number only
    if mnum:
        x_num = int(mnum.group(1))
    else:
        # fallback to the natural-order index returned by _pick_next_asset
        x_num = idx_fallback

    total = len(files)
    caption_text = f'Banner {x_num}/{total}'
    caption_html = f'<p align="center"><sub>🖼️ {caption_text}</sub></p>\n'

    # Fresh block content we can fall back to if patching fails
    new_inner = (
        f'\n<p align="center">\n'
        f'  <img src="{img_src}" alt="Banner" width="960">\n'
        f'</p>\n' + caption_html
    )

    # Try to patch an existing banner block first
    block_pat = r"(<!-- BANNER:START -->)(.*?)(<!-- BANNER:END -->)"
    mblock = _re.search(block_pat, md_text, flags=_re.S)

    if mblock:
        inner = mblock.group(2)

        # 1) Update image src (handles relative and raw URLs that point into /assets/)
        innerpatched = _re.sub(
            r'src="[^"]*?/assets/[^"?"]+[^"]*"',
            f'src="{img_src}"',
            inner,
            flags=_re.I
        )

        # 2) Update caption "Banner X/Y" (preserve or add the 🖼️ emoji)
        innerpatched = _re.sub(
            r'(?:🖼️\s*)?Banner\s+\d+/\d+',
            f'🖼️ {caption_text}',
            innerpatched,
            flags=_re.I
        )

        # If there was no caption at all, append it under the image
        if 'Banner' not in innerpatched:
            # place after the closing </p> of the image if present; otherwise just append
            after_img = _re.sub(r'(</p>\s*)$', r'\1' + caption_html, innerpatched, count=1)
            if after_img == innerpatched:
                innerpatched = innerpatched + caption_html

        # If anything changed, return the patched block
        if innerpatched != inner:
            return md_text[:mblock.start(2)] + innerpatched + md_text[mblock.end(2):]

        # If we couldn’t safely patch, overwrite inner with a fresh block
        return md_text[:mblock.start(2)] + new_inner + md_text[mblock.end(2):]

    # No banner block yet — prepend a fresh one to the README
    banner_block = f'<!-- BANNER:START -->{new_inner}<!-- BANNER:END -->\n'
    return banner_block + md_text


# --------- Dynamic Insight ---------
MORNING_QUOTES = [
    "Time for some coffee and MLOps ☕",
    "Start your morning with automation! 🛠️",
    "Good morning! Let's optimize ML experiments! 🎯",
]
AFTERNOON_QUOTES = [
    "Keep pushing your MLOps pipeline forward! 🔧",
    "Optimize, deploy, repeat! 🔄",
    "Perfect time for CI/CD magic! ⚡",
]
EVENING_QUOTES = [
    "Evening is the best time to track ML experiments 🌙",
    "Relax and let automation handle your work 🤖",
    "Wrap up the day with some Bayesian tuning 🎯",
]
DAY_OF_WEEK_QUOTES = {
    "Monday": "Start your week strong! 🚀",
    "Tuesday": "Keep up the momentum! 🔥",
    "Wednesday": "Halfway to the weekend, keep automating! 🛠️",
    "Thursday": "Test, iterate, deploy! 🚀",
    "Friday": "Wrap it up like a pro! 🔥",
    "Saturday": "Weekend automation vibes! 🎉",
    "Sunday": "Prepare for an MLOps-filled week! ⏳",
}
EXTRA_EMOJIS = ["🚀", "⚡", "🔥", "💡", "🎯", "🔄", "📈", "🛠️"]


def get_dynamic_quote():
    """Pick a time-of-day + weekday flavored quote with a random emoji."""
    now = datetime.datetime.utcnow()
    day_of_week = now.strftime("%A")
    hour = now.hour

    if 6 <= hour < 12:
        selected = random.choice(MORNING_QUOTES)
    elif 12 <= hour < 18:
        selected = random.choice(AFTERNOON_QUOTES)
    else:
        selected = random.choice(EVENING_QUOTES)

    selected += f" | {DAY_OF_WEEK_QUOTES[day_of_week]}"
    selected += f" {random.choice(EXTRA_EMOJIS)}"
    return selected


# -----------------------------------

def generate_new_readme():
    md_path = Path(README_FILE)
    md = md_path.read_text(encoding="utf-8")

    # 1) Rotate the banner (stateless)
    md = rotate_banner_in_md(md)

    # 2) Update timestamp and insight line
    now = datetime.datetime.utcnow()
    dynamic_quote = get_dynamic_quote()

    lines = md.splitlines(keepends=True)
    updated = []
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

    md_path.write_text("".join(updated), encoding="utf-8")
    print(f"✅ README updated at {now} UTC")
    print(f"🖼️ Banner mode: {BANNER_MODE}")
    print(f"📝 Quote: {dynamic_quote}")


if __name__ == "__main__":
    generate_new_readme()
