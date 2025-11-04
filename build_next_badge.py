# automation/build_next_badge.py
# -*- coding: utf-8 -*-
"""
Builds a dynamic Shields "endpoint" badge JSON that shows time left
until the next scheduled README update (e.g., 12:15 UTC daily).
- Color and emoji depend on minutes left
- Adds "~" prefix when schedule uses jitter (approximate)
- Writes to badges/next_update.json and only commits if changed
"""

from __future__ import annotations
import os
import json
import datetime as dt
from pathlib import Path

# ---- Configuration via ENV (with sensible defaults) -------------------------

# Next planned schedule (keep in sync with the main update workflow cron)
CRON_HOUR   = int(os.getenv("NEXT_UPDATE_HOUR", "12"))
CRON_MINUTE = int(os.getenv("NEXT_UPDATE_MIN",  "15"))

# If your main workflow has random jitter (in seconds), show "~" to indicate approx
JITTER_MAX_SEC = int(os.getenv("JITTER_MAX_SEC", "1800"))

# Thresholds (minutes) -> shield color
THRESHOLDS = [
    (5,   "red"),         # <= 5 min
    (15,  "orange"),      # <= 15 min
    (60,  "yellow"),      # <= 60 min
    (240, "brightgreen"), # <= 4 hours
]
DEFAULT_COLOR = "blue"

# Visuals
LABEL       = os.getenv("NEXT_BADGE_LABEL",        "Next Update")
LABEL_COLOR = os.getenv("NEXT_BADGE_LABEL_COLOR",  "2e2e2e")  # dark label for dark themes
LOGO        = os.getenv("NEXT_BADGE_LOGO",         "timer")

# Output path
OUT_PATH = Path("badges/next_update.json")


# ---- Helpers ----------------------------------------------------------------

def _next_scheduled(now_utc: dt.datetime) -> dt.datetime:
    """Return next occurrence of the daily schedule at CRON_HOUR:CRON_MINUTE UTC."""
    target = now_utc.replace(hour=CRON_HOUR, minute=CRON_MINUTE, second=0, microsecond=0)
    if target <= now_utc:
        target += dt.timedelta(days=1)
    return target

def _fmt_human(delta: dt.timedelta) -> str:
    """Human readable 'Hh Mm' (supports negative for overdue)."""
    total_sec = int(delta.total_seconds())
    sign = "-" if total_sec < 0 else ""
    total_sec = abs(total_sec)
    minutes, seconds = divmod(total_sec, 60)
    hours, minutes = divmod(minutes, 60)
    if hours >= 1:
        return f"{sign}{hours}h {minutes:02d}m"
    return f"{sign}{minutes}m"

def _color_for_minutes(min_left: float) -> str:
    for limit, color in THRESHOLDS:
        if min_left <= limit:
            return color
    return DEFAULT_COLOR


# ---- Main -------------------------------------------------------------------

def main() -> None:
    now = dt.datetime.utcnow()
    next_t = _next_scheduled(now)

    approx = JITTER_MAX_SEC > 0          # show "~" if jitter is enabled
    minutes_left = (next_t - now).total_seconds() / 60.0

    # Emoji by state
    if minutes_left < 0:
        emoji = "⏱️"   # overdue (should have started already)
    elif minutes_left <= 5:
        emoji = "⚡"
    elif minutes_left <= 30:
        emoji = "⌛"
    else:
        emoji = "⏳"

    human = _fmt_human(next_t - now)
    if approx:
        human = f"~{human}"

    color = _color_for_minutes(minutes_left)

    payload = {
        "schemaVersion": 1,
        "label": LABEL,
        "labelColor": LABEL_COLOR,
        "message": f"{emoji} {human}",
        "color": color,
        "logo": LOGO,
    }

    # Write only if changed to avoid noisy commits
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    old = None
    if OUT_PATH.exists():
        try:
            old = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass

    if old != payload:
        OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        print("[badge] updated:", payload)
    else:
        print("[badge] no change")


if __name__ == "__main__":
    main()
