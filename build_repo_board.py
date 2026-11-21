# build_repo_board.py
# -*- coding: utf-8 -*-
"""Self-hosted "Repo Health Board" for the profile README.

One GitHub GraphQL call (no per-repo REST calls, no third-party renderer)
produces:

  * a categorised, collapsible table of every public repo with language,
    CI status, last-push age and stars  -> README block REPOS
  * six featured-repo cards (self-drawn Tokyo Night SVGs, 3x2 grid)
                                         -> README block FEATURED + badges/

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
# Git ref the README images are served from; only overridden to preview a branch.
REF = os.getenv("REPO_BOARD_REF", "main")
RAW_BASE = f"https://raw.githubusercontent.com/{LOGIN}/{LOGIN}/{REF}/badges"

# The profile repo itself is the page you are reading - not listed.
EXCLUDE = {LOGIN}

# Featured cards (bottom of the README), in display order.
FEATURED = [
    "route-optimization-vrp",
    "agent-memory",
    "civics-sql-rag",
    "tableau-business-cases",
    "olist-e-commerce-analytics",
    "cv-logistics-mlops",
]

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


def build_board_md(repos: List[Dict[str, Any]], now: dt.datetime) -> str:
    ok = sum(r["ci"] == "SUCCESS" for r in repos)
    bad = sum(r["ci"] in ("FAILURE", "ERROR") for r in repos)
    pend = sum(r["ci"] in ("PENDING", "EXPECTED") for r in repos)
    none = len(repos) - ok - bad - pend
    stars = sum(r["stars"] for r in repos)
    lines = [
        f'<p align="center"><b>{len(repos)} public repos</b> · 🟢 {ok} passing · '
        f'🔴 {bad} failing · 🟡 {pend} running · ⚪ {none} no CI · ⭐ {stars} stars</p>',
        "",
    ]
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


# ---------------------------------------------------------- featured SVG ---
def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _wrap(text: str, width: int, max_lines: int) -> List[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + (1 if cur else 0) <= width:
            cur = f"{cur} {w}".strip()
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: width - 1].rstrip() + "…"
    return lines


def build_card_svg(r: Dict[str, Any], now: dt.datetime) -> str:
    w, h = 380, 132
    ci = r["ci"]
    ci_label = {"SUCCESS": "passing", "FAILURE": "failing", "ERROR": "failing",
                "PENDING": "running", "EXPECTED": "running"}.get(ci, "no CI")
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
         f'font-family="{FONT}">',
         f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="8" fill="{SURFACE}" stroke="{GRID}"/>',
         f'<text x="16" y="29" font-size="15" font-weight="700" fill="{ACCENT}">{_esc(r["name"])}</text>']
    for i, line in enumerate(_wrap(r["desc"] or "No description yet.", 56, 3)):
        p.append(f'<text x="16" y="{52 + i * 16}" font-size="11.5" fill="{TEXT_SOFT}">{_esc(line)}</text>')
    y = h - 16
    p.append(f'<circle cx="21" cy="{y - 4}" r="5" fill="{r["lang_color"]}"/>')
    p.append(f'<text x="31" y="{y}" font-size="11" fill="{TEXT_MUTED}">{_esc(r["lang"] or "—")}</text>')
    p.append(f'<text x="118" y="{y}" font-size="11" fill="{TEXT_MUTED}">★ {r["stars"]}</text>')
    p.append(f'<circle cx="168" cy="{y - 4}" r="4" fill="{CI_COLOR.get(ci, TEXT_MUTED)}"/>')
    p.append(f'<text x="177" y="{y}" font-size="11" fill="{TEXT_MUTED}">{ci_label}</text>')
    p.append(f'<text x="{w - 16}" y="{y}" font-size="11" fill="{TEXT_MUTED}" text-anchor="end">'
             f'updated {age(r["pushed"], now)}</text>')
    p.append("</svg>")
    return "".join(p)


def write_featured(repos: List[Dict[str, Any]], now: dt.datetime) -> str:
    by_name = {r["name"]: r for r in repos}
    cells = []
    for i, name in enumerate(FEATURED, 1):
        r = by_name.get(name)
        if r is None:
            raise SystemExit(f"featured repo not found: {name}")
        svg = build_card_svg(r, now)
        path = OUT_DIR / f"featured_{i}.svg"
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(svg, encoding="utf-8")
        v = hashlib.md5(svg.encode()).hexdigest()[:8]  # cache-bust only when content changes
        cells.append(f'<td><a href="{r["url"]}"><img src="{RAW_BASE}/featured_{i}.svg?v={v}" '
                     f'width="380" alt="{_esc(name)}"/></a></td>')
    rows = ["<tr>" + "".join(cells[i:i + 3]) + "</tr>" for i in range(0, len(cells), 3)]
    return ('<h3 align="center">⭐ Featured repositories</h3>\n'
            '<table align="center">\n' + "\n".join(rows) + "\n</table>")


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
    md = replace_block(md, "REPOS", build_board_md(repos, now))
    md = replace_block(md, "FEATURED", write_featured(repos, now))
    README.write_text(md, encoding="utf-8")
    print(f"[repo-board] {len(repos)} repos, {len(FEATURED)} featured cards")


if __name__ == "__main__":
    main()
