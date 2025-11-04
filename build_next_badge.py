# build_next_badge.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import os, json, datetime as dt
from pathlib import Path

CRON_HOUR   = int(os.getenv("NEXT_UPDATE_HOUR", "12"))
CRON_MINUTE = int(os.getenv("NEXT_UPDATE_MIN",  "15"))
JITTER_MAX_SEC = int(os.getenv("JITTER_MAX_SEC", "1800"))

THRESHOLDS = [(5,"red"),(15,"orange"),(60,"yellow"),(240,"brightgreen")]
DEFAULT_COLOR = "blue"

LABEL       = os.getenv("NEXT_BADGE_LABEL",       "Next Update")
LABEL_COLOR = os.getenv("NEXT_BADGE_LABEL_COLOR", "2e2e2e")
LOGO        = os.getenv("NEXT_BADGE_LOGO",        "timer")   # <
OUT_PATH = Path("badges/next_update.json")

def _next_scheduled(now_utc: dt.datetime) -> dt.datetime:
    t = now_utc.replace(hour=CRON_HOUR, minute=CRON_MINUTE, second=0, microsecond=0)
    if t <= now_utc: t += dt.timedelta(days=1)
    return t

def _fmt_human(delta: dt.timedelta) -> str:
    s = int(delta.total_seconds()); sign = "-" if s < 0 else ""; s = abs(s)
    m, _ = divmod(s, 60); h, m = divmod(m, 60)
    return f"{sign}{h}h {m:02d}m" if h else f"{sign}{m}m"

def _color_for_minutes(min_left: float) -> str:
    for lim, col in THRESHOLDS:
        if min_left <= lim: return col
    return DEFAULT_COLOR

def main() -> None:
    now = dt.datetime.utcnow()
    nxt = _next_scheduled(now)
    approx = JITTER_MAX_SEC > 0
    minutes_left = (nxt - now).total_seconds()/60.0

    if minutes_left < 0:   emoji = "⏱️"
    elif minutes_left <=5: emoji = "⚡"
    elif minutes_left <=30:emoji = "⌛"
    else:                  emoji = "⏳"

    human = _fmt_human(nxt - now)
    if approx: human = f"~{human}"

    payload = {
        "schemaVersion": 1,
        "label": LABEL,
        "labelColor": LABEL_COLOR,
        "message": f"{emoji} {human}",
        "color": _color_for_minutes(minutes_left),
        "namedLogo": LOGO,               # <— ВАЖНО: namedLogo
        # "style": "flat"                # опционально
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    old = None
    if OUT_PATH.exists():
        try: old = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        except Exception: pass

    if old != payload:
        OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        print("[badge] updated:", payload)
    else:
        print("[badge] no change")

if __name__ == "__main__":
    main()
