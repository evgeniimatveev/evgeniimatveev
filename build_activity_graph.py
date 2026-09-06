# build_activity_graph.py
# -*- coding: utf-8 -*-
"""Self-hosted replacement for github-readme-activity-graph.vercel.app.

That widget drew a 30-day daily-commits line/area chart — a different view
from GitHub's own native contribution calendar (which the profile already
shows further down the page, so duplicating it here would be redundant).
This fetches the same 30-day window straight from GitHub's own GraphQL API
and renders the line/area chart locally — no third-party renderer to fail.
"""

from __future__ import annotations

import os
import json
import datetime as dt
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Dict, List, Tuple

LOGIN = os.getenv("ACTIVITY_GRAPH_LOGIN", "evgeniimatveev")
TOKEN = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
OUT_PATH = Path(os.getenv("ACTIVITY_GRAPH_OUT", "badges/activity_graph.svg"))
WINDOW_DAYS = int(os.getenv("ACTIVITY_GRAPH_WINDOW_DAYS", "30"))

# Tokyo Night palette — matches the theme already used by the trophies /
# streak-stats / summary-cards widgets on the same profile page.
SURFACE = "#1a1b26"
GRID = "#2a2e42"
TEXT_PRIMARY = "#c0caf5"
TEXT_MUTED = "#565f89"
ACCENT = "#7aa2f7"
ACCENT_FILL_TOP = "rgba(122,162,247,0.35)"
ACCENT_FILL_BOTTOM = "rgba(122,162,247,0.0)"

WIDTH = 784
HEIGHT = 220
PAD_LEFT = 34
PAD_RIGHT = 16
PAD_TOP = 40
PAD_BOTTOM = 42
PLOT_W = WIDTH - PAD_LEFT - PAD_RIGHT
PLOT_H = HEIGHT - PAD_TOP - PAD_BOTTOM

MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def fetch_daily_counts(login: str, token: str, window_days: int) -> Tuple[List[Dict[str, Any]], int]:
    """Query the last `window_days` of contributionCalendar via GitHub GraphQL."""
    to = dt.datetime.now(dt.timezone.utc)
    frm = to - dt.timedelta(days=window_days - 1)

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
    days = [d for week in calendar["weeks"] for d in week["contributionDays"]]
    days = [d for d in days if frm.date() <= dt.date.fromisoformat(d["date"]) <= to.date()]
    total = sum(d["contributionCount"] for d in days)
    return days, total


def _catmull_rom_to_bezier_path(points: List[Tuple[float, float]]) -> str:
    """Smooth line through points using Catmull-Rom -> cubic Bezier conversion."""
    if len(points) < 2:
        return ""
    path = [f"M {points[0][0]:.1f} {points[0][1]:.1f}"]
    for i in range(len(points) - 1):
        p0 = points[i - 1] if i > 0 else points[i]
        p1 = points[i]
        p2 = points[i + 1]
        p3 = points[i + 2] if i + 2 < len(points) else p2
        c1x = p1[0] + (p2[0] - p0[0]) / 6
        c1y = p1[1] + (p2[1] - p0[1]) / 6
        c2x = p2[0] - (p3[0] - p1[0]) / 6
        c2y = p2[1] - (p3[1] - p1[1]) / 6
        path.append(f"C {c1x:.1f} {c1y:.1f} {c2x:.1f} {c2y:.1f} {p2[0]:.1f} {p2[1]:.1f}")
    return " ".join(path)


def build_svg(days: List[Dict[str, Any]], total: int, login: str, window_days: int) -> str:
    n = len(days)
    counts = [d["contributionCount"] for d in days]
    max_count = max(counts) if counts else 0
    y_max = max(max_count, 1) * 1.2

    def x_at(i: int) -> float:
        if n == 1:
            return PAD_LEFT + PLOT_W / 2
        return PAD_LEFT + (PLOT_W * i / (n - 1))

    def y_at(count: int) -> float:
        return PAD_TOP + PLOT_H - (count / y_max) * PLOT_H

    points = [(x_at(i), y_at(c)) for i, c in enumerate(counts)]
    baseline_y = PAD_TOP + PLOT_H

    parts: List[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" font-family="-apple-system,BlinkMacSystemFont,'
        f'\'Segoe UI\',Helvetica,Arial,sans-serif">'
    )
    parts.append("<defs><linearGradient id=\"areaFill\" x1=\"0\" y1=\"0\" x2=\"0\" y2=\"1\">"
                  f'<stop offset="0%" stop-color="{ACCENT_FILL_TOP}"/>'
                  f'<stop offset="100%" stop-color="{ACCENT_FILL_BOTTOM}"/>'
                  "</linearGradient></defs>")
    parts.append(f'<rect width="{WIDTH}" height="{HEIGHT}" fill="{SURFACE}" rx="6"/>')
    parts.append(
        f'<text x="{PAD_LEFT}" y="16" font-size="13" font-weight="600" fill="{TEXT_PRIMARY}">'
        f'{total} contributions in the last {window_days} days</text>'
    )

    # Horizontal gridlines + y labels (0 / mid / max).
    for frac, label in ((0.0, "0"), (0.5, str(round(y_max / 2))), (1.0, str(round(y_max)))):
        gy = PAD_TOP + PLOT_H - frac * PLOT_H
        parts.append(f'<line x1="{PAD_LEFT}" y1="{gy:.1f}" x2="{WIDTH - PAD_RIGHT}" y2="{gy:.1f}" '
                      f'stroke="{GRID}" stroke-width="1"/>')
        parts.append(f'<text x="{PAD_LEFT - 6}" y="{gy + 3:.1f}" font-size="9" fill="{TEXT_MUTED}" '
                      f'text-anchor="end">{label}</text>')

    # Area fill + smoothed line.
    line_path = _catmull_rom_to_bezier_path(points)
    if line_path:
        area_path = (
            f"{line_path} L {points[-1][0]:.1f} {baseline_y:.1f} "
            f"L {points[0][0]:.1f} {baseline_y:.1f} Z"
        )
        parts.append(f'<path d="{area_path}" fill="url(#areaFill)" stroke="none"/>')
        parts.append(f'<path d="{line_path}" fill="none" stroke="{ACCENT}" stroke-width="2" '
                      f'stroke-linecap="round" stroke-linejoin="round"/>')

    # Dots — every point gets a small marker; the peak day gets a bigger one + label.
    peak_i = max(range(n), key=lambda i: counts[i]) if n else 0
    for i, (px, py) in enumerate(points):
        is_peak = i == peak_i and counts[i] > 0
        r = 4 if is_peak else 2.5
        parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{r}" fill="{ACCENT}"/>')
        if is_peak:
            parts.append(f'<text x="{px:.1f}" y="{py - 8:.1f}" font-size="9" fill="{TEXT_PRIMARY}" '
                          f'text-anchor="middle" font-weight="600">{counts[i]}</text>')

    # X-axis date labels — first, last, and every ~5th day in between.
    label_stride = max(1, n // 6)
    for i, d in enumerate(days):
        if i != 0 and i != n - 1 and i % label_stride != 0:
            continue
        date = dt.date.fromisoformat(d["date"])
        label = f"{MONTH_ABBR[date.month - 1]} {date.day}"
        anchor = "start" if i == 0 else "end" if i == n - 1 else "middle"
        parts.append(f'<text x="{points[i][0]:.1f}" y="{HEIGHT - PAD_BOTTOM + 12}" font-size="9" '
                      f'fill="{TEXT_MUTED}" text-anchor="{anchor}">{label}</text>')

    parts.append(
        f'<text x="{PAD_LEFT}" y="{HEIGHT - 6}" font-size="9" fill="{TEXT_MUTED}">'
        f'@{login} &#183; self-hosted, updates daily</text>'
    )

    parts.append("</svg>")
    return "".join(parts)


def main() -> None:
    if not TOKEN:
        raise SystemExit("GH_TOKEN or GITHUB_TOKEN env var is required")

    days, total = fetch_daily_counts(LOGIN, TOKEN, WINDOW_DAYS)
    svg = build_svg(days, total, LOGIN, WINDOW_DAYS)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(svg, encoding="utf-8")
    print(f"[activity-graph] wrote {OUT_PATH} ({len(days)} days, {total} total contributions)")


if __name__ == "__main__":
    main()
