import datetime
import random
import re
from pathlib import Path

README_FILE = "README.md"

# ============ ROTATING BANNER SETTINGS ============
ASSETS = Path("assets")
STATE = ASSETS / ".banner_state"      # persists the last shown banner path
MAX_MB = 10
EXTS = {".gif", ".webp", ".png", ".jpg", ".jpeg"}

# Banner selection mode: "sequential" | "random"
BANNER_MODE = "sequential"

# ---------- utils ----------
def _natkey(p: Path):
    """
    Natural sort key: ensures 2.gif < 10.gif.
    Splits string into digit/non-digit chunks and converts digits to int.
    """
    import re as _re
    s = p.name.lower()
    return [
        (int(t) if t.isdigit() else t)
        for t in _re.findall(r"\d+|\D+", s)
    ]

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
# ---------------------------

def pick_image_random():
    """Pick a random asset, avoiding the last shown one when possible."""
    files = _list_assets()
    if not files:
        return None
    last = STATE.read_text().strip() if STATE.exists() else ""
    paths = [f.as_posix() for f in files]
    candidates = [p for p in paths if p != last] or paths
    choice = random.choice(candidates)
    STATE.write_text(choice)
    return choice

def pick_image_sequential():
    """Pick the next asset in order (wraps around)."""
    files = _list_assets()
    if not files:
        return None
    last = STATE.read_text().strip() if STATE.exists() else ""
    paths = [f.as_posix() for f in files]
    try:
        i = paths.index(last)
        nxt = paths[(i + 1) % len(paths)]
    except ValueError:
        nxt = paths[0]
    STATE.write_text(nxt)
    return nxt

def rotate_banner_in_md(md_text: str) -> str:
    """
    Replace/insert the banner between:
      <!-- BANNER:START --> ... <!-- BANNER:END -->
    Always overwrite the inner block so we don't depend on previous markup.
    If the block is missing, insert it at the very top of the README.
    """
    pat = r"(<!-- BANNER:START -->)(.*?)(<!-- BANNER:END -->)"
    m = re.search(pat, md_text, flags=re.S)

    files = _list_assets()
    if not files:
        return md_text

    # pick next banner (sequential or random)
    img = pick_image_sequential() if BANNER_MODE == "sequential" else pick_image_random()
    if not img:
        return md_text

    # cache buster (GitHub caches aggressively)
    bust = int(datetime.datetime.utcnow().timestamp())
    img_src = f'{img}?t={bust}'

    # position / counter only for caption
    paths = [f.as_posix() for f in files]
    try:
        idx = paths.index(img) + 1
    except ValueError:
        idx = 0
    caption = f'<p align="center"><sub>🖼️ Banner {idx}/{len(files)}</sub></p>\n' if idx else ""

    # always rebuild the inner HTML
    new_inner = (
        f'\n<p align="center">\n'
        f'  <img src="{img_src}" alt="Banner" width="960">\n'
        f'</p>\n' + caption
    )

    if m:
        # overwrite whatever is between START/END with our new block
        return md_text[:m.start(2)] + new_inner + md_text[m.end(2):]
    else:
        # no banner block yet — prepend a fresh one
        banner_block = f'<!-- BANNER:START -->{new_inner}<!-- BANNER:END -->\n'
        return banner_block + md_text
# ===================================================

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
    md = Path(README_FILE).read_text(encoding="utf-8")

    # 1) Rotate the banner
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

    Path(README_FILE).write_text("".join(updated), encoding="utf-8")
    print(f"✅ README updated at {now} UTC")
    print(f"🖼️ Banner mode: {BANNER_MODE}")
    print(f"📝 Quote: {dynamic_quote}")

if __name__ == "__main__":
    generate_new_readme()
