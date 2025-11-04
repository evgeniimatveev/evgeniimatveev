# build_next_badge.py
# -*- coding: utf-8 -*-

from __future__ import annotations
import os, json, datetime as dt
from pathlib import Path
from typing import Iterable, Optional, Tuple

# -------------------- small env helpers --------------------

def getenv_first(keys: Iterable[str], default: Optional[str] = None) -> str:
    """Return the first existing env var among keys, else default (or empty)."""
    for k in keys:
        v = os.getenv(k)
        if v is not None:
            return v
    return default if default is not None else ""

def getenv_int(keys: Iterable[str], default: int) -> int:
    """Same as getenv_first but coerces result to int with a safe fallback."""
    raw = getenv_first(keys, None)
    try:
        return int(raw) if raw is not None else default
    except Exception:
        return default

# -------------------- config (via env) --------------------

# Daily target time in UTC (kept compatible with earlier names)
CRON_HOUR   = getenv_int(["NEXT_UPDATE_HOUR", "CRON_HOUR", "NEXT_CRON_HOUR"], 12)
CRON_MINUTE = getenv_int(["NEXT_UPDATE_MIN",  "CRON_MINUTE", "NEXT_CRON_MINUTE"], 15)

# If >0 we prefix human time with "~" to indicate jitter/approximation
JITTER_MAX_SEC = getenv_int(["JITTER_MAX_SEC", "NEXT_BADGE_JITTER_SEC"], 0)

# Badge appearance
LABEL       = getenv_first(["NEXT_BADGE_LABEL"], "Next Update")
LABEL_COLOR = getenv_first(["NEXT_BADGE_LABEL_COLOR"], "2e2e2e")
LOGO        = getenv_first(["NEXT_BADGE_NAMED_LOGO", "NEXT_BADGE_LOGO"], "timer")

# Output JSON
OUT_PATH = Path("badges/next_update.json")

# -------------------- time helpers --------------------

def next_scheduled(now_utc: dt.datetime) -> dt.datetime:
    """Return the next daily occurrence at CRON_HOUR:CRON_MINUTE (UTC)."""
    nxt = now_utc.replace(hour=CRON_HOUR, minute=CRON_MINUTE, second=0, microsecond=0)
    if nxt <= now_utc:
        nxt += dt.timedelta(days=1)
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

# -------------------- color helpers (period-wide gradient) --------------------

def _hex_to_rgb(h: str) -> Tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

def _rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    r, g, b = rgb
    return f"{r:02x}{g:02x}{b:02x}"

def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t

def _lerp_rgb(a: Tuple[int, int, int], b: Tuple[int, int, int], t: float) -> Tuple[int, int, int]:
    return (
        int(round(_lerp(a[0], b[0], t))),
        int(round(_lerp(a[1], b[1], t))),
        int(round(_lerp(a[2], b[2], t))),
    )

def palette_color_hex(ratio: float) -> str:
    """
    Map ratio in [0..1] to a smooth multi-stop gradient across the WHOLE period:
      ratio=1.0 -> just after last update (far from deadline)
      ratio=0.0 -> right at next update (deadline)
    Palette: calm cyan -> sky blue -> violet -> amber -> red.
    """
    stops = ["#00c6ff", "#1e88e5", "#7e57c2", "#ffb300", "#e53935"]
    # Convert to RGB once
    rgbs = [_hex_to_rgb(s) for s in stops]
    n = len(rgbs) - 1
    if n <= 0:
        return stops[0].lstrip("#")

    # Clamp ratio
    r = max(0.0, min(1.0, ratio))
    # Find segment
    pos = r * n
    i = int(pos)
    t = pos - i
    if i >= n:
        i = n - 1
        t = 1.0
    rgb = _lerp_rgb(rgbs[i], rgbs[i+1], t)
    return _rgb_to_hex(rgb)

# -------------------- main --------------------

def main() -> None:
    now = dt.datetime.utcnow()
    nxt = next_scheduled(now)
    prev = nxt - dt.timedelta(days=1)  # previous day’s scheduled time

    # Remaining time & human string
    remaining = nxt - now
    human = fmt_human(remaining, approx=(JITTER_MAX_SEC > 0))

    # Ratio across the WHOLE period (prev -> nxt). 1 = just after prev (far), 0 = at nxt.
    period = (nxt - prev).total_seconds()
    ratio  = (now - prev).total_seconds() / period if period > 0 else 1.0
    # Convert to “distance to deadline” so that 1 (far) -> calm; 0 (near) -> intense
    ratio_to_deadline = 1.0 - max(0.0, min(1.0, ratio))

    # Overdue safeguard
    if remaining.total_seconds() < 0:
        color_hex = "b00040"  # deep red
    else:
        color_hex = palette_color_hex(ratio_to_deadline)

    payload = {
        "schemaVersion": 1,
        "label": LABEL,
        "labelColor": LABEL_COLOR,
        "message": human,          # <- no emojis here
        "color": color_hex,
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
