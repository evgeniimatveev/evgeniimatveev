#!/usr/bin/env python3
"""build_ci_stats.py — self-updating CI/CD table for the profile README.

Single sources of truth (nothing is typed by hand):
  * workflow list + cumulative run numbers  -> GitHub REST API (stdlib urllib)
  * schedules / triggers                    -> the cron / push / pull_request lines of .github/workflows/*.yml
  * "README mutations" counter              -> .ci/update_count.txt

Rewrites two README spots (both are no-ops if the content is unchanged):
  <!-- CISTATS:START --> ... <!-- CISTATS:END -->   the workflows table
  <!-- CIHEAD:START -->  ... <!-- CIHEAD:END -->    inline "N+ cumulative workflow runs · M+ README mutations"

Env: GH_TOKEN / GITHUB_TOKEN (actions:read), GITHUB_REPOSITORY (default evgeniimatveev/evgeniimatveev).
Run from the repo root:  python build_ci_stats.py [--dry-run]
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

REPO = os.environ.get("GITHUB_REPOSITORY", "evgeniimatveev/evgeniimatveev")
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
WF_DIR = Path(".github/workflows")
README = Path("README.md")
COUNT_FILE = Path(".ci/update_count.txt")

# Display names + order. Unknown workflows still appear (title-cased file name, after these).
NAMES = {
    "update_readme": "Auto Update README",
    "next_update_badge": "Next Update Badge",
    "blank": "CI/CD Pipeline",
    "smoke": "Smoke Tests",
    "cache_trophies": "Cache GitHub Trophies",
    "snake": "Generate Snake",
    "badges_extra": "Extra Badges",
    "activity_graph": "Activity Graph",
    "repo_board": "Repo Board",
    "codeql": "CodeQL",
}
ORDER = list(NAMES)
DOW = {"0": "Sun", "1": "Mon", "2": "Tue", "3": "Wed", "4": "Thu", "5": "Fri", "6": "Sat", "7": "Sun"}


# ───────────────────────── GitHub API ─────────────────────────
def api(path: str):
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/{path}",
        headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "profile-ci-stats"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def latest_run_number(workflow_id: int) -> int:
    runs = api(f"actions/workflows/{workflow_id}/runs?per_page=1")["workflow_runs"]
    return int(runs[0]["run_number"]) if runs else 0


# ───────────────────────── schedule parsing ─────────────────────────
def _hhmm(h: int, m: int) -> str:
    return f"{h:02d}:{m:02d}"


def parse_crons(text: str) -> list[tuple[str, str, str]]:
    """Return [(minute, hour, dow)] for every `cron:` line (comments stripped)."""
    out = []
    for m in re.finditer(r"""^\s*-\s*cron:\s*['"]([^'"]+)['"]""", text, re.M):
        parts = m.group(1).split()
        if len(parts) == 5 and parts[2] == "*" and parts[3] == "*":
            out.append((parts[0], parts[1], parts[4]))
    return out


def humanize(crons: list[tuple[str, str, str]]) -> str:
    # A daily slot makes a weekly slot at the very same time redundant (smoke.yml lists both).
    daily = {(m, h) for m, h, d in crons if d == "*"}
    uniq = []
    for c in crons:
        if c[2] != "*" and (c[0], c[1]) in daily:
            continue
        if c not in uniq:
            uniq.append(c)
    parts = []
    for m, h, d in uniq:
        if not m.isdigit():
            parts.append(f"cron {m} {h} * * {d}")
            continue
        mi = int(m)
        if h == "*":
            parts.append(f"Hourly (:{mi:02d})")
            continue
        hours = [int(x) for x in h.split(",")] if re.fullmatch(r"\d+(,\d+)*", h) else None
        if hours is None:
            parts.append(f"cron {m} {h} * * {d}")
            continue
        step = hours[1] - hours[0] if len(hours) > 1 else 0
        # "Every Nh" only for 3+ evenly spaced slots; two slots (05:15 & 17:15) read better as explicit times
        even = step > 0 and len(hours) >= 3 and 24 % step == 0 and len(hours) == 24 // step and \
            all(b - a == step for a, b in zip(hours, hours[1:]))
        if d == "*":
            if even and mi == 0:
                parts.append(f"Every {step}h")
            elif even:
                parts.append(f"Every {step}h (:{mi:02d})")
            else:
                parts.append("Daily " + " & ".join(_hhmm(x, mi) for x in hours) + " UTC")
        else:
            days = "/".join(DOW.get(x, x) for x in d.split(","))
            parts.append(f"{days} " + " & ".join(_hhmm(x, mi) for x in hours) + " UTC")
    return parts_to_text(parts)


def parse_schedule(text: str) -> str:
    crons = parse_crons(text)
    sched = humanize(crons) if crons else ""
    event = bool(re.search(r"^\s{2}(push|pull_request):", text, re.M))
    if event and sched:
        return f"On push/PR · {sched}"
    if event:
        return "On push/PR"
    return sched or "Manual"


def parts_to_text(parts: list[str]) -> str:
    # "Daily 06:45" already carries UTC only when it is a daily slot; keep a uniform "... UTC" suffix.
    out = []
    for p in parts:
        if re.fullmatch(r"Daily \d\d:\d\d", p):
            p += " UTC"
        out.append(p)
    return " + ".join(out)


# ───────────────────────── build ─────────────────────────
def collect():
    listing = api("actions/workflows?per_page=100")["workflows"]
    rows, total = [], 0
    for w in listing:
        if w.get("state") != "active":
            continue
        n = latest_run_number(w["id"])
        total += n
        path = w["path"]
        if not path.startswith(".github/workflows/"):  # dynamic (dependabot): counted in the total only
            continue
        stem = Path(path).stem
        f = WF_DIR / Path(path).name
        sched = parse_schedule(f.read_text(encoding="utf-8")) if f.exists() else "—"
        rows.append((stem, Path(path).name, sched, n))
    rows.sort(key=lambda r: (ORDER.index(r[0]) if r[0] in ORDER else len(ORDER), r[0]))
    return rows, total


def table_md(rows) -> str:
    base = f"https://github.com/{REPO}/actions/workflows"
    lines = ["| Workflow | Schedule | Runs¹ | Status |", "|----------|----------|------|--------|"]
    for stem, fname, sched, n in rows:
        name = NAMES.get(stem, stem.replace("_", " ").title())
        runs = f"**{n:,}**" if n else "**new**"
        lines.append(f'| <a href="{base}/{fname}">{name}</a> | {sched} | {runs} | '
                     f'<img alt="status" src="{base}/{fname}/badge.svg"> |')
    return "\n".join(lines)


def head_text(total: int) -> str:
    text = f"{total // 500 * 500:,}+ cumulative workflow runs"
    if COUNT_FILE.exists():
        try:
            mut = int(COUNT_FILE.read_text().strip())
            text += f" · {mut // 10 * 10}+ README mutations"
        except ValueError:
            pass
    return text


def sub_block(text: str, name: str, inner: str, inline: bool) -> str:
    pat = re.compile(rf"(<!-- {name}:START -->)(.*?)(<!-- {name}:END -->)", re.S)
    if not pat.search(text):
        raise SystemExit(f"README is missing the <!-- {name}:START/END --> markers")
    body = inner if inline else f"\n{inner}\n"
    return pat.sub(lambda m: f"{m.group(1)}{body}{m.group(3)}", text, count=1)


def main() -> None:
    dry = "--dry-run" in sys.argv
    if not TOKEN:
        raise SystemExit("GH_TOKEN or GITHUB_TOKEN env var is required")
    rows, total = collect()
    if len(rows) < 5:  # sanity: never replace the table with an empty/partial API answer
        raise SystemExit(f"only {len(rows)} workflows returned — refusing to rewrite README")
    md = README.read_text(encoding="utf-8")
    new = sub_block(md, "CISTATS", table_md(rows), inline=False)
    new = sub_block(new, "CIHEAD", head_text(total), inline=True)
    print(f"[ci-stats] {len(rows)} workflows · cumulative total {total:,} · {head_text(total)}")
    for r in rows:
        print(f"  {r[1]:<24} {r[2]:<34} {r[3]:>6,}")
    if dry:
        print("[ci-stats] dry run — README untouched")
        return
    if new != md:
        README.write_text(new, encoding="utf-8", newline="\n")
        print("[ci-stats] README updated")
    else:
        print("[ci-stats] no change")


if __name__ == "__main__":
    main()
