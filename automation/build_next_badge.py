# automation/build_next_badge.py
# -*- coding: utf-8 -*-
"""
Builds a dynamic Shields.io 'endpoint' JSON badge showing the time left until
the next scheduled README update (e.g., 12:15 UTC daily).
"""

from __future__ import annotations
import os, json, datetime as dt
from pathlib import Path

# Configuration via environment
CRON_HOUR   = int(os.getenv("NEXT_UPDATE_HOUR", "12"))
CRON_MINUTE = int(os.getenv("NEXT_UPDATE_MIN",  "15"))
JITTER_MAX_SEC = int(os.getenv("JITTER_MAX_SEC", "1800"))  # show "~" if jitter active

LABEL        = os.getenv("NEXT_BADGE_LABEL", "Next Update")
LABEL_COLOR  = os.getenv("NEXT_BADGE_LABEL_COLOR", "2e2e2e")
LOGO         = os.getenv("NEXT_BADGE_LOGO", "timer")
OUT_PATH     = Path("badges/next_update.json")

# Color thresholds by minutes left
THRESHOLDS = [
    (5,   "red"),
    (15,  "orange"),
    (60,  "yellow"),
    (240, "yellowgreen"),
    (1440, "brightgreen"),
]
DEFAULT_COLOR = "lightgrey"

def _next_eta(now: dt.datetime) -> dt.datetime:
    target = now.replace(hour=CRON_HOUR, minute=CRON_MINUTE, second=0, microsecond=0)
    if target <= now:
        target += dt.timedelta(days=1)
    return target

def _fmt(td: dt.timedelta) -> str:
    total = int(td.total_seconds())
    if total < 0: total = 0
    h, rem = divmod(total, 3600)
    m, _ = divmod(rem, 60)
    return f"{h}h {m:02d}m" if h > 0 else f"{m}m"

def _color_for_minutes(mins: int) -> str:
    for limit, color in THRESHOLDS:
        if mins <= limit:
            return color
    return DEFAULT_COLOR

def main():
    now = dt.datetime.utcnow()
    eta = _next_eta(now)
    delta = eta - now
    mins = int(delta.total_seconds() // 60)
    approx = JITTER_MAX_SEC > 0
    emoji = "⚡" if mins <= 5 else "⌛" if mins <= 30 else "⏳"
    msg = f"{emoji} {'~' if approx else ''}{_fmt(delta)}"
    badge = {
        "schemaVersion": 1,
        "label": LABEL,
        "message": msg,
        "color": _color_for_minutes(mins),
        "labelColor": LABEL_COLOR,
        "logo": LOGO,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(badge, ensure_ascii=False), encoding="utf-8")
    print(f"[build_next_badge] wrote {OUT_PATH} → {badge}")

if __name__ == "__main__":
    main()
