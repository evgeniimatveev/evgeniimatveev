# update_readme.py
# -*- coding: utf-8 -*-
"""
README auto-updater:
- Rotates banner (stateless) with cache-busted raw URL
- Updates "Last updated:" and "🔥 MLOps Insight:" lines
- Injects/refreshes a <details> Run Meta block with links
- Optional calendar-based banner rotation (stable per day of year)

Env vars:
  BANNER_MODE = sequential | random           (default: sequential)
  BANNER_CALENDAR_MODE = true/1/yes           (default: off)
  GITHUB_* (provided by Actions)              (for links/metadata)
  SCHEDULE_BADGE (optional)                   (for Run Meta display only)
"""

from __future__ import annotations

import json
import hashlib
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

BANNER_MODE = os.getenv("BANNER_MODE", "sequential").strip().lower()
CAL_MODE = os.getenv("BANNER_CALENDAR_MODE", "").strip().lower() in {"1", "true", "yes"}

# -------- Utils --------
def _natkey(p: Path) -> List[object]:
    s = p.name.lower()
    return [(int(t) if t.isdigit() else t) for t in re.findall(r"\d+|\D+", s)]

def _list_assets() -> List[Path]:
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
    repo = os.getenv("GITHUB_REPOSITORY", "evgeniimatveev/evgeniimatveev")
    branch = os.getenv("GITHUB_REF_NAME", "main")
    return f"https://raw.githubusercontent.com/{repo}/{branch}/{rel_path}"

def _extract_current_asset_from_md(md_text: str) -> Optional[str]:
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
    """Return ('assets/<file>', 1-based-index) for next banner."""
    if not files:
        raise RuntimeError("No valid assets found in 'assets/'.")
    paths = [f.as_posix() for f in files]

    # Calendar-stable mode has priority over others
    if CAL_MODE:
        doy = int(datetime.datetime.utcnow().strftime("%j"))  # 1..366
        idx = (doy - 1) % len(paths)
        choice = paths[idx]
        return choice, idx + 1

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
def rotate_banner_in_md(md_text: str) -> Tuple[str, Tuple[int,int]]:
    """
    Returns (new_md, (x,total)), where x/total is shown in caption and used in Run Meta.
    """
    files = _list_assets()
    if not files:
        return md_text, (0, 0)

    # Choose next asset path and its index (1-based in sorted list)
    next_rel, idx_fallback = _pick_next_asset(md_text, files)

    # Cache-busted raw URL
    bust = int(datetime.datetime.utcnow().timestamp())
    img_src = f'{_to_raw_url(next_rel)}?t={bust}'

    # Determine X from filename if numeric prefix; else fallback index
    base = os.path.basename(next_rel)
    mnum = re.match(r'(\d+)', base)
    x_num = int(mnum.group(1)) if mnum else idx_fallback

    total = len(files)
    caption_text = f'Banner {x_num}/{total}'
    caption_html = f'<p align="center"><sub>🖼️ {caption_text}</sub></p>\n'

    new_inner = (
        f'\n<p align="center">\n'
        f'  <img src="{img_src}" alt="Banner" style="max-width:960px;width:100%;">\n'
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
            new_md = md_text[:mblock.start(2)] + inner_patched2 + md_text[mblock.end(2):]
        else:
            new_md = md_text[:mblock.start(2)] + new_inner + md_text[mblock.end(2):]
        return new_md, (x_num, total)

    # If block absent — prepend a fresh one
    banner_block = f'<!-- BANNER:START -->{new_inner}<!-- BANNER:END -->\n'
    return banner_block + md_text, (x_num, total)

 ===================== MLOps Quotes (Unified & Compact) =====================

from collections import OrderedDict

def _dedupe(seq):
    return list(OrderedDict.fromkeys(seq))

# === More variety (drop-in additions) ===

MORNING_QUOTES += [
    "Kickstart the day with green checks and clean diffs ✅🧼",
    "Caffeinate, lint, and log wisely ☕🧪",
    "Warm caches, cold starts, steady pipelines ❄️🔄",
    "Spin up, smoke test, ship a slice 🚀🧪",
    "Make the first commit count 🧠🖋️",
    "Hydrate features, sync schemas, breathe 💧📂",
    "Morning stand-up, evening stand-down 🧍‍♂️↔️🛏️",
    "Fewer flags, clearer flows 🎯🧩",
    "Start simple, measure truth 📊💡",
    "Steady inputs → stable outputs 🔧📦",
]

AFTERNOON_QUOTES += [
    "Bench, profile, optimize — then commit 📈🧠",
    "Cut toil, raise signal 📉→📡",
    "Push the canary, watch the graphs 🐤📊",
    "Docs or it didn’t happen 📓✨",
    "Lower variance, higher confidence 🎯📏",
    "Refactor small, deliver often 🔁🚀",
    "Ruthless with flakiness, gentle with humans 🛟✅",
    "Cache misses pay the bill — fix them 💾⚙️",
    "Resilience beats brilliance on-call 🧯🧭",
    "Guard the SLO, respect the budget ⏱️💎",
]

EVENING_QUOTES += [
    "Close loops, open learnings 🔄📚",
    "Archive artifacts, retire the noise 📦🔕",
    "Tag the champion, park the challengers 🏷️🎯",
    "Cool the cluster, warm the roadmap ❄️🗺️",
    "Write once, run always — reproducibility first 🧪💾",
    "Queue tomorrow’s batch and sleep well ⏳🛏️",
    "Curate insights, trim the backlog ✂️💡",
    "One clean PR before lights out 🍳💡",
    "Snapshot state, freeze versions 🧊📦",
    "Reflect on impact, not effort 🌌📈",
]

# Optional alternates per day (keep your original DAY_OF_WEEK_QUOTES as-is)
DAY_OF_WEEK_ALTS = {
    "Monday": [
        "Monday: align goals, pin metrics 📌📊",
        "New week, new slice of value 🍰🚀",
    ],
    "Tuesday": [
        "Tuesday: prune scope, grow signal ✂️📡",
        "Keep momentum, kill blockers 🔥🧱",
    ],
    "Wednesday": [
        "Midweek: stabilize, then accelerate 🧱⚡",
        "Halfway: fewer knobs, better defaults 🧩✅",
    ],
    "Thursday": [
        "Thursday: test hard, deploy soft 🧪🛟",
        "Pre-weekend: canary first, main later 🐤🚀",
    ],
    "Friday": [
        "Friday: ship small, sleep well 😴✅",
        "Wrap clean, leave breadcrumbs 📓🧵",
    ],
    "Saturday": [
        "Saturday: sandbox ideas, zero risk 🧪🧰",
        "Light touch, heavy learning 😎💡",
    ],
    "Sunday": [
        "Sunday: roadmap calm, queues ready 🗺️⏳",
        "Prep quietly, launch loudly tomorrow 🤫🚀",
    ],
}

# Extra seasonal variety (adds; originals remain)
SEASON_QUOTES["Spring"] += [
    "Seed ideas, weed tech debt 🌱✂️",
    "Fresh data, fresh baselines 📊🌿",
    "Lightweight deps, heavy insights 🪴💡",
]
SEASON_QUOTES["Summer"] += [
    "Scale carefully, chill the costs ☀️📉",
    "Heat maps up, errors down 🔥🧯",
    "Sunny builds, shady incidents 😎🛟",
]
SEASON_QUOTES["Autumn"] += [
    "Harvest metrics, store wisdom 🍁📦",
    "Trim configs, keep clarity ✂️✨",
    "Retrain, re-evaluate, retain 📈🧠",
]
SEASON_QUOTES["Winter"] += [
    "Hibernate noise, amplify signal ❄️📡",
    "Deep focus, long tests 🧊🧪",
    "Plan lean, ship clean 🧭✅",
]

# More headline variety
HEADLINE_TEMPLATES += [
    "MEASURE TWICE, SHIP ONCE",
    "DAGs BEFORE DRAMA",
    "AUTOMATE • OBSERVE • IMPROVE",
    "CANARY FIRST, MAIN LATER",
    "LOW VARIANCE, HIGH TRUST",
    "GREEN CHECKS, QUIET PAGES",
    "DATA → DECISIONS → DELIGHT",
]

def _get_season_by_month(m: int) -> str:
    if m in (3,4,5): return "Spring"
    if m in (6,7,8): return "Summer"
    if m in (9,10,11): return "Autumn"
    return "Winter"

def _style_text(text: str) -> str:
    r = random.random()
    if r < 0.30:
        return text.upper()
    if r < 0.60:
        parts = []
        keep_caps = ("🧪","🚀","⚡","🔥","💡","🎯","🔄","📈","🛠️","🧠","🤖","❄️","☀️","🍁","🌸","😎","🌙","📝","✅")
        for token in text.split(" "):
            if any(ch.isalpha() for ch in token) and not token.isupper() and not token.startswith(keep_caps):
                parts.append(token[:1].upper() + token[1:].lower())
            else:
                parts.append(token)
        return " ".join(parts)
    return text

def get_dynamic_quote() -> str:
    now = datetime.datetime.utcnow()
    day = now.strftime("%A")
    hour = now.hour
    season = _get_season_by_month(now.month)

    if 6 <= hour < 12:
        vibe = random.choice(MORNING_QUOTES)
    elif 12 <= hour < 18:
        vibe = random.choice(AFTERNOON_QUOTES)
    else:
        vibe = random.choice(EVENING_QUOTES)

    season_line = random.choice(SEASON_QUOTES[season])
    day_line = DAY_OF_WEEK_QUOTES.get(day, "")
    tail_emoji = random.choice(EXTRA_EMOJIS)

    run_no = os.getenv("GITHUB_RUN_NUMBER")
    run_tag = f" • RUN #{run_no}" if run_no else ""

    headline = _style_text(random.choice(HEADLINE_TEMPLATES))
    core = _style_text(f"{season_line} | {day_line} {vibe} {tail_emoji}")

    return f"{headline}{run_tag} — {core}"

# -------- Run Meta block --------
def _update_runmeta_block(md_text: str, *, banner_pos: tuple[int,int]) -> str:
    """Inject/refresh a <details> Run Meta block with links."""
    run_no   = os.getenv("GITHUB_RUN_NUMBER", "")
    run_id   = os.getenv("GITHUB_RUN_ID", "")
    sha_full = os.getenv("GITHUB_SHA", "")
    sha      = sha_full[:7] if sha_full else ""
    repo     = os.getenv("GITHUB_REPOSITORY","")
    schedule = os.getenv("SCHEDULE_BADGE","24h_5m")
    actor    = os.getenv("GITHUB_ACTOR","")
    event    = os.getenv("GITHUB_EVENT_NAME","")
    now_utc  = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    open_run    = f"https://github.com/{repo}/actions/runs/{run_id}" if run_id and repo else ""
    open_commit = f"https://github.com/{repo}/commit/{sha_full}" if sha_full and repo else ""

    meta_md = f"""
<details>
  <summary>🗒️ Run Meta (click to expand)</summary>

- 🕒 Updated (UTC): **{now_utc}**
- 🔢 Run: **#{run_no}** — {'[open run](' + open_run + ')' if open_run else '—'}
- 🔗 Commit: **{sha}** — {'[open commit](' + open_commit + ')' if open_commit else '—'}
- ⚙️ Workflow: **Auto Update README** · Job: **update-readme**
- 🪄 Event: **{event}** · 👤 Actor: **{actor}**
- ⏱️ Schedule: **{schedule}**
- 🖼️ Banner: **{banner_pos[0]}/{banner_pos[1]}**
</details>
""".strip()+"\n"

    pat = r"(<!-- RUNMETA:START -->)(.*?)(<!-- RUNMETA:END -->)"
    m = re.search(pat, md_text, flags=re.S)
    if m:
        return md_text[:m.start(2)] + "\n" + meta_md + "\n" + md_text[m.end(2):]
    else:
        return md_text + "\n<!-- RUNMETA:START -->\n" + meta_md + "\n<!-- RUNMETA:END -->\n"

# -------- Main driver --------
def generate_new_readme() -> None:
    md_path = Path(README_FILE)
    md = md_path.read_text(encoding="utf-8")

    # 1) Rotate banner -> returns (md, (x,total))
    md, banner_pos = rotate_banner_in_md(md)

    # 2) Update timestamp + insight
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

    # 3) Inject/refresh RUNMETA block
    md = _update_runmeta_block(md, banner_pos=banner_pos)

    # 4) Write back
    md_path.write_text(md, encoding="utf-8")
     # --- JSONL audit log (structured) ---
    current_asset = _extract_current_asset_from_md(md) or ""
    banner_file = os.path.basename(current_asset) if current_asset else ""
    quote_hash = hashlib.sha1(dynamic_quote.encode("utf-8")).hexdigest()[:8]

    payload = {
        "ts_utc": now.strftime("%Y-%m-%d %H:%M:%S"),
        "run_id": os.getenv("GITHUB_RUN_ID", ""),
        "run_number": os.getenv("GITHUB_RUN_NUMBER", ""),
        "sha": os.getenv("GITHUB_SHA", "")[:7],
        "event": os.getenv("GITHUB_EVENT_NAME", ""),
        "actor": os.getenv("GITHUB_ACTOR", ""),
        "schedule_badge": os.getenv("SCHEDULE_BADGE", "24h_5m"),
        "banner_index": banner_pos[0],
        "banner_total": banner_pos[1],
        "banner_file": banner_file,
        "banner_mode": ("calendar" if CAL_MODE else BANNER_MODE),
        "insight_preview": dynamic_quote[:140],
        "insight_hash": quote_hash,
    }
    with open("update_log.jsonl", "a", encoding="utf-8") as jf:
        jf.write(json.dumps(payload, ensure_ascii=False) + "\n")

    
    try:
        from pathlib import Path as _P
        sz = _P("update_log.jsonl").stat().st_size
        print(f"🧾 JSONL appended · banner={banner_file} {banner_pos[0]}/{banner_pos[1]} · size={sz} bytes")
    except Exception:
        pass
    
    # 5) Log heartbeat
    run_no    = os.getenv("GITHUB_RUN_NUMBER", "?")
    short_sha = os.getenv("GITHUB_SHA", "")[:7]
    schedule  = os.getenv("SCHEDULE_BADGE", "24h_5m")
    next_eta = (now + datetime.timedelta(days=1)).strftime("%Y-%m-%d %H:%M UTC")

    bar = "─" * 72
    print("\n" + bar)
    print(f"✅ README updated: {now:%Y-%m-%d %H:%M:%S} UTC")
    print(f"🖼️ Banner mode: {'calendar' if CAL_MODE else BANNER_MODE}   🔢 Run: #{run_no}   🔗 SHA: {short_sha}")
    print(f"💬 Insight: {dynamic_quote}")
    print(f"⏱️ Schedule: {schedule}   ▶️ Next ETA: {next_eta}")
    print(bar + "\n")

if __name__ == "__main__":
    generate_new_readme()
