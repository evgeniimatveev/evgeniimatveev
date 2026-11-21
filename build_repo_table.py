# build_repo_table.py
# -*- coding: utf-8 -*-
"""Self-updating colour-coded table of every public repo on the profile.

GitHub strips CSS/bgcolor from README tables, so colour is carried by
emoji squares inside the cells (category, language, freshness). Everything
is plain markdown: clickable links, no third-party renderer to go down.

Rewrites the block between <!-- REPOS:START --> and <!-- REPOS:END -->.
New repos appear automatically on the next run; unknown names fall back to
the "Other" category (or "Learning" if they end in -A-Z).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

LOGIN = os.getenv("REPO_TABLE_LOGIN", "evgeniimatveev")
TOKEN = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
README = Path(os.getenv("REPO_TABLE_README", "README.md"))

START, END = "<!-- REPOS:START -->", "<!-- REPOS:END -->"

# Third-party widget copies / forks used only to power the profile page.
EXCLUDE = {
    "snk",
    "github-profile-trophy",
    "github-readme-streak-stats",
    "github-profile-summary-cards",
}

# (emoji, label) in display order.
CATEGORIES = {
    "analytics": ("🟧", "Analytics & BI"),
    "mlops": ("🟩", "MLOps & AI"),
    "pipelines": ("🟨", "Data Pipelines"),
    "learning": ("🟦", "Learning A-Z"),
    "profile": ("🟪", "Profile & Site"),
    "other": ("⬜", "Other"),
}

CATEGORY_OF = {
    # Analytics & BI
    "olist-e-commerce-analytics": "analytics",
    "uber-driver-analytics": "analytics",
    "so-survey-analytics": "analytics",
    "layoffs-tracker": "analytics",
    "crypto-dashboard": "analytics",
    "business-sql-analytics": "analytics",
    "hr-bi-analytics-project": "analytics",
    "nyc-311-duckdb-motherduck-analysis": "analytics",
    "tableau-business-cases": "analytics",
    "remote-job-tracker": "analytics",
    # MLOps & AI
    "cv-logistics-mlops": "mlops",
    "route-optimization-vrp": "mlops",
    "agent-memory": "mlops",
    "civics-sql-rag": "mlops",
    "mcp-data-quality-agent": "mlops",
    "interview-coach": "mlops",
    "mlops_project": "mlops",
    "mlops_ollama_env": "mlops",
    # Data pipelines
    "weather-pipeline": "pipelines",
    "job-market-pulse": "pipelines",
    "data-pipeline-etl-project": "pipelines",
    # Learning
    "EXCEL-A-Z": "learning",
    "Power-BI-A-Z": "learning",
    "SQL-Database-Design-A-Z": "learning",
    "Advanced-SQL-Data-Management-A-Z": "learning",
    "Snowflake-A-Z": "learning",
    "ML-Classics-in-Python": "learning",
    "ML-Classics-in-R": "learning",
    "Ml-Classics-Level2-Boosting": "learning",
    "Advanced-R-for-Analytics": "learning",
    "Python-for-Data-Science-A-Z": "learning",
    "Feature-Engineering": "learning",
    "Python-Programming-A-Z": "learning",
    "R-Programming-A-Z": "learning",
    "Python-Projects": "learning",
    # Profile & site
    "evgeniimatveev": "profile",
    "evgeniimatveev.github.io": "profile",
}

LANG_EMOJI = {
    "Python": "🟦",
    "Jupyter Notebook": "🟧",
    "R": "🟪",
    "SQL": "🟨",
    "PLpgSQL": "🟨",
    "TSQL": "🟨",
    "JavaScript": "🟥",
    "TypeScript": "🟥",
    "HTML": "🟥",
    "CSS": "🟥",
    "Shell": "⬜",
    "Dockerfile": "⬜",
}


def category_key(name: str) -> str:
    if name in CATEGORY_OF:
        return CATEGORY_OF[name]
    return "learning" if name.lower().endswith("-a-z") else "other"


def freshness(pushed_at: str, today: dt.date) -> str:
    days = (today - dt.date.fromisoformat(pushed_at[:10])).days
    if days <= 7:
        return "🟢"
    if days <= 30:
        return "🟡"
    if days <= 90:
        return "🟠"
    return "🔴"


def fetch_repos() -> List[Dict[str, Any]]:
    repos: List[Dict[str, Any]] = []
    page = 1
    while True:
        url = (
            f"https://api.github.com/users/{LOGIN}/repos"
            f"?per_page=100&type=owner&page={page}"
        )
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
        if TOKEN:
            req.add_header("Authorization", f"Bearer {TOKEN}")
        with urllib.request.urlopen(req, timeout=30) as resp:
            batch = json.load(resp)
        repos.extend(batch)
        if len(batch) < 100:
            return repos
        page += 1


def short(text: str | None, limit: int = 70) -> str:
    text = (text or "").replace("|", "/").replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def render(repos: List[Dict[str, Any]], today: dt.date) -> str:
    rows = [r for r in repos if r["name"] not in EXCLUDE and not r.get("archived")]
    order = list(CATEGORIES)
    # stable two-pass sort: newest first, then grouped by category order
    rows.sort(key=lambda r: r["pushed_at"], reverse=True)
    rows.sort(key=lambda r: order.index(category_key(r["name"])))

    counts: Dict[str, int] = {}
    for r in rows:
        counts[category_key(r["name"])] = counts.get(category_key(r["name"]), 0) + 1
    legend = " · ".join(
        f"{CATEGORIES[k][0]} {CATEGORIES[k][1]} ({counts[k]})" for k in order if k in counts
    )

    lines = [
        f"<p align=\"center\"><b>{len(rows)} repositories</b> — auto-generated daily from the GitHub API</p>",
        "",
        "| Repository | Category | Language | Updated | About |",
        "|:--|:--|:--|:--|:--|",
    ]
    for r in rows:
        emoji, label = CATEGORIES[category_key(r["name"])]
        lang = r.get("language")
        lang_cell = f"{LANG_EMOJI.get(lang, '⬜')} {lang}" if lang else "⬜ —"
        updated = f"{freshness(r['pushed_at'], today)} {r['pushed_at'][:10]}"
        lines.append(
            f"| [**{r['name']}**]({r['html_url']}) | {emoji} {label} | {lang_cell} "
            f"| {updated} | {short(r.get('description'))} |"
        )
    lines += [
        "",
        f"<sub>{legend}</sub><br>",
        "<sub>Updated: 🟢 ≤ 7 days · 🟡 ≤ 30 days · 🟠 ≤ 90 days · 🔴 older</sub>",
    ]
    return "\n".join(lines)


def inject(readme_text: str, block: str) -> str:
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    if not pattern.search(readme_text):
        raise SystemExit(f"Markers {START} / {END} not found in README")
    return pattern.sub(lambda _m: f"{START}\n{block}\n{END}", readme_text, count=1)


def main() -> None:
    today = dt.datetime.now(dt.timezone.utc).date()
    block = render(fetch_repos(), today)
    old = README.read_text(encoding="utf-8")
    new = inject(old, block)
    if new != old:
        README.write_text(new, encoding="utf-8")
        print("README repo table updated")
    else:
        print("No changes")


if __name__ == "__main__":
    main()
