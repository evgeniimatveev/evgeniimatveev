# build_next_badge.py
# -*- coding: utf-8 -*-

from __future__ import annotations
import os
import json
import datetime as dt
from pathlib import Path
from typing import Iterable, Optional

# ------------------------------------------------------------
# Env helpers
# ------------------------------------------------------------

def getenv_first(candidates: Iterable[str], default: Optional[str] = None) -> str:
    """Return the first existing env value from candidates, else default (or empty)."""
    for k in candidates:
        v = os.getenv(k)
        if v is not None:
            return v
    return default if default is not None else ""

def getenv_int(cands: Iterable[str], default: int) -> int:
    """Return env as int with a safe fallback."""
    raw = getenv_first(cands, None)
    try:
        return int(raw) if raw is not None else default
    except Exception:
        return default

def getenv_float(cands: Iterable[str], default: float) -> float:
    """Return env as float with a safe fallback."""
    raw = getenv_first(cands, None)
    try:
        return float(raw) if raw is not None else default
    except Exception:
        return default

# ------------------------------------------------------------
# Config (via env)
# ------------------------------------------------------------

# Daily schedule (UTC). Multiple keys kept for backward compatibility.
CRON_HOUR   = getenv_int(["NEXT_UPDATE_HOUR", "CRON_HOUR", "NEXT_CRON_HOUR"], 7)
CRON_MINUTE = getenv_int(["NEXT_UPDATE_MIN",  "CRON_MINUTE", "NEXT_CRON_MINUTE"], 43)

# If >0 we mark human time as approximate with "~".
JITTER_MAX_SEC   = getenv_int(["JITTER_MAX_SEC", "NEXT_BADGE_JITTER_SEC"], 0)

# Countdown window in minutes that controls the color gradient.
TOTAL_WINDOW_MIN = getenv_float(["NEXT_BADGE_WINDOW_MIN", "TOTAL_WINDOW_MIN"], 20.0)

# Badge appearance.
LABEL       = getenv_first(["NEXT_BADGE_LABEL"], "Next Update")
LABEL_COLOR = getenv_first(["NEXT_BADGE_LABEL_COLOR"], "2e2e2e")    # left label color
LOGO        = getenv_first(["NEXT_BADGE_NAMED_LOGO", "NEXT_BADGE_LOGO"], "timer")

# Output JSON path consumed by shields.io endpoint
OUT_PATH    = Path("badges/next_update.json")

# --- Logging config (rotating logs) ---
LOG_JSONL_PATH   = Path("badges/next_update_log.jsonl")  # one JSON per line
LOG_TXT_PATH     = Path("badges/next_update_log.txt")    # human-readable
LOG_MAX_LINES    = getenv_int(["NEXT_BADGE_LOG_MAX", "LOG_MAX_LINES"], 400)

# When to write to logs:
# - LOG_EVERY_RUN: "1" -> append on every run (can cause frequent commits)
# - otherwise append only when badge JSON changed, plus periodic snapshots
LOG_EVERY_RUN    = getenv_first(["NEXT_BADGE_LOG_EVERY_RUN"], "0") not in ("0", "false", "False")

# Append a snapshot every N minutes regardless of change (0 = disabled)
LOG_SNAPSHOT_MIN = getenv_int(["NEXT_BADGE_LOG_SNAPSHOT_MIN"], 60)  # hourly by default

# ------------------------------------------------------------
# Time helpers
# ------------------------------------------------------------

def next_scheduled(now_utc: dt.datetime) -> dt.datetime:
    """Return the next daily occurrence at CRON_HOUR:CRON_MINUTE (UTC)."""
    nxt = now_utc.replace(hour=CRON_HOUR, minute=CRON_MINUTE, second=0, microsecond=0)
    if nxt <= now_utc:
        nxt = nxt + dt.timedelta(days=1)
    return nxt

def fmt_human(delta: dt.timedelta, approx: bool = False) -> str:
    """Return compact human-friendly remaining time string."""
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

# ------------------------------------------------------------
# Color gradient (red -> yellow -> green)
# ------------------------------------------------------------

def gradient_color_hex(minutes_left: float, window_min: float) -> str:
    """
    Return hex color (without '#') for smooth red->yellow->green transition.
    ratio=0 (now/overdue) => red, ratio=1 (>=window) => green.
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

# ------------------------------------------------------------
# Logging helpers
# ------------------------------------------------------------

def _should_take_snapshot(now: dt.datetime) -> bool:
    """Return True if periodic snapshot should be taken at this minute."""
    if LOG_SNAPSHOT_MIN <= 0:
        return False
    minute_index = int(now.timestamp() // 60)
    return (minute_index % LOG_SNAPSHOT_MIN) == 0

def _append_and_rotate(path: Path, new_line: str, max_lines: int) -> None:
    """Append a line and keep only the last max_lines."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        lines = []
    lines.append(new_line)
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

def write_logs(now: dt.datetime,
               human: str,
               minutes_left: float,
               color_hex: str,
               message: str) -> None:
    """Write JSONL + text logs with rotation."""
    LOG_JSONL_PATH.parent.mkdir(parents=True, exist_ok=True)
    ts = now.replace(microsecond=0).isoformat() + "Z"
    entry = {
        "ts": ts,
        "human": human,
        "minutes_left": round(minutes_left, 2),
        "color": color_hex,
        "label": LABEL,
        "message": message,
        "sha": os.getenv("GITHUB_SHA", ""),
        "run_id": os.getenv("GITHUB_RUN_ID", ""),
        "repo": os.getenv("GITHUB_REPOSITORY", ""),
    }
    # JSONL
    _append_and_rotate(LOG_JSONL_PATH, json.dumps(entry, ensure_ascii=False), LOG_MAX_LINES)
    # TXT (compact)
    txt = f'{ts} | {human:<8} | {minutes_left:6.1f}m | #{color_hex} | {message}'
    _append_and_rotate(LOG_TXT_PATH, txt, LOG_MAX_LINES)

# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

def main() -> None:
    now = dt.datetime.utcnow()
    nxt = next_scheduled(now)
    approx = JITTER_MAX_SEC > 0

    minutes_left = (nxt - now).total_seconds() / 60.0
    human        = fmt_human(nxt - now, approx=approx)
    color_hex    = gradient_color_hex(minutes_left, TOTAL_WINDOW_MIN)

    # message shows only the time string (no emoji for a clean look)
    payload = {
        "schemaVersion": 1,
        "label": LABEL,
        "labelColor": LABEL_COLOR,
        "message": human,
        "color": color_hex,
        "namedLogo": LOGO,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    try:
        old = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    except Exception:
        old = None

    changed = (old != payload)
    if changed:
        OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        print("[badge] updated:", payload)
    else:
        print("[badge] no change")

    # Logging policy: every run OR changed OR periodic snapshot
    take_snapshot = _should_take_snapshot(now)
    if LOG_EVERY_RUN or changed or take_snapshot:
        write_logs(now, human, minutes_left, color_hex, payload["message"])
        print("[log] written",
              "(every-run)" if LOG_EVERY_RUN else
              "(changed)" if changed else
              f"(snapshot/{LOG_SNAPSHOT_MIN}m)")
    else:
        print("[log] skipped (no change and no snapshot)")

if __name__ == "__main__":
    main()
