# build_repo_board.py
# -*- coding: utf-8 -*-
"""Self-hosted "Repo Health Board" for the profile README.

One GitHub GraphQL call (no per-repo REST calls, no third-party renderer)
produces:

  * a categorised, collapsible table of every public repo with language,
    CI status, last-push age and stars  -> README block REPOS
  * an animated status panel (repos / weekly pushes / CI health bar /
    language bar), self-drawn Tokyo Night SVG -> badges/repo_status.svg

Same architecture as build_activity_graph.py: stdlib only, idempotent
(re-running with unchanged data produces a byte-identical README/SVGs, so
the workflow commits nothing), replaces content strictly between markers.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

LOGIN = os.getenv("REPO_BOARD_LOGIN", "evgeniimatveev")
TOKEN = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
README = Path(os.getenv("REPO_BOARD_README", "README.md"))
OUT_DIR = Path(os.getenv("REPO_BOARD_OUT", "badges"))
# Image paths are relative to the README (like ./dist/snake.svg), so the same README renders
# correctly on a PR branch (preview) and on main - no per-branch absolute URLs to fix up.
ASSET_BASE = "badges"

# The profile repo itself is the page you are reading - not listed.
EXCLUDE = {LOGIN}

# Tracks, in display order: key -> (heading, open-by-default).
TRACKS = {
    "prod": ("🚀 Production apps & AI systems", True),
    "bi": ("📊 Analytics, BI & data engineering", False),
    "learn": ("🎓 A–Z learning repos", False),
    "infra": ("🧩 Self-hosted widgets & forks", False),
}
TRACK_OF = {
    # production apps & AI systems
    "route-optimization-vrp": "prod", "agent-memory": "prod",
    "civics-sql-rag": "prod", "evgeniimatveev.github.io": "prod",
    "cv-logistics-mlops": "prod", "crypto-dashboard": "prod",
    "layoffs-tracker": "prod", "so-survey-analytics": "prod",
    "weather-pipeline": "prod", "interview-coach": "prod",
    "job-market-pulse": "prod", "uber-driver-analytics": "prod",
    "mcp-data-quality-agent": "prod", "mlops_ollama_env": "prod",
    "mlops_project": "prod",
    # analytics / BI / DE
    "tableau-business-cases": "bi", "olist-e-commerce-analytics": "bi",
    "hr-bi-analytics-project": "bi", "business-sql-analytics": "bi",
    "nyc-311-duckdb-motherduck-analysis": "bi", "remote-job-tracker": "bi",
    "data-pipeline-etl-project": "bi", "Snowflake-A-Z": "bi",
    # forks / widget infra
    "snk": "infra", "github-profile-trophy": "infra",
    "github-readme-streak-stats": "infra", "github-profile-summary-cards": "infra",
}
DEFAULT_TRACK = "learn"  # anything unlisted is a learning/practice repo

# Language -> emoji marker (markdown cannot colour text; emoji is the portable option).
LANG_EMOJI = {
    "Python": "🐍", "R": "📈", "SQL": "🛢️", "JavaScript": "🟨", "TypeScript": "🔷",
    "HTML": "🟧", "Jupyter Notebook": "📓", "PHP": "🐘", "CSV": "📄",
}
CI_EMOJI = {"SUCCESS": "🟢", "FAILURE": "🔴", "ERROR": "🔴", "PENDING": "🟡", "EXPECTED": "🟡"}

# Tokyo Night - same palette as build_activity_graph.py.
SURFACE, GRID = "#1a1b26", "#2a2e42"
TEXT_PRIMARY, TEXT_SOFT, TEXT_MUTED, ACCENT = "#c0caf5", "#a9b1d6", "#565f89", "#7aa2f7"
CI_COLOR = {"SUCCESS": "#9ece6a", "FAILURE": "#f7768e", "ERROR": "#f7768e",
            "PENDING": "#e0af68", "EXPECTED": "#e0af68"}
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"

QUERY = """
query($login: String!) {
  user(login: $login) {
    repositories(first: 100, privacy: PUBLIC, ownerAffiliations: OWNER,
                 orderBy: {field: PUSHED_AT, direction: DESC}) {
      nodes {
        name description url pushedAt stargazerCount diskUsage isFork isArchived
        primaryLanguage { name color }
        defaultBranchRef { target { ... on Commit {
          statusCheckRollup { state }
        } } }
      }
    }
  }
}
"""


# ----------------------------------------------------------------- data ---
def fetch_repos(login: str, token: str) -> List[Dict[str, Any]]:
    body = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql", data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                 "User-Agent": "repo-board-builder"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode())
    if "errors" in payload:
        raise RuntimeError(f"GraphQL error: {payload['errors']}")
    repos = []
    for n in payload["data"]["user"]["repositories"]["nodes"]:
        if n["name"] in EXCLUDE or n["isArchived"]:
            continue
        target = ((n.get("defaultBranchRef") or {}).get("target") or {})
        rollup = target.get("statusCheckRollup") or {}
        lang = n.get("primaryLanguage") or {}
        repos.append({
            "name": n["name"], "url": n["url"], "desc": (n.get("description") or "").strip(),
            "pushed": dt.datetime.fromisoformat(n["pushedAt"].replace("Z", "+00:00")),
            "stars": n["stargazerCount"], "size_kb": n["diskUsage"] or 0, "fork": n["isFork"],
            "lang": lang.get("name"), "lang_color": lang.get("color") or "#8b949e",
            # A fork inherits upstream workflows, so its red/green says nothing about my code.
            "ci": None if n["isFork"] else rollup.get("state"),
        })
    return repos


def age(pushed: dt.datetime, now: dt.datetime) -> str:
    d = (now - pushed).days
    if d < 1:
        return "today"
    if d < 14:
        return f"{d}d ago"
    if d < 60:
        return f"{d // 7}w ago"
    return f"{d // 30}mo ago"


def track_of(repo: Dict[str, Any]) -> str:
    return TRACK_OF.get(repo["name"], DEFAULT_TRACK)


# ------------------------------------------------------------- markdown ---
def _cell(text: str, limit: int) -> str:
    text = text.replace("|", "\\|").replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def build_board_md(repos: List[Dict[str, Any]], now: dt.datetime, status_html: str) -> str:
    lines = [status_html, ""]
    for key, (heading, is_open) in TRACKS.items():
        group = [r for r in repos if track_of(r) == key]
        if not group:
            continue
        group.sort(key=lambda r: r["pushed"], reverse=True)
        lines.append(f'<details{" open" if is_open else ""}>')
        lines.append(f"<summary><b>{heading}</b> <em>({len(group)})</em></summary>")
        lines.append("")
        lines.append("| Repo | What it is | Lang | CI | Updated | ⭐ |")
        lines.append("|---|---|---|:-:|---|--:|")
        for r in group:
            lang = f'{LANG_EMOJI.get(r["lang"], "⚪")} {r["lang"]}' if r["lang"] else "—"
            fork = " <sub>fork</sub>" if r["fork"] else ""
            lines.append(
                f'| [**{r["name"]}**]({r["url"]}){fork} | {_cell(r["desc"], 90) or "—"} | {lang} | '
                f'{CI_EMOJI.get(r["ci"], "⚪")} | {age(r["pushed"], now)} | {r["stars"]} |')
        lines += ["", "</details>", ""]
    lines.append('<p align="center"><sub>Generated from the GitHub GraphQL API by '
                 '<code>build_repo_board.py</code> · CI = default-branch check status · '
                 'refreshed daily · no third-party renderer</sub></p>')
    return "\n".join(lines)


# ------------------------------------------------------------ status SVG ---
def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


SW, SH = 744, 152
STATUS_CSS = (
    "@keyframes up{from{opacity:0;transform:translateY(7px)}to{opacity:1;transform:none}}"
    "@keyframes grow{from{transform:scaleX(0)}to{transform:scaleX(1)}}"
    "@keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}"
    ".t{animation:up .7s ease-out both}"
    ".b{transform-box:fill-box;transform-origin:left;animation:grow 1.1s cubic-bezier(.2,.8,.2,1) both}"
    ".live{animation:pulse 2s ease-in-out infinite}"
    # Whole-perimeter neon border drifting through the portfolio site's "chameleon" palette
    # (amber -> teal -> cobalt -> violet -> wine, hue 30/185/220/270/335, 26 s loop, same
    # hsl(h 90% 68%) accent) while the glow "breathes". Any failing CI = red/amber + fast blink.
    "@keyframes hue{0%,100%{stroke:hsl(30,90%,68%)}20%{stroke:hsl(185,90%,68%)}"
    "40%{stroke:hsl(220,90%,68%)}60%{stroke:hsl(270,90%,68%)}80%{stroke:hsl(335,90%,68%)}}"
    "@keyframes breathe{0%,100%{opacity:.3}50%{opacity:.95}}"
    "@keyframes hue-bad{0%,100%{stroke:#f7768e}50%{stroke:#e0af68}}"
    "@keyframes breathe-bad{0%,100%{opacity:.25}50%{opacity:1}}"
    ".edge,.glow{fill:none}"
    ".edge{animation:hue 26s linear infinite}"
    ".glow{animation:hue 26s linear infinite,breathe 2.6s ease-in-out infinite}"  # 2.6 s = the site's badge-glow
    # Light sweep across the panel, same 3.4 s rhythm as the site's .ask-badge shine.
    "@keyframes shine{0%{transform:translateX(-200px) skewX(-25deg)}55%,100%{transform:translateX(900px) skewX(-25deg)}}"
    ".shine{animation:shine 3.4s ease-in-out infinite}"
    ".edge.bad{animation:hue-bad .9s ease-in-out infinite}"
    ".glow.bad{animation:hue-bad .9s ease-in-out infinite,breathe-bad .9s ease-in-out infinite}"
    # Seven-segment digits ride the very same palette/phase as the border (fill instead of stroke).
    "@keyframes hue-fill{0%,100%{fill:hsl(30,90%,68%)}20%{fill:hsl(185,90%,68%)}"
    "40%{fill:hsl(220,90%,68%)}60%{fill:hsl(270,90%,68%)}80%{fill:hsl(335,90%,68%)}}"
    "@keyframes hue-fill-bad{0%,100%{fill:#f7768e}50%{fill:#e0af68}}"
    ".seg{animation:hue-fill 26s linear infinite}"
    ".seg.bad{animation:hue-fill-bad .9s ease-in-out infinite}"
    ".off{opacity:.09}"
)
PAD = 40  # room for the glow to fade out fully (halo reaches ~stroke/2 + 3*sigma = 38px), else a faint box shows

# ---- seven-segment ("LED calculator") digits, drawn as polygons: no font needed in an <img> SVG ----
SEG_W, SEG_H, SEG_T, SEG_GAP, SEG_ADV = 17.0, 28.0, 3.6, 0.9, 22.0
SEG_MAP = {"0": "abcdef", "1": "bc", "2": "abdeg", "3": "abcdg", "4": "bcfg",
           "5": "acdfg", "6": "acdefg", "7": "abc", "8": "abcdefg", "9": "abcdfg", "-": "g"}


def _hex(pts: List[Any], ox: float, oy: float) -> str:
    return " ".join(f"{ox + px:.2f},{oy + py:.2f}" for px, py in pts)


def _seg_polys() -> Dict[str, List[Any]]:
    w, h, t, g = SEG_W, SEG_H, SEG_T, SEG_GAP
    def horiz(yc: float) -> List[Any]:
        x0, x1 = t / 2 + g, w - t / 2 - g
        return [(x0, yc), (x0 + t / 2, yc - t / 2), (x1 - t / 2, yc - t / 2),
                (x1, yc), (x1 - t / 2, yc + t / 2), (x0 + t / 2, yc + t / 2)]
    def vert(xc: float, y0: float, y1: float) -> List[Any]:
        return [(xc, y0), (xc + t / 2, y0 + t / 2), (xc + t / 2, y1 - t / 2),
                (xc, y1), (xc - t / 2, y1 - t / 2), (xc - t / 2, y0 + t / 2)]
    up0, up1, lo0, lo1 = t / 2 + g, h / 2 - g, h / 2 + g, h - t / 2 - g
    return {"a": horiz(t / 2), "g": horiz(h / 2), "d": horiz(h - t / 2),
            "f": vert(t / 2, up0, up1), "b": vert(w - t / 2, up0, up1),
            "e": vert(t / 2, lo0, lo1), "c": vert(w - t / 2, lo0, lo1)}


def seven_seg(x: float, y: float, text: str, bad: bool) -> str:
    """Render `text` (digits, '-', '/') as a glowing LED readout whose top-left is (x, y).
    Unlit segments stay faintly visible ('ghost 8'), exactly like a real display."""
    polys, cls = _seg_polys(), "seg bad" if bad else "seg"
    out, cx = [], x
    for ch in text:
        if ch == "/":
            t, h = SEG_T, SEG_H
            out.append(f'<polygon class="{cls}" points="{_hex([(0, h), (t, h), (t + 8, 0), (8, 0)], cx + 1, y)}"/>')
            cx += 15
            continue
        lit = SEG_MAP.get(ch, "")
        for name, pts in polys.items():
            off = "" if name in lit else " off"
            out.append(f'<polygon class="{cls}{off}" points="{_hex(pts, cx, y)}"/>')
        cx += SEG_ADV
    return '<g filter="url(#segglow)">' + "".join(out) + "</g>"



def _stack(p: List[str], x: float, y: float, w: float, segs: List[Any], delay: float) -> None:
    """Stacked horizontal bar; segs = [(count, colour)]. Grows in from the left."""
    total = sum(c for c, _ in segs) or 1
    p.append(f'<rect x="{x}" y="{y}" width="{w}" height="8" rx="4" fill="{GRID}"/>')
    p.append(f'<g class="b" style="animation-delay:{delay}s"><clipPath id="c{int(x)}">'
             f'<rect x="{x}" y="{y}" width="{w}" height="8" rx="4"/></clipPath><g clip-path="url(#c{int(x)})">')
    cx = x
    for c, col in segs:
        sw = c / total * w
        p.append(f'<rect x="{cx:.1f}" y="{y}" width="{sw + 0.5:.1f}" height="8" fill="{col}"/>')
        cx += sw
    p.append("</g></g>")


def build_status_svg(repos: List[Dict[str, Any]], now: dt.datetime) -> str:
    own = [r for r in repos if not r["fork"]]
    ci = [r["ci"] for r in own]
    ok = sum(c == "SUCCESS" for c in ci)
    bad = sum(c in ("FAILURE", "ERROR") for c in ci)
    run = sum(c in ("PENDING", "EXPECTED") for c in ci)
    none = len(own) - ok - bad - run
    week = sum((now - r["pushed"]).days < 7 for r in own)
    stars = sum(r["stars"] for r in own)
    with_ci = len(own) - none
    forks = len(repos) - len(own)
    tiles = [(str(len(own)), f"own repos (+{forks} forks)" if forks else "own repos"),
             (str(week), "pushed this week"),
             (f"{ok}/{with_ci}" if with_ci else "—", "CI passing"), (str(stars), "stars")]
    alarm = bad > 0
    edge = f'x="1" y="1" width="{SW - 2}" height="{SH - 2}" rx="8"'
    bad_cls = " bad" if alarm else ""

    p = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{SW + 2 * PAD}" height="{SH + 2 * PAD}" '
         f'viewBox="0 0 {SW + 2 * PAD} {SH + 2 * PAD}" font-family="{FONT}"><style>{STATUS_CSS}</style>',
         '<defs><filter id="glow" x="-15%" y="-80%" width="130%" height="260%">'
         '<feGaussianBlur stdDeviation="6"/></filter>'
         '<filter id="segglow" x="-20%" y="-20%" width="140%" height="140%">'
         '<feGaussianBlur stdDeviation="1.5" result="b"/>'
         '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
         '<filter id="halo" x="-20%" y="-120%" width="140%" height="340%">'
         '<feGaussianBlur stdDeviation="10"/></filter>'
         '<linearGradient id="sheen" x1="0" y1="0" x2="1" y2="0">'
         '<stop offset="0" stop-color="#fff" stop-opacity="0"/>'
         '<stop offset="0.5" stop-color="#fff" stop-opacity="0.09"/>'
         '<stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
         f'<clipPath id="panel"><rect width="{SW}" height="{SH}" rx="8"/></clipPath></defs>',
         f'<g transform="translate({PAD} {PAD})">',
         f'<rect width="{SW}" height="{SH}" fill="{SURFACE}" rx="8"/>',
         f'<rect class="glow{bad_cls}" {edge} stroke-width="16" filter="url(#halo)"/>',   # wide outer halo
         f'<rect class="glow{bad_cls}" {edge} stroke-width="9" filter="url(#glow)"/>',    # tight bright glow
         f'<rect class="edge{bad_cls}" {edge} stroke-width="1.6"/>',
         f'<circle class="live" cx="22" cy="21" r="4" fill="{"#f7768e" if alarm else "#9ece6a"}"/>',
         f'<text x="34" y="25" font-size="11" font-weight="600" fill="{TEXT_PRIMARY}" letter-spacing="1.2">'
         f'REPO HEALTH · LIVE</text>',
         f'<text x="{SW - 16}" y="25" font-size="10" fill="{TEXT_MUTED}" text-anchor="end">'
         f'synced {now.strftime("%Y-%m-%d %H:%M")} UTC</text>']
    tw = (SW - 32) / len(tiles)
    for i, (num, label) in enumerate(tiles):
        x = 16 + i * tw
        p.append(f'<g class="t" style="animation-delay:{i * 0.12:.2f}s">'
                 + seven_seg(x, 38, num if num != "—" else "-", alarm) +
                 f'<text x="{x:.0f}" y="82" font-size="10.5" fill="{TEXT_MUTED}">{label}</text></g>')

    half = (SW - 48) / 2
    lx, rx = 16, 32 + half
    p.append(f'<text x="{lx}" y="104" font-size="9.5" fill="{TEXT_MUTED}" letter-spacing="1">CI HEALTH</text>')
    _stack(p, lx, 109, half, [(ok, CI_COLOR["SUCCESS"]), (run, CI_COLOR["PENDING"]),
                              (bad, CI_COLOR["FAILURE"]), (none, GRID)], 0.5)
    parts = [(ok, "passing"), (run, "running"), (bad, "failing"), (none, "no CI")]
    p.append(f'<text x="{lx}" y="138" font-size="10" fill="{TEXT_SOFT}">'
             + " · ".join(f"{c} {n}" for c, n in parts if c) + "</text>")

    counts: Dict[str, int] = {}
    colors: Dict[str, str] = {}
    for r in own:
        if r["lang"]:
            counts[r["lang"]] = counts.get(r["lang"], 0) + 1
            colors[r["lang"]] = r["lang_color"]
    top = sorted(counts, key=lambda k: -counts[k])[:4]
    segs = [(counts[k], colors[k]) for k in top]
    rest = sum(counts.values()) - sum(counts[k] for k in top)
    if rest:
        segs.append((rest, TEXT_MUTED))
    p.append(f'<text x="{rx}" y="104" font-size="9.5" fill="{TEXT_MUTED}" letter-spacing="1">LANGUAGES</text>')
    _stack(p, rx, 109, half, segs, 0.7)
    cx = rx
    for k in top:
        p.append(f'<circle cx="{cx + 4:.0f}" cy="135" r="3.5" fill="{colors[k]}"/>')
        label = f"{k} {counts[k]}"
        p.append(f'<text x="{cx + 12:.0f}" y="138" font-size="10" fill="{TEXT_SOFT}">{_esc(label)}</text>')
        cx += 24 + len(label) * 5.6
    p.append(f'<g clip-path="url(#panel)"><rect class="shine" x="0" y="-10" width="150" height="{SH + 20}" '
             f'fill="url(#sheen)"/></g>')
    p.append("</g></svg>")
    return "".join(p)


def write_status(repos: List[Dict[str, Any]], now: dt.datetime) -> str:
    svg = build_status_svg(repos, now)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "repo_status.svg").write_text(svg, encoding="utf-8")
    v = hashlib.md5(svg.encode()).hexdigest()[:8]  # cache-bust only when content changes
    return (f'<p align="center"><img src="{ASSET_BASE}/repo_status.svg?v={v}" width="{SW + 2 * PAD}" '
            f'alt="Repo health: repos, CI status and language mix"/></p>')


# ----------------------------------------------------------------- main ---
def replace_block(text: str, name: str, inner: str) -> str:
    pat = re.compile(rf"(<!-- {name}:START -->)(.*?)(<!-- {name}:END -->)", re.S)
    if not pat.search(text):
        raise SystemExit(f"README is missing the <!-- {name}:START/END --> markers")
    return pat.sub(lambda m: f"{m.group(1)}\n{inner}\n{m.group(3)}", text, count=1)


def main() -> None:
    if not TOKEN:
        raise SystemExit("GH_TOKEN or GITHUB_TOKEN env var is required")
    now = dt.datetime.now(dt.timezone.utc)
    repos = fetch_repos(LOGIN, TOKEN)

    md = README.read_text(encoding="utf-8")
    md = replace_block(md, "REPOS", build_board_md(repos, now, write_status(repos, now)))
    README.write_text(md, encoding="utf-8")
    print(f"[repo-board] {len(repos)} repos")


if __name__ == "__main__":
    main()
