import datetime
import random
import re
from pathlib import Path

README_FILE = "README.md"

# --------- ROTATING BANNER SETTINGS ---------
ASSETS = Path("assets")
STATE = ASSETS / ".banner_state"
MAX_MB = 10
EXTS = {".gif", ".webp", ".png", ".jpg", ".jpeg"}

def pick_image_random():
    files = []
    for p in ASSETS.iterdir():
        if p.is_file() and p.suffix.lower() in EXTS and not p.name.startswith("."):
            if p.stat().st_size <= MAX_MB * 1024 * 1024:
                files.append(p)
    if not files:
        return None
    last = STATE.read_text().strip() if STATE.exists() else ""
    candidates = [f for f in files if f.as_posix() != last] or files
    choice = random.choice(candidates).as_posix()
    STATE.write_text(choice)
    return choice

def rotate_banner_in_md(md_text: str) -> str:
    pat = r"(<!-- BANNER:START -->)(.*?)(<!-- BANNER:END -->)"
    m = re.search(pat, md_text, flags=re.S)
    if not m:
        return md_text
    block = m.group(2)
    img = pick_image_random()
    if not img:
        return md_text
    new_block = re.sub(r'src="assets/[^"]+"', f'src="{img}"', block)
    if new_block == block:
        new_block = f'\n<p align="center">\n  <img src="{img}" alt="Banner" width="960">\n</p>\n'
    return md_text[:m.start(2)] + new_block + md_text[m.end(2):]
# --------------------------------------------

MORNING_QUOTES = [
    "Time for some coffee and MLOps ☕",
    "Start your morning with automation! 🛠️",
    "Good morning! Let's optimize ML experiments! 🎯"
]
AFTERNOON_QUOTES = [
    "Keep pushing your MLOps pipeline forward! 🔧",
    "Optimize, deploy, repeat! 🔄",
    "Perfect time for CI/CD magic! ⚡"
]
EVENING_QUOTES = [
    "Evening is the best time to track ML experiments 🌙",
    "Relax and let automation handle your work 🤖",
    "Wrap up the day with some Bayesian tuning 🎯"
]
DAY_OF_WEEK_QUOTES = {
    "Monday": "Start your week strong! 🚀",
    "Tuesday": "Keep up the momentum! 🔥",
    "Wednesday": "Halfway to the weekend, keep automating! 🛠️",
    "Thursday": "Test, iterate, deploy! 🚀",
    "Friday": "Wrap it up like a pro! 🔥",
    "Saturday": "Weekend automation vibes! 🎉",
    "Sunday": "Prepare for an MLOps-filled week! ⏳"
}
EXTRA_EMOJIS = ["🚀", "⚡", "🔥", "💡", "🎯", "🔄", "📈", "🛠️"]

def get_dynamic_quote():
    now = datetime.datetime.utcnow()
    day_of_week = now.strftime("%A")
    hour = now.hour
    if 6 <= hour < 12:
        selected_quote = random.choice(MORNING_QUOTES)
    elif 12 <= hour < 18:
        selected_quote = random.choice(AFTERNOON_QUOTES)
    else:
        selected_quote = random.choice(EVENING_QUOTES)
    selected_quote += f" | {DAY_OF_WEEK_QUOTES[day_of_week]}"
    selected_quote += f" {random.choice(EXTRA_EMOJIS)}"
    return selected_quote

def generate_new_readme():
    md = Path(README_FILE).read_text(encoding="utf-8")

   
    md = rotate_banner_in_md(md)

   
    now = datetime.datetime.utcnow()
    dynamic_quote = get_dynamic_quote()

    lines = md.splitlines(keepends=True)
    updated = []
    saw_updated, saw_insight = False, False
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
    print(f"📝 Quote: {dynamic_quote}")

if __name__ == "__main__":
    generate_new_readme()
