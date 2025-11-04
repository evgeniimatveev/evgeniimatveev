# build_next_badge.py
# -*- coding: utf-8 -*-
# Generates a Shields.io endpoint JSON with a time-to-next-update message
# and a smooth color gradient driven by minutes remaining.
# No emoji, only a clean label + message + dynamic color.

from __future__ import annotations
import os, json, datetime as dt
from pathlib import Path
from typing import Iterable, Optional

# ---------- env helpers ----------

def getenv_first(candidates: Iterable[str], default: Optional[str] = None) -> str:
    """Return the first existing env value from candidates, else default (or empty)."""
    for k in candidates:
        v = os.getenv(k)
        if v is not None:
            return v
    return default if default is not None else ""

def getenv_int(cands: Iterable[str], default: int) -> int:
    """Integer version of getenv with safe fallback."""
    raw = getenv_first(cands, None)
    try:
        return int(raw) if raw is not None else default
    except Exception:
        return default

def getenv_float(cands: Iterable[str], default: float) -> float:
    """Float version of getenv with safe fallback."""
    raw = getenv_first(cands, None)
    try:
        return float(raw) if raw is not None else default
    except Exception:
        return default

# ---------- config (via env) ----------

# Daily schedule (UTC). Multiple keys kept for backward compatibility.
CRON_HOUR   = getenv_int(["NEXT_UPDATE_HOUR", "CRON_HOUR", "NEXT_CRON_HOUR"], 7)
CRON_MINUTE = getenv_int(["NEXT_UPDATE_MIN",  "CRON_MINUTE", "NEXT_CRON_MINUTE"], 43)

# If >0 we prefix human time with "~" to signal possible jitter around the moment.
JITTER_MAX_SEC = getenv_int(["JITTER_MAX_SEC", "NEXT_BADGE_JITTER_SEC"], 0)

# Size of the visualization window (in minutes) that drives the color transition.
# At ratio=0 (now/overdue) we use a "hot" color; at ratio>=1 (far) we clamp to a calm color.
WINDOW_MIN = getenv_float(["NEXT_BADGE_WINDOW_MIN", "TOTAL_WINDOW_MIN"], 20.0)

# Badge appearance.
LABEL       = getenv_first(["NEXT_BADGE_LABEL"], "Next Update")
LABEL_COLOR = getenv_first(["NEXT_BADGE_LABEL_COLOR"], "2e2e2e")
LOGO        = getenv_first(["NEXT_BADGE_NAMED_LOGO", "NEXT_BADGE_LOGO"], "timer")

# Output JSON path.
OUT_PATH = Path("badges/next_update.json")

# ---------- time utils ----------

def next_scheduled(now_utc: dt.datetime) -> dt.datetime:
    """Return the next daily occurrence at CRON_HOUR:CRON_MINUTE (UTC)."""
    nxt = now_utc.replace(hour=CRON_HOUR, minute=CRON_MINUTE, second=0, microsecond=0)
    if nxt <= now_utc:
        nxt = nxt + dt.timedelta(days=1)
    return nxt

def fmt_human(delta: dt.timedelta, approx: bool = False) -> str:
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

# ---------- color utils (HSL -> HEX) ----------

def _hsl_to_hex(h: float, s: float, l: float) -> str:
    """
    Convert HSL (0..360, 0..1, 0..1) to hex string without '#'.
    Uses standard HSL-to-RGB conversion.
    """
    c = (1 - abs(2*l - 1)) * s
    h_ = (h % 360) / 60.0
    x = c * (1 - abs((h_ % 2) - 1))
    if   0 <= h_ < 1: r, g, b = c, x, 0
    elif 1 <= h_ < 2: r, g, b = x, c, 0
    elif 2 <= h_ < 3: r, g, b = 0, c, x
    elif 3 <= h_ < 4: r, g, b = 0, x, c
    elif 4 <= h_ < 5: r, g, b = x, 0, c
    else:             r, g, b = c, 0, x
    m = l - c/2
    R = int(round((r + m) * 255))
    G = int(round((g + m) * 255))
    B = int(round((b + m) * 255))
    return f"{R:02x}{G:02x}{B:02x}"

def timeline_color_hex(minutes_left: float, window_min: float) -> str:
    """
    Smooth color across time using HSL for a pleasing, modern look.

    Design:
      - Overdue/now: deep crimson (attention but not harsh red)
      - Progress through window: hue sweeps from hot pink -> amber -> lime
      - Beyond window: clamp to calm lime (stable)

    Hues (degrees): 330 -> 60 -> 140 (piecewise, via a single 330->140 sweep)
    Saturation: 0.90, Lightness: 0.45
    """
    if minutes_left < 0:
        return "b00040"  # deep crimson for overdue

    # ratio in [0..1]; >=1 clamps to final calm color
    ratio = max(0.0, min(1.0, minutes_left / max(1e-6, window_min)))

    # Sweep hue from 330 (hot pink) down to 140 (lime) as ratio grows.
    start_h, end_h = 330.0, 140.0
    # Interpolate with slight easing for a softer start
    eased = ratio * ratio * (3 - 2 * ratio)  # smoothstep
    h = start_h + (end_h - start_h) * eased
    return _hsl_to_hex(h, s=0.90, l=0.45)

# ---------- main ----------

def main() -> None:
    now = dt.datetime.utcnow()
    nxt = next_scheduled(now)
    approx = JITTER_MAX_SEC > 0

    delta = nxt - now
    minutes_left = delta.total_seconds() / 60.0
    human = fmt_human(delta, approx=approx)

    payload = {
        "schemaVersion": 1,
        "label": LABEL,
        "labelColor": LABEL_COLOR,
        "message": human,  # clean text only, no emoji
        "color": timeline_color_hex(minutes_left, WINDOW_MIN),
        "namedLogo": LOGO,
        # "style": "flat",
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    try:
        old = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    except Exception:
        old = None

    if old != payload:
        OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        print("[badge] updated:", payload)
    else:
        print("[badge] no change")

if __name__ == "__main__":
    main()
