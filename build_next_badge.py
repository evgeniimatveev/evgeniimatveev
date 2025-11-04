# build_next_badge.py
# -*- coding: utf-8 -*-

from __future__ import annotations
import os, json, datetime as dt
from pathlib import Path
from typing import Iterable, Optional

# ---------- env helpers ----------

def getenv_first(candidates: Iterable[str], default: Optional[str]=None) -> str:
    """Return the first existing env value from candidates, else default (or empty)."""
    for k in candidates:
        v = os.getenv(k)
        if v is not None:
            return v
    return default if default is not None else ""

def getenv_int(cands: Iterable[str], default: int) -> int:
    """Same as getenv_first but coerces the result to int with a safe fallback."""
    raw = getenv_first(cands, None)
    try:
        return int(raw) if raw is not None else default
    except Exception:
        return default

# ---------- config (via env) ----------

# Daily schedule (UTC). Multiple keys kept for backward compatibility.
CRON_HOUR   = getenv_int(["NEXT_UPDATE_HOUR","CRON_HOUR","NEXT_CRON_HOUR"], 7)
CRON_MINUTE = getenv_int(["NEXT_UPDATE_MIN","CRON_MINUTE","NEXT_CRON_MINUTE"], 43)

# If >0 we mark human time as approximate with "~".
JITTER_MAX_SEC = getenv_int(["JITTER_MAX_SEC","NEXT_BADGE_JITTER_SEC"], 0)

# Countdown window in minutes for color/emoji transitions.
TOTAL_WINDOW_MIN = float(getenv_first(["NEXT_BADGE_WINDOW_MIN","TOTAL_WINDOW_MIN"], "20"))

# Badge appearance.
LABEL       = getenv_first(["NEXT_BADGE_LABEL"], "Next Update")
LABEL_COLOR = getenv_first(["NEXT_BADGE_LABEL_COLOR"], "black")
LOGO        = getenv_first(["NEXT_BADGE_NAMED_LOGO"], "")  # e.g., "github"

# Output JSON path.
OUT_PATH = Path("badges/next_update.json")

# ---------- time utils ----------

def next_scheduled(now_utc: dt.datetime) -> dt.datetime:
    """Return the next daily occurrence at CRON_HOUR:CRON_MINUTE (UTC)."""
    nxt = now_utc.replace(hour=CRON_HOUR, minute=CRON_MINUTE, second=0, microsecond=0)
    if nxt <= now_utc:
        nxt = nxt + dt.timedelta(days=1)
    return nxt

def fmt_human(delta: dt.timedelta, approx: bool=False) -> str:
    """Compact human-friendly remaining time string."""
    sec = int(delta.total_seconds())
    if sec <= 0:
        return "now" if sec >= -30 else "overdue"
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    tilde = "~" if approx else ""
    if h > 0:
        return f"{tilde}{h}h {m}m"
    if m >= 2:
        return f"{tilde}{m}m"
    return f"{tilde}{m}m {s}s"

# ---------- color gradient: red -> yellow -> green ----------

def gradient_color_hex(minutes_left: float, window_min: float) -> str:
    """
    Return hex color (without '#') for smooth red->yellow->green transition.
    ratio=0 (now) => red, ratio=1 (far) => green.
    """
    if minutes_left < 0:
        return "9e0142"  # dark red for overdue

    ratio = max(0.0, min(1.0, minutes_left / max(1e-6, window_min)))

    if ratio < 0.5:
        # red -> yellow
        g = int(255 * (ratio / 0.5))   # 0..255
        r = 255
        b = 0
    else:
        # yellow -> green
        g = 255
        r = int(255 * (1 - (ratio - 0.5) / 0.5))  # 255..0
        b = 0

    return f"{r:02x}{g:02x}{b:02x}"

# ---------- 72-step emoji palette ----------

def build_emoji_palette(n: int = 72) -> list[str]:
    """
    Create a palette progressing from 'alert' red to 'ok' green.
    Last steps are celebratory: rocket/fire/sparkles; overdue uses explosion.
    """
    reds    = ["🟥","🔴","🧨","🛑","❗"]
    yellows = ["🟨","🟡","⚠️","⏳","⌛"]
    greens  = ["🟩","🟢","✅","☘️","💚","🟩","🟢","✅","💚","🟢"]

    n_red = max(6, int(n * 0.30))
    n_yel = max(4, int(n * 0.20))
    n_grn = max(10, n - n_red - n_yel)

    palette = (
        [reds[i % len(reds)] for i in range(n_red)] +
        [yellows[i % len(yellows)] for i in range(n_yel)] +
        [greens[i % len(greens)] for i in range(n_grn)]
    )

    if len(palette) >= 3:
        palette[-3:] = ["🚀","🔥","✨"]
    return palette[:n]

_EMOJI_STEPS = build_emoji_palette(72)

def emoji_for_minutes(minutes_left: float, window_min: float) -> str:
    """Map remaining minutes to one of the 72 emoji steps."""
    if minutes_left < 0:
        return "💥"
    idx = int(round((window_min - max(0.0, minutes_left)) / max(1e-6, window_min)
                    * (len(_EMOJI_STEPS)-1)))
    idx = max(0, min(len(_EMOJI_STEPS)-1, idx))
    return _EMOJI_STEPS[idx]

# ---------- main ----------

def main() -> None:
    now = dt.datetime.utcnow()
    nxt = next_scheduled(now)
    approx = JITTER_MAX_SEC > 0

    minutes_left = (nxt - now).total_seconds() / 60.0
    human = fmt_human(nxt - now, approx=approx)
    emoji = emoji_for_minutes(minutes_left, TOTAL_WINDOW_MIN)

    payload = {
        "schemaVersion": 1,
        "label": LABEL,
        "labelColor": LABEL_COLOR,
        "message": f"{emoji} {human}",
        "color": gradient_color_hex(minutes_left, TOTAL_WINDOW_MIN),
        "namedLogo": LOGO,
        # "style": "flat",
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    old = None
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
