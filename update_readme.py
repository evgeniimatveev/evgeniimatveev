# update_readme.py
# -*- coding: utf-8 -*-
"""
README auto-updater:
- Rotates banner (stateless) with cache-busted raw URL
- Updates "Last updated:" and "🔥 MLOps Insight:" lines
- Injects/refreshes a <details> Run Meta block with links
- Appends JSON run-log and injects <details> Recent updates (last 5)
"""

from __future__ import annotations

import json, os, re, datetime, random
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

# -------- Config --------
README_FILE = "README.md"
ASSETS = Path("assets")
STATE_DIR = Path(".cache")           # keeps banner state and run log
STATE_DIR.mkdir(parents=True, exist_ok=True)

MAX_MB = 10
EXTS = {".gif", ".webp", ".png", ".jpg", ".jpeg"}

BANNER_MODE = os.getenv("BANNER_MODE", "sequential").strip().lower()
CAL_MODE = os.getenv("BANNER_CALENDAR_MODE", "").strip().lower() in {"1", "true", "yes"}

# Run-log & details markers
RUN_LOG_JSON = STATE_DIR / "run_log.json"
LOG_START = "<!-- LOG:START -->"
LOG_END   = "<!-- LOG:END -->"
RUNS_TO_SHOW = 5

# -------- Utils --------
def _natkey(p: Path) -> List[object]:
    s = p.name.lower()
    return [(int(t) if t.isdigit() else t) for t in re.findall(r"\d+|\D+", s)]

def _list_assets() -> List[Path]:
    if not ASSETS.exists():
        return []
    out = []
    for p in ASSETS.iterdir():
        if p.is_file() and p.suffix.lower() in EXTS and not p.name.startswith(".") and p.stat().st_size <= MAX_MB * 1024 * 1024:
            out.append(p)
    return sorted(out, key=_natkey)

def _to_raw_url(rel_path: str) -> str:
    repo = os.getenv("GITHUB_REPOSITORY", "evgeniimatveev/evgeniimatveev")
    branch = os.getenv("GITHUB_REF_NAME", "main")
    return f"https://raw.githubusercontent.com/{repo}/{branch}/{rel_path}"

def _extract_current_asset_from_md(md_text: str) -> Optional[str]:
    m = re.search(r"(<!-- BANNER:START -->)(.*?)(<!-- BANNER:END -->)", md_text, flags=re.S)
    scope = m.group(2) if m else md_text
    m2 = re.search(r'src="([^"]*?/assets/[^"?"]+)', scope, flags=re.I)
    if not m2:
        return None
    url = m2.group(1)
    tail = re.search(r'/assets/([^/]+)$', url)
    return f'assets/{tail.group(1)}' if tail else (url if url.startswith("assets/") else None)

def _pick_next_asset(md_text: str, files: List[Path]) -> Tuple[str, int]:
    if not files:
        raise RuntimeError("No valid assets found in 'assets/'.")
    paths = [f.as_posix() for f in files]
    if CAL_MODE:
        doy = int(datetime.datetime.utcnow().strftime("%j"))
        idx = (doy - 1) % len(paths)
        return paths[idx], idx + 1
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
def rotate_banner_in_md(md_text: str) -> Tuple[str, Tuple[int,int]]:
    files = _list_assets()
    if not files:
        return md_text, (0, 0)

    next_rel, idx_fallback = _pick_next_asset(md_text, files)
    bust = int(datetime.datetime.utcnow().timestamp())
    img_src = f'{_to_raw_url(next_rel)}?t={bust}'

    base = os.path.basename(next_rel)
    mnum = re.match(r'(\d+)', base)
    x_num = int(mnum.group(1)) if mnum else idx_fallback

    total = len(files)
    caption_text = f'Banner {x_num}/{total}'
    caption_html = '<p align="center"><sub>🖼️ ' + caption_text + '</sub></p>\n'

    new_inner = (
        '\n<p align="center">\n'
        '  <img src="' + img_src + '" alt="Banner" style="max-width:960px;width:100%;">\n'
        '</p>\n' + caption_html
    )

    mblock = re.search(r"(<!-- BANNER:START -->)(.*?)(<!-- BANNER:END -->)", md_text, flags=re.S)
    if mblock:
        inner = mblock.group(2)
        inner_patched = re.sub(r'src="[^"]*?/assets/[^"?"]+[^"]*"', 'src="' + img_src + '"', inner, flags=re.I)
        inner_patched2 = re.sub(r'(?:🖼️\s*)?Banner\s+\d+/\d+', '🖼️ ' + caption_text, inner_patched, flags=re.I)
        if 'Banner' not in inner_patched2:
            after_img = re.sub(r'(</p>\s*)$', r'\1' + caption_html, inner_patched2, count=1)
            if after_img == inner_patched2:
                inner_patched2 = inner_patched2 + caption_html
        new_md = md_text[:mblock.start(2)] + inner_patched2 + md_text[mblock.end(2):]
        return new_md, (x_num, total)

    banner_block = '<!-- BANNER:START -->' + new_inner + '<!-- BANNER:END -->\n'
    return banner_block + md_text, (x_num, total)

# -------- Quotes & headline --------
MORNING_QUOTES = [
    "Time for some coffee and MLOps ☕","Start your morning with automation! 🛠️",
    "Good morning! Let's optimize ML experiments! 🎯","Kick off with clean pipelines and clear metrics 📊",
    "Bootstrap your day with reproducible runs 🔁","Ship small, ship early, measure always 📈",
    "Warm up the DAGs and run smoke tests 🌅","Start with data quality, end with insights ✅",
    "One small PR before breakfast 🍳","Spin up environments, hydrate the features 💧",
]
AFTERNOON_QUOTES = [
    "Keep pushing your MLOps pipeline forward! 🔧","Perfect time for CI/CD magic ⚡",
    "Optimize, deploy, repeat! 🔄","Measure → iterate → ship 🚀","Refactor the DAGs, simplify the flows 🧩",
    "Guardrails on, feature flags ready 🧯","Profile the hotspots, cache the wins 🧠",
    "Review metrics, cut toil, add value 📉→📈","Monitor, alert, respond — calmly 🧭",
    "Make it boring: stable, predictable releases 🫡",
]
EVENING_QUOTES = [
    "Evening is the best time to track ML experiments 🌙","Relax and let automation handle your work 🤖",
    "Wrap up the day with some Bayesian tuning 🎯","Document results, queue tomorrow's jobs 📝",
    "Small wins today, big gains tomorrow 📈","Close issues, open insights ✅",
    "Archive artifacts, tag the best runs 🏷️","Cool down the cluster, warm up ideas ❄️💡",
    "Write the changelog you wish you had 📓","Reflect, refactor, and rest 🌌",
]
DAY_OF_WEEK_QUOTES = {
    "Monday": "Start your week strong! 🚀","Tuesday": "Keep up the momentum! 🔥",
    "Wednesday": "Halfway there — keep automating! 🛠️","Thursday": "Test, iterate, deploy! 🚀",
    "Friday": "Wrap it up like a pro! ⚡","Saturday": "Weekend automation vibes! 🎉",
    "Sunday": "Prep for an MLOps-filled week! ⏳",
}
SEASON_QUOTES = {
    "Spring": ["Fresh start — time to grow 🌸","Refactor and bloom 🌼","Spring into automation! 🪴","Plant ideas, water pipelines 🌱","Rebuild with lighter dependencies 🌿","Nurture data quality from the root 🌷"],
    "Summer": ["Keep shining and shipping ☀️","Hot pipelines, cool results 🔥","Sunny mindset, clean commits 😎","Scale up smart, throttle costs 🏖️","Ship value before the sunset 🌇","Heat-proof your infra with tests 🔥🧪"],
    "Autumn": ["Reflect, refine, retrain 🍂","Collect insights like golden leaves 🍁","Harvest your best MLOps ideas 🌾","Prune legacy, keep essentials ✂️","Tune models, store wisdom 📦","Backtest decisions, bank learnings 🏦"],
    "Winter": ["Deep focus and model tuning ❄️","Hibernate and optimize 🧊","Great time for infra upgrades 🛠️","Keep the core warm and robust 🔧","Reduce noise, raise signal 📡","Plan roadmaps with calm clarity 🧭"],
}
EXTRA_EMOJIS = ["🚀","⚡","🔥","💡","🎯","🔄","📈","🛠️","🧠","🤖","🧪","✅","📊","🧭","🌅","🌇","🌙","❄️","🍁","☀️","🌸","🌾","🌈","🌊"]
HEADLINE_TEMPLATES = [
    "MLOPS DAILY","BUILD • MEASURE • LEARN","AUTOMATE EVERYTHING",
    "SHIP SMALL, SHIP OFTEN","EXPERIMENT → INSIGHT → DEPLOY","DATA • CODE • IMPACT",
    "TRACK • TUNE • TRUST","REPRODUCIBILITY FIRST","OBSERVE • ALERT • IMPROVE",
    "LOW TOIL, HIGH LEVERAGE","METRICS OVER MYTHS","PIPELINES, NOT FIRE-DRILLS",
]

def _get_season_by_month(m: int) -> str:
    if m in (3,4,5): return "Spring"
    if m in (6,7,8): return "Summer"
    if m in (9,10,11): return "Autumn"
    return "Winter"

def _style_text(text: str) -> str:
    r = random.random()
    if r < 0.30: return text.upper()
    if r < 0.60:
        parts, keep_caps = [], ("🧪","🚀","⚡","🔥","💡","🎯","🔄","📈","🛠️","🧠","🤖","❄️","☀️","🍁","🌸","😎","🌙","📝","✅")
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
    vibe = random.choice(MORNING_QUOTES if 6 <= hour < 12 else AFTERNOON_QUOTES if 12 <= hour < 18 else EVENING_QUOTES)
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

    open_run_link = f"[open run]({open_run})" if open_run else "—"
    open_commit_link = f"[open commit]({open_commit})" if open_commit else "—"

    meta_lines = [
        "<details>",
        "  <summary>🗒️ Run Meta (click to expand)</summary>",
        "",
        f"- 🕒 Updated (UTC): **{now_utc}**",
        f"- 🔢 Run: **#{run_no}** — {open_run_link}",
        f"- 🔗 Commit: **{sha}** — {open_commit_link}",
        "- ⚙️ Workflow: **Auto Update README** · Job: **update-readme**",
        f"- 🪄 Event: **{event}** · 👤 Actor: **{actor}**",
        f"- ⏱️ Schedule: **{schedule}**",
        f"- 🖼️ Banner: **{banner_pos[0]}/{banner_pos[1]}**",
        "</details>",
        ""
    ]
    meta_md = "\n".join(meta_lines)

    pat = r"(<!-- RUNMETA:START -->)(.*?)(<!-- RUNMETA:END -->)"
    m = re.search(pat, md_text, flags=re.S)
    if m:
        return md_text[:m.start(2)] + "\n" + meta_md + "\n" + md_text[m.end(2):]
    return md_text + "\n<!-- RUNMETA:START -->\n" + meta_md + "\n<!-- RUNMETA:END -->\n"

# -------- Run log --------
def _load_json(p: Path, default):
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default

def _save_json(p: Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def append_run_log_from_env() -> None:
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    entry = {
        "time_utc": now,
        "run": os.getenv("GITHUB_RUN_NUMBER") or os.getenv("RUN_NUMBER") or "",
        "sha": (os.getenv("GITHUB_SHA") or "")[:7],
        "banner": os.getenv("BANNER_HINT",""),
        "actor": f"{os.getenv('GITHUB_EVENT_NAME','manual')}/{os.getenv('GITHUB_ACTOR','')}",
        "insight": os.getenv("MLOPS_INSIGHT",""),
    }
    if not (entry["sha"] or entry["run"] or entry["insight"]):
        return
    data: List[Dict[str, Any]] = _load_json(RUN_LOG_JSON, [])
    key = (entry["sha"] or "").lower() or str(entry["run"])
    def _k(e): return (e.get("sha","") or "").lower() or str(e.get("run",""))
    for i, e in enumerate(data):
        if key and _k(e) == key:
            data[i] = {**e, **entry}
            break
    else:
        data.append(entry)
    data.sort(key=lambda e: e.get("time_utc",""), reverse=True)
    _save_json(RUN_LOG_JSON, data)

def _recent_updates_table(n: int = RUNS_TO_SHOW) -> str:
    data: List[Dict[str, Any]] = _load_json(RUN_LOG_JSON, [])
    head = "| Time (UTC) | Run | SHA | Banner | Event/Actor | Insight |\n|---|---|---|---|---|---|"
    if not data:
        return head + "\n| _no data_ |  |  |  |  |  |"
    rows = []
    for r in data[:n]:
        row = (
            "| " + r.get('time_utc','') + " | " + str(r.get('run','')) + " | `" + (r.get('sha','')[:7]) + "` | "
            + r.get('banner','') + " | " + r.get('actor','') + " | " + str(r.get('insight','')).replace('\n',' ') + " |"
        )
        rows.append(row)
    return head + "\n" + "\n".join(rows)

def inject_recent_updates_block(md_text: str) -> str:
    details = "<details><summary><b>Recent updates (last 5)</b></summary>\n\n" + _recent_updates_table(RUNS_TO_SHOW) + "\n\n</details>"
    block = LOG_START + "\n\n" + details + "\n\n" + LOG_END
    if LOG_START in md_text and LOG_END in md_text:
        return re.sub(re.compile(re.escape(LOG_START) + r".*?" + re.escape(LOG_END), re.DOTALL), block, md_text)
    return md_text.rstrip() + "\n\n" + block + "\n"

# -------- Main driver --------
def generate_new_readme() -> None:
    md_path = Path(README_FILE)
    md = md_path.read_text(encoding="utf-8")

    # 1) Rotate banner
    md, banner_pos = rotate_banner_in_md(md)

    # 2) Update timestamp + insight
    now = datetime.datetime.utcnow()
    dynamic_quote = get_dynamic_quote()

    lines = md.splitlines(keepends=True)
    updated, saw_updated, saw_insight = [], False, False
    for line in lines:
        if line.startswith("Last updated:"):
            updated.append("Last updated: " + str(now) + " UTC\n")
            saw_updated = True
        elif line.startswith("🔥 MLOPS Insight:"):
            insight_line = os.getenv("MLOPS_INSIGHT", "").strip() or "💡 " + dynamic_quote
            updated.append("🔥 MLOPS Insight: " + insight_line + "\n")
            saw_insight = True
        else:
            updated.append(line)
    if not saw_updated:
        updated.append("\nLast updated: " + str(now) + " UTC\n")
    if not saw_insight:
        insight_line = os.getenv("MLOPS_INSIGHT", "").strip() or "💡 " + dynamic_quote
        updated.append("\n🔥 MLOPS Insight: " + insight_line + "\n")
    md = "".join(updated)

    # 3) Run Meta
    md = _update_runmeta_block(md, banner_pos=banner_pos)

    # 4) Run-log + details
    append_run_log_from_env()
    md = inject_recent_updates_block(md)

    # 5) Save
    md_path.write_text(md, encoding="utf-8")

    # 6) Console heartbeat
    run_no    = os.getenv("GITHUB_RUN_NUMBER", "?")
    short_sha = os.getenv("GITHUB_SHA", "")[:7]
    schedule  = os.getenv("SCHEDULE_BADGE", "24h_5m")
    next_eta = (now + datetime.timedelta(days=1)).strftime("%Y-%m-%d %H:%M UTC")

    bar = "─" * 72
    print("\n" + bar)
    print("✅ README updated: " + now.strftime("%Y-%m-%d %H:%M:%S") + " UTC")
    print("🖼️ Banner mode: " + ("calendar" if CAL_MODE else BANNER_MODE) + f"   🔢 Run: #{run_no}   🔗 SHA: {short_sha}")
    env_insight = os.getenv('MLOPS_INSIGHT', '')
    print("💬 Insight: " + (env_insight if env_insight else "(dynamic) " + dynamic_quote))
    print(f"⏱️ Schedule: {schedule}   ▶️ Next ETA: {next_eta}")
    print(bar + "\n")

if __name__ == "__main__":
    generate_new_readme()
