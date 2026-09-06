# build_activity_graph.py
# -*- coding: utf-8 -*-
"""Self-hosted replacement for github-readme-activity-graph.vercel.app.

Fetches the last 365 days of contribution data straight from GitHub's own
GraphQL API and renders a calendar-heatmap SVG locally — no third-party
rendering service, so there is nothing external to go down.
"""

from __future__ import annotations

import os
import json
import datetime as dt
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Dict, List

LOGIN = os.getenv("ACTIVITY_GRAPH_LOGIN", "evgeniimatveev")
TOKEN = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
OUT_PATH = Path(os.getenv("ACTIVITY_GRAPH_OUT", "badges/activity_graph.svg"))

# Sequential ramp: one hue (brand blue), light->dark, monotone lightness.
# Level 0 = GitHub's own "no contributions" dark tone so it blends with the
# surrounding dark-mode card instead of looking like a hole.
LEVEL_COLORS = ["#161b22", "#0d3a66", "#155a99", "#1f7ecc", "#3fa9f5"]
SURFACE = "#0d1117"
TEXT_PRIMARY = "#c9d1d9"
TEXT_MUTED = "#8b949e"

CELL = 11
GAP = 3
STEP = CELL + GAP
LEFT_MARGIN = 28
TOP_MARGIN = 34
BOTTOM_MARGIN = 30
RIGHT_MARGIN = 14

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
WEEKDAY_LABELS = {1: "Mon", 3: "Wed", 5: "Fri"}  # Monday=0 .. Sunday=6


def fetch_contribution_days(login: str, token: str) -> List[Dict[str, Any]]:
    """Query the last 365 days of contributionCalendar via GitHub GraphQL."""
    to = dt.datetime.now(dt.timezone.utc)
    frm = to - dt.timedelta(days=365)

    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                date
                contributionCount
              }
            }
          }
        }
      }
    }
    """
    body = json.dumps({
        "query": query,
        "variables": {
            "login": login,
            "from": frm.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to": to.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "activity-graph-builder",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    if "errors" in payload:
        raise RuntimeError(f"GraphQL error: {payload['errors']}")

    calendar = payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    weeks = calendar["weeks"]
    total = calendar["totalContributions"]
    days = [d for week in weeks for d in week["contributionDays"]]
    return days, total


def levels_for(days: List[Dict[str, Any]]):
    """Fixed log-scale buckets (not quantiles): this profile's daily counts are
    heavily skewed (many single-commit days, occasional 100+ commit bursts from
    project pushes), so a quantile split collapses into "1 vs everything else".
    """

    def level(count: int) -> int:
        if count <= 0:
            return 0
        if count == 1:
            return 1
        if count <= 4:
            return 2
        if count <= 14:
            return 3
        return 4

    return level


def build_svg(days: List[Dict[str, Any]], total: int, login: str) -> str:
    level_fn = levels_for(days)

    # Group into weeks (Sunday-start columns, matching GitHub's own layout).
    weeks: List[List[Dict[str, Any]]] = []
    current_week: List[Dict[str, Any]] = []
    for d in days:
        date = dt.date.fromisoformat(d["date"])
        weekday = (date.weekday() + 1) % 7  # Sunday=0 .. Saturday=6
        if weekday == 0 and current_week:
            weeks.append(current_week)
            current_week = []
        current_week.append(d)
    if current_week:
        weeks.append(current_week)

    n_weeks = len(weeks)
    width = LEFT_MARGIN + n_weeks * STEP + RIGHT_MARGIN
    height = TOP_MARGIN + 7 * STEP + BOTTOM_MARGIN

    parts: List[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="-apple-system,BlinkMacSystemFont,'
        f'\'Segoe UI\',Helvetica,Arial,sans-serif">'
    )
    parts.append(f'<rect width="{width}" height="{height}" fill="{SURFACE}" rx="6"/>')
    parts.append(
        f'<text x="{LEFT_MARGIN}" y="16" font-size="13" font-weight="600" '
        f'fill="{TEXT_PRIMARY}">{total:,} contributions in the last year</text>'
    )

    # Month labels: emit a label the first time a week starts a new month.
    seen_month = None
    for wi, week in enumerate(weeks):
        first_day = dt.date.fromisoformat(week[0]["date"])
        if first_day.month != seen_month:
            seen_month = first_day.month
            x = LEFT_MARGIN + wi * STEP
            parts.append(
                f'<text x="{x}" y="{TOP_MARGIN - 6}" font-size="10" '
                f'fill="{TEXT_MUTED}">{MONTH_NAMES[first_day.month - 1]}</text>'
            )

    # Weekday labels.
    for wd, label in WEEKDAY_LABELS.items():
        y = TOP_MARGIN + wd * STEP + CELL - 2
        parts.append(f'<text x="0" y="{y}" font-size="9" fill="{TEXT_MUTED}">{label}</text>')

    # Day cells.
    for wi, week in enumerate(weeks):
        for d in week:
            date = dt.date.fromisoformat(d["date"])
            weekday = (date.weekday() + 1) % 7
            count = d["contributionCount"]
            level = level_fn(count)
            x = LEFT_MARGIN + wi * STEP
            y = TOP_MARGIN + weekday * STEP
            color = LEVEL_COLORS[level]
            parts.append(
                f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2" '
                f'fill="{color}"><title>{count} contribution{"s" if count != 1 else ""} '
                f'on {d["date"]}</title></rect>'
            )

    # Legend (bottom-right): Less [] [] [] [] [] More
    legend_y = height - 12
    legend_label_w = 30
    swatch_x = width - RIGHT_MARGIN - legend_label_w - len(LEVEL_COLORS) * STEP
    parts.append(
        f'<text x="{swatch_x - 6}" y="{legend_y - 2}" font-size="9" fill="{TEXT_MUTED}" '
        f'text-anchor="end">Less</text>'
    )
    for i, color in enumerate(LEVEL_COLORS):
        x = swatch_x + i * STEP
        parts.append(f'<rect x="{x}" y="{legend_y - 10}" width="{CELL}" height="{CELL}" rx="2" fill="{color}"/>')
    more_x = swatch_x + len(LEVEL_COLORS) * STEP + 4
    parts.append(f'<text x="{more_x}" y="{legend_y - 2}" font-size="9" fill="{TEXT_MUTED}">More</text>')

    parts.append(
        f'<text x="{LEFT_MARGIN}" y="{legend_y - 2}" font-size="9" fill="{TEXT_MUTED}">'
        f'@{login} &#183; self-hosted, updates daily</text>'
    )

    parts.append("</svg>")
    return "".join(parts)


def main() -> None:
    if not TOKEN:
        raise SystemExit("GH_TOKEN or GITHUB_TOKEN env var is required")

    days, total = fetch_contribution_days(LOGIN, TOKEN)
    svg = build_svg(days, total, LOGIN)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(svg, encoding="utf-8")
    print(f"[activity-graph] wrote {OUT_PATH} ({len(days)} days, {total} total contributions)")


if __name__ == "__main__":
    main()
