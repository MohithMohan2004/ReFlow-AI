"""OCEMS limit alerts: one alert per excursion, reopen instead of flapping,
plant-scoped endpoints."""
import itertools

import pytest

import ocems_alerts as OA

LIMITS = {"pH": "6.5 - 8.5", "BOD": "<= 10", "COD": "<= 50", "TSS": "<= 10"}
UNITS = {"BOD": "mg/L", "COD": "mg/L", "TSS": "mg/L"}


def row(t, **values):
    base = {"pH": 7.2, "BOD": 6, "COD": 30, "TSS": 5}
    base.update(values)
    return dict(base, timestamp=f"2026-11-24 {t}:00")


def run(rows, alerts, last=""):
    ids = (f"OA-{i}" for i in itertools.count(1))
    return OA.evaluate("PSTP001", rows, LIMITS, UNITS, alerts, last, "2026-11-24 12:00:00", lambda: next(ids))


def test_parse_limit():
    assert OA.parse_limit("6.5 - 8.5") == (6.5, 8.5)
    assert OA.parse_limit("<= 10") == (None, 10)
    assert OA.parse_limit("≥ 2") == (2, None)
    assert OA.parse_limit("-") is None


def test_first_check_only_uses_newest_reading():
    alerts = []
    opened, last = run([row("09:00", BOD=30), row("10:00")], alerts)
    assert opened == [] and alerts == [] and last == "2026-11-24 10:00:00"


def test_one_alert_per_excursion_tracks_worst_and_resolves():
    alerts = []
    _, last = run([row("10:00")], alerts)
    opened, last = run([row("10:15", BOD=12.4), row("10:30", BOD=15), row("10:45", BOD=11)], alerts, last)
    assert [a["parameter"] for a in opened] == ["BOD"]
    a = alerts[0]
    assert (a["status"], a["first_value"], a["worst_value"], a["last_value"]) == ("open", "12.4", "15", "11")
    assert OA.describe(a) == "BOD is 11 mg/L (limit ≤ 10 mg/L)"
    opened, last = run([row("11:00", BOD=8)], alerts, last)
    assert opened == [] and a["status"] == "resolved" and a["resolved_at"] == "2026-11-24 11:00:00"


def test_ph_low_and_high_both_alert():
    alerts = []
    _, last = run([row("10:00")], alerts)
    opened, _ = run([row("10:15", pH=6.1)], alerts, last)
    assert opened[0]["parameter"] == "pH"


def test_flapping_reopens_same_alert():
    alerts = []
    _, last = run([row("10:00")], alerts)
    _, last = run([row("10:15", COD=55), row("10:30", COD=40)], alerts, last)
    opened, last = run([row("10:45", COD=52)], alerts, last)   # 15 min later: reopen
    assert len(alerts) == 1 and alerts[0]["status"] == "open" and opened == [alerts[0]]
    _, last = run([row("11:00", COD=40)], alerts, last)
    opened, _ = run([row("12:00", COD=60)], alerts, last)       # an hour later: new alert
    assert len(alerts) == 2 and opened == [alerts[1]]


def test_missing_values_and_old_rows_ignored():
    alerts = []
    _, last = run([row("10:00")], alerts)
    opened, last2 = run([row("09:00", BOD=99), row("10:15", BOD="--", TSS=None)], alerts, last)
    assert opened == [] and alerts == [] and last2 == "2026-11-24 10:15:00"


# --- endpoints -------------------------------------------------------------
@pytest.fixture()
def feed(app_module, monkeypatch):
    app_module.save_ocems_alerts([])
    state = {"rows": [row("10:00")]}

    def fake_load(stp_id):
        if stp_id != "PSTP001":
            return {"available": False, "rows": []}
        return {"available": True, "rows": list(reversed(state["rows"])), "units": UNITS,
                "permissible_ranges": LIMITS, "parameters": list(LIMITS), "latest": state["rows"][-1]}

    monkeypatch.setattr(app_module, "load_ocems_data", fake_load)
    with app_module.store.open(app_module.OCEMS_ALERT_STATE_FILE, "w", encoding="utf-8") as f:
        f.write("{}")
    return state


def test_plant_sees_and_reads_its_alerts(as_user, feed):
    c = as_user(user_id="plant-1", role="stp", stp_id="PSTP001")
    assert c.get("/api/ocems_alerts").get_json()["alerts"] == []
    feed["rows"].append(row("10:15", TSS=14))
    body = c.get("/api/ocems_alerts").get_json()
    assert body["open"] == 1 and body["unread"] == 1
    assert body["alerts"][0]["message"] == "TSS is 14 mg/L (limit ≤ 10 mg/L)"
    assert c.post("/api/ocems_alerts/read", headers={"Origin": "http://localhost"}).status_code == 200
    assert c.get("/api/ocems_alerts").get_json()["unread"] == 0


def test_other_roles_and_plants_cannot_see_alerts(as_user, app_module, feed):
    plant = as_user(user_id="plant-1", role="stp", stp_id="PSTP001")
    plant.get("/api/ocems_alerts")
    feed["rows"].append(row("10:15", TSS=14))
    plant.get("/api/ocems_alerts")
    other = as_user(user_id="plant-2", role="stp", stp_id="PSTP002")
    assert other.get("/api/ocems_alerts").get_json()["alerts"] == []
    buyer = as_user(user_id="d-1", role="demand")
    assert buyer.get("/api/ocems_alerts").status_code == 403
    assert buyer.post("/api/ocems_alerts/read", headers={"Origin": "http://localhost"}).status_code == 403
