"""OCEMS limit alerts: turn a plant's readings into alerts.

A parameter (pH, BOD, COD, TSS) "goes out of limits" when a reading falls
outside its prescribed range (OCEMS_DEFAULT_LIMITS in app.py). Each
excursion is one alert: it opens on the first reading outside the range,
follows the readings while they stay outside (latest and worst value), and
closes on the first reading back inside. One excursion = one notification,
however long it lasts.

If the same parameter goes out again within REOPEN_MINUTES of closing, the
closed alert reopens instead of starting a new one, so a value hovering on
the limit doesn't send a stream of notifications.

This module only holds the rules. app.py stores the alerts, runs the
background check and serves them to the plant's Supply page.
"""

import re
from datetime import datetime, timedelta

REOPEN_MINUTES = 30

FIELDS = [
    "alert_id", "stp_id", "parameter", "unit", "limit", "status",
    "started_at", "first_value", "worst_value", "last_value", "last_seen_at",
    "resolved_at", "created_at", "read_at",
]

OPEN = "open"
RESOLVED = "resolved"

_NUMBER = r"(-?\d+(?:\.\d+)?)"


def parse_limit(text):
    """"6.5 - 8.5" -> (6.5, 8.5); "<= 10" -> (None, 10); ">= 2" -> (2, None).
    Anything else -> None (no limit, never alerts)."""
    text = str(text or "").strip()
    m = re.fullmatch(_NUMBER + r"\s*[-–]\s*" + _NUMBER, text)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.fullmatch(r"(?:<=|≤|<)\s*" + _NUMBER, text)
    if m:
        return None, float(m.group(1))
    m = re.fullmatch(r"(?:>=|≥|>)\s*" + _NUMBER, text)
    if m:
        return float(m.group(1)), None
    return None


def as_number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        n = float(str(value).replace(",", "").strip())
    except ValueError:
        return None
    return n if n == n and n not in (float("inf"), float("-inf")) else None


def outside(value, bounds):
    low, high = bounds
    return (low is not None and value < low) or (high is not None and value > high)


def excess(value, bounds):
    """How far a value is beyond its limit (0 when inside)."""
    low, high = bounds
    if low is not None and value < low:
        return low - value
    if high is not None and value > high:
        return value - high
    return 0.0


def _ts(text):
    try:
        return datetime.strptime(str(text), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _fmt(n):
    return str(int(n)) if float(n).is_integer() else str(round(n, 3))


def evaluate(stp_id, rows, limits, units, alerts, last_checked, now_text, new_id):
    """Apply new readings to a plant's alerts.

    rows         readings, any order, {"timestamp": "YYYY-MM-DD HH:MM:SS", "BOD": 12, ...}
    limits       {"BOD": "<= 10", ...}
    alerts       this plant's alert rows (dicts with FIELDS); changed in place
    last_checked timestamp of the newest reading already applied ("" = never)
    Returns (opened, last_checked): alerts that newly opened or reopened,
    and the timestamp to remember for next time.

    The first time a plant is checked only its newest reading counts, so
    connecting a feed doesn't raise alerts for last week."""
    bounds = {p: parse_limit(l) for p, l in limits.items()}
    bounds = {p: b for p, b in bounds.items() if b}

    readings = sorted(
        (r for r in rows if _ts(r.get("timestamp"))),
        key=lambda r: r["timestamp"],
    )
    if last_checked:
        readings = [r for r in readings if r["timestamp"] > last_checked]
    else:
        readings = readings[-1:]

    opened = []
    by_param = {}
    for alert in alerts:
        if alert.get("stp_id") == stp_id:
            current = by_param.get(alert["parameter"])
            if current is None or alert.get("started_at", "") >= current.get("started_at", ""):
                by_param[alert["parameter"]] = alert

    for reading in readings:
        stamp = reading["timestamp"]
        for parameter, limit_bounds in bounds.items():
            value = as_number(reading.get(parameter))
            if value is None:
                continue   # missing reading: neither opens nor closes
            alert = by_param.get(parameter)
            is_open = alert is not None and alert.get("status") == OPEN

            if not outside(value, limit_bounds):
                if is_open:
                    alert["status"] = RESOLVED
                    alert["resolved_at"] = stamp
                continue

            if is_open:
                alert["last_value"] = _fmt(value)
                alert["last_seen_at"] = stamp
                worst = as_number(alert.get("worst_value"))
                if worst is None or excess(value, limit_bounds) > excess(worst, limit_bounds):
                    alert["worst_value"] = _fmt(value)
                continue

            closed_at = _ts(alert.get("resolved_at")) if alert else None
            if closed_at and _ts(stamp) - closed_at <= timedelta(minutes=REOPEN_MINUTES):
                alert.update(status=OPEN, resolved_at="", last_value=_fmt(value),
                             last_seen_at=stamp, read_at="")
                worst = as_number(alert.get("worst_value"))
                if worst is None or excess(value, limit_bounds) > excess(worst, limit_bounds):
                    alert["worst_value"] = _fmt(value)
                if alert not in opened:
                    opened.append(alert)
                continue

            alert = {
                "alert_id": new_id(),
                "stp_id": stp_id,
                "parameter": parameter,
                "unit": str(units.get(parameter) or ""),
                "limit": str(limits.get(parameter) or ""),
                "status": OPEN,
                "started_at": stamp,
                "first_value": _fmt(value),
                "worst_value": _fmt(value),
                "last_value": _fmt(value),
                "last_seen_at": stamp,
                "resolved_at": "",
                "created_at": now_text,
                "read_at": "",
            }
            alerts.append(alert)
            by_param[parameter] = alert
            opened.append(alert)

    if readings:
        last_checked = readings[-1]["timestamp"]
    return opened, last_checked


def describe(alert):
    """One-line text for a notification: "BOD is 12.4 mg/L (limit ≤ 10)"."""
    unit = f" {alert['unit']}" if alert.get("unit") else ""
    limit = str(alert.get("limit") or "").replace("<=", "≤").replace(">=", "≥")
    return f"{alert['parameter']} is {alert.get('last_value')}{unit} (limit {limit}{unit})"
