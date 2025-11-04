# build_next_badge.py
# -*- coding: utf-8 -*-

from __future__ import annotations
import os
import json
import datetime as dt
from pathlib import Path
from typing import Iterable, Optional, Dict, Any, Tuple

# -------------------------- env helpers --------------------------

def getenv_first(candidates: Iterable[str], default: Optional[str] = None) -> str:
    """Return the first existing env value from candidates, else default (or empty)."""
    for k in candidates:
        v = os.getenv(k)
        if v is not None:
            return v
    return default if default is not None else ""

def getenv_int(cands: Iterable[str], default: int) -> int:
    """Like getenv_first but coerces to int with safe fallback."""
    raw = getenv_first(cands, None)
    try:
        return int(raw) if raw is not None else default
    except Exception:
        return default

def getenv_float(cands: Iterable[str], default: float) -> float:
    """Like getenv_first but coerces to float with safe fallback."""
    raw = getenv_first(cands, None)
    try:
        return float(raw) if raw is not None else default
    except Exception:
        return default

def getenv_bool(cands: Iterable[str], default: bool) -> bool:
    """Interpret typical truthy/falsey strings."""
    raw = getenv_first(cands, None)
    if raw is None:
        return default
    return str(raw).lower() not in ("0", "false", "no", "off", "")

# -------------------------- configuration --------------------------

# Daily schedule (UTC). Multiple keys kept for backward compatibility.
CRON_HOUR   = getenv_int(["NEXT_UPDATE_HOUR", "CRON_HOUR", "NEXT_CRON_HOUR"], 7)
CRON_MINUTE = getenv_int(["NEXT_UPDATE_MIN", "CRON_MINUTE", "NEXT_CRON_MINUTE"], 43)

# If >0 we mark human time as approximate with "~".
JITTER_MAX_SEC = getenv_int(["JITTER_MAX_SEC", "NEXT_BADGE_JITTER_SEC"], 0)

# Size (minutes) of the window used by the color gradient.
TOTAL_WINDOW_MIN = getenv_float(["NEXT_BADGE_WINDOW_MIN", "TOTAL_WINDOW_MIN"], 20.0)

# Badge appearance
LABEL       = getenv_first(["NEXT_BADGE_LABEL"], "Next Update")
LABEL_COLOR = getenv_first(["NEXT_BADGE_LABEL_COLOR"], "2e2e2e")
LOGO        = getenv_first(["NEXT_BADGE_NAMED_LOGO", "NEXT_BADGE_LOGO"], "timer")

# Output paths
BADGE_PATH = Path("badges/next_update.json")
LOG_JSONL  = Path("badges/next_update_log.jsonl")  # line-delimited JSON (telemetry)
LOG_TXT    = Path("badges/next_update_log.txt")    # human-friendly tail view

# Logging policy
LOG_EVERY_RUN  = getenv_bool(["NEXT_BADGE_LOG_EVERY_RUN"], False)
SNAPSHOT_MIN   = getenv_int(["NEXT_BADGE_LOG_SNAPSHOT_MIN"], 60)  # minutes; 0 disables
LOG_MAX_LINES  = getenv_int(["NEXT_BADGE_LOG_MAX"], 400)          # rotation cap for each log

# -------------------------- time helpers --------------------------

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

# -------------------------- color gradient --------------------------
# Red -> Yellow -> Green smooth transition within TOTAL_WINDOW_MIN.

def gradient_color_hex(minutes_left: float, window_min: float) -> str:
    """
    Return hex color (without '#') for a smooth red->yellow->green transition.
    ratio=0 (now/overdue) => red, ratio=1 (>=window) => green.
    """
    if minutes_left < 0:
        return "9e0142"  # dark red for overdue

    # Clamp to [0..1]
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

# -------------------------- logging utils --------------------------

def _ensure_dirs() -> None:
    BADGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_JSONL.parent.mkdir(parents=True, exist_ok=True)
    LOG_TXT.parent.mkdir(parents=True, exist_ok=True)

def _read_last_jsonl_line(path: Path) -> Optional[str]:
    """Efficient tail(1) for reasonably-sized files."""
    try:
        with path.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            if size == 0:
                return None
            # read backwards up to ~8KB to find the last newline
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
    """Extract last 'ts' field from the JSONL tail, if present."""
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
    """Rotate file to keep the last N non-empty lines."""
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
    """Append a single entry to both JSONL and TXT logs, then rotate."""
    # JSONL
    with LOG_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # Human-readable TXT (compact)
    line = (
        f"[{entry['ts']}] color={entry['color']} "
        f"msg='{entry['message']}' next_utc={entry['next_utc']} "
        f"mins_left={entry['minutes_left']:.2f}\n"
    )
    with LOG_TXT.open("a", encoding="utf-8") as f:
        f.write(line)

    # Rotate both
    _tail_lines(LOG_JSONL, LOG_MAX_LINES)
    _tail_lines(LOG_TXT, LOG_MAX_LINES)

# -------------------------- main --------------------------

def build_payload(now: dt.datetime) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Build shields.io payload and a telemetry entry."""
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
        "message": human,           # no emoji, human-readable remaining time
        "color": color_hex,
        "namedLogo": LOGO,
        # "style": "flat",
    }

    telemetry: Dict[str, Any] = {
        "ts": now.replace(microsecond=0).isoformat(),  # ISO8601 UTC
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

    # Use UTC consistently
    now = dt.datetime.utcnow()

    payload, telemetry = build_payload(now)

    # Write badge JSON only if changed (reduces churn)
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
