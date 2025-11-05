# build_next_badge.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import json
import datetime as dt
from pathlib import Path
from typing import Iterable, Optional, Dict, Any, Tuple
from colorsys import rgb_to_hls, hls_to_rgb  # used to pastelize colors

# -------------------------- env helpers --------------------------

def getenv_first(candidates: Iterable[str], default: Optional[str] = None) -> str:
    """Return the first present env var from the list, else default (or empty string)."""
    for k in candidates:
        v = os.getenv(k)
        if v is not None:
            return v
    return default if default is not None else ""

def getenv_int(cands: Iterable[str], default: int) -> int:
    """Like getenv_first but coerces to int with a safe fallback."""
    raw = getenv_first(cands, None)
    try:
        return int(raw) if raw is not None else default
    except Exception:
        return default

def getenv_float(cands: Iterable[str], default: float) -> float:
    """Like getenv_first but coerces to float with a safe fallback."""
    raw = getenv_first(cands, None)
    try:
        return float(raw) if raw is not None else default
    except Exception:
        return default

def getenv_bool(cands: Iterable[str], default: bool) -> bool:
    """Interpret typical truthy/falsey strings for boolean env vars."""
    raw = getenv_first(cands, None)
    if raw is None:
        return default
    return str(raw).lower() not in ("0", "false", "no", "off", "")

# -------------------------- configuration --------------------------

# Daily schedule in UTC (kept backward-compatible with alternative names)
CRON_HOUR   = getenv_int(["NEXT_UPDATE_HOUR", "CRON_HOUR", "NEXT_CRON_HOUR"], 7)
CRON_MINUTE = getenv_int(["NEXT_UPDATE_MIN", "CRON_MINUTE", "NEXT_CRON_MINUTE"], 43)

# If >0 we mark human time as approximate by prefixing "~"
JITTER_MAX_SEC = getenv_int(["JITTER_MAX_SEC", "NEXT_BADGE_JITTER_SEC"], 0)

# Size (minutes) of the gradient sensitivity window
TOTAL_WINDOW_MIN = getenv_float(["NEXT_BADGE_WINDOW_MIN", "TOTAL_WINDOW_MIN"], 20.0)

# Badge appearance
LABEL       = getenv_first(["NEXT_BADGE_LABEL"], "Next Update")
# Light label color ensures Shields renders black text on the left side
LABEL_COLOR = getenv_first(["NEXT_BADGE_LABEL_COLOR"], "e5e7eb")
LOGO        = getenv_first(["NEXT_BADGE_NAMED_LOGO", "NEXT_BADGE_LOGO"], "timer")

# Output paths
BADGE_PATH = Path("badges/next_update.json")
LOG_JSONL  = Path("badges/next_update_log.jsonl")  # line-delimited JSON telemetry
LOG_TXT    = Path("badges/next_update_log.txt")    # human-friendly text tail

# Logging policy
LOG_EVERY_RUN  = getenv_bool(["NEXT_BADGE_LOG_EVERY_RUN"], False)
SNAPSHOT_MIN   = getenv_int(["NEXT_BADGE_LOG_SNAPSHOT_MIN"], 60)  # minutes; 0 disables
LOG_MAX_LINES  = getenv_int(["NEXT_BADGE_LOG_MAX"], 400)          # rotation cap

# Pastel palette (light backgrounds => Shields chooses black text on right side)
PASTELIZE        = getenv_bool(["NEXT_BADGE_PASTELIZE"], True)
PASTEL_FACTOR    = getenv_float(["NEXT_BADGE_PASTEL_FACTOR"], 0.65)  # 0.55..0.75 typical
OVERDUE_COLOR    = getenv_first(["NEXT_BADGE_OVERDUE_COLOR"], "fca5a5")  # light red
GREEN_MAX_COLOR  = getenv_first(["NEXT_BADGE_GREEN_COLOR"], "86efac")    # light green
YELLOW_COLOR     = getenv_first(["NEXT_BADGE_YELLOW_COLOR"], "fde68a")   # light yellow
RED_COLOR        = getenv_first(["NEXT_BADGE_RED_COLOR"], "f87171")      # red-400

# -------------------------- time helpers --------------------------

def next_scheduled(now_utc: dt.datetime) -> dt.datetime:
    """Return the next daily occurrence at CRON_HOUR:CRON_MINUTE (UTC)."""
    nxt = now_utc.replace(hour=CRON_HOUR, minute=CRON_MINUTE, second=0, microsecond=0)
    if nxt <= now_utc:
        nxt = nxt + dt.timedelta(days=1)
    return nxt

def fmt_human(delta: dt.timedelta, approx: bool = False) -> str:
    """Compact human-friendly remaining time string like '~5h 12m'."""
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

# -------------------------- color helpers --------------------------

def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"{r:02x}{g:02x}{b:02x}"

def _pastelize(hex_color: str, factor: float) -> str:
    """
    Lighten a hex color (using HLS) and slightly reduce saturation to get a pastel tone.
    factor: 0..1 (0 = unchanged, 1 = nearly white).
    """
    r, g, b = _hex_to_rgb(hex_color)
    rf, gf, bf = [x / 255.0 for x in (r, g, b)]
    h, l, s = rgb_to_hls(rf, gf, bf)
    l = l + (1.0 - l) * factor
    s = s * (1.0 - 0.35 * factor)
    r2, g2, b2 = hls_to_rgb(h, l, s)
    return _rgb_to_hex(int(r2 * 255), int(g2 * 255), int(b2 * 255))

# -------------------------- gradient --------------------------

def gradient_color_hex(minutes_left: float, window_min: float) -> str:
    """
    Smooth red -> yellow -> green gradient within the window.
    Then pastelize so the right side remains light and readable on dark themes.
    """
    if minutes_left < 0:
        base = OVERDUE_COLOR
    else:
        ratio = max(0.0, min(1.0, minutes_left / max(1e-6, window_min)))
        if ratio < 0.5:
            # RED -> YELLOW
            t = ratio / 0.5
            r1, g1, b1 = _hex_to_rgb(RED_COLOR)
            r2, g2, b2 = _hex_to_rgb(YELLOW_COLOR)
        else:
            # YELLOW -> GREEN
            t = (ratio - 0.5) / 0.5
            r1, g1, b1 = _hex_to_rgb(YELLOW_COLOR)
            r2, g2, b2 = _hex_to_rgb(GREEN_MAX_COLOR)
        r = int(r1 + (r2 - r1) * t)
        g = int(g1 + (g2 - g1) * t)
        b = int(b1 + (b2 - b1) * t)
        base = _rgb_to_hex(r, g, b)
    return _pastelize(base, PASTEL_FACTOR) if PASTELIZE else base

# -------------------------- logging utils --------------------------

def _ensure_dirs() -> None:
    BADGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_JSONL.parent.mkdir(parents=True, exist_ok=True)
    LOG_TXT.parent.mkdir(parents=True, exist_ok=True)

def _read_last_jsonl_line(path: Path) -> Optional[str]:
    """Tail(1) for reasonably small files — read last non-empty line from JSONL."""
    try:
        with path.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            if size == 0:
                return None
            chunk = 8192
            pos = max(0, size - chunk)
            f.seek(pos)
            data = f.read().decode("utf-8", errors="ignore")
            lines = [ln for ln in data.splitlines() if ln.strip()]
            return lines[-1] if lines else None
    except FileNotFoundError:
        return None
    except Exception:
        return None

def _last_snapshot_ts() -> Optional[dt.datetime]:
    """Extract last 'ts' from JSONL tail if present."""
    line = _read_last_jsonl_line(LOG_JSONL)
    if not line:
        return None
    try:
        obj = json.loads(line)
        if "ts" in obj:
            return dt.datetime.fromisoformat(obj["ts"])
    except Exception:
        pass
    return None

def _should_write_log(now: dt.datetime) -> bool:
    """Decide whether to append a telemetry entry this run."""
    if LOG_EVERY_RUN:
        return True
    if SNAPSHOT_MIN <= 0:
        return False
    last = _last_snapshot_ts()
    if last is None:
        return True
    return (now - last) >= dt.timedelta(minutes=SNAPSHOT_MIN)

def _tail_lines(path: Path, keep: int) -> None:
    """Rotate log file to keep only the last N non-empty lines."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) <= keep:
        return
    tail = "\n".join(lines[-keep:]) + "\n"
    path.write_text(tail, encoding="utf-8")

def _append_logs(entry: Dict[str, Any]) -> None:
    """Append one entry to both JSONL and TXT logs, then rotate."""
    with LOG_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    line = (
        f"[{entry['ts']}] color={entry['color']} "
        f"msg='{entry['message']}' next_utc={entry['next_utc']} "
        f"mins_left={entry['minutes_left']:.2f}\n"
    )
    with LOG_TXT.open("a", encoding="utf-8") as f:
        f.write(line)

    _tail_lines(LOG_JSONL, LOG_MAX_LINES)
    _tail_lines(LOG_TXT, LOG_MAX_LINES)

# -------------------------- main --------------------------

def build_payload(now: dt.datetime) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Build a Shields.io payload and a telemetry entry."""
    nxt = next_scheduled(now)
    approx = JITTER_MAX_SEC > 0
    delta = nxt - now
    minutes_left = delta.total_seconds() / 60.0

    human = fmt_human(delta, approx=approx)
    color_hex = gradient_color_hex(minutes_left, TOTAL_WINDOW_MIN)

    payload: Dict[str, Any] = {
        "schemaVersion": 1,
        "label": LABEL,
        "labelColor": LABEL_COLOR,
        "message": human,
        "color": color_hex,
        "namedLogo": LOGO,
    }

    telemetry: Dict[str, Any] = {
        "ts": now.replace(microsecond=0).isoformat(),
        "next_utc": nxt.replace(microsecond=0).isoformat(),
        "minutes_left": minutes_left,
        "message": human,
        "color": color_hex,
        "label": LABEL,
        "labelColor": LABEL_COLOR,
        "window_min": TOTAL_WINDOW_MIN,
        "cron_hour": CRON_HOUR,
        "cron_min": CRON_MINUTE,
        "jitter_max_sec": JITTER_MAX_SEC,
    }
    return payload, telemetry

def main() -> None:
    _ensure_dirs()
    now = dt.datetime.utcnow()

    payload, telemetry = build_payload(now)

    # Update badge JSON only if changed (reduces churn/commits)
    old = None
    try:
        old = json.loads(BADGE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass

    if old != payload:
        BADGE_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        print("[badge] updated:", payload)
    else:
        print("[badge] no change")

    # Telemetry logging (every run or periodic snapshots)
    if _should_write_log(now):
        _append_logs(telemetry)
        print("[log] appended")
    else:
        print("[log] skipped (policy)")

if __name__ == "__main__":
    main()
