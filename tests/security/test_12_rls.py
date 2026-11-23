"""Item 12: live tanker locations no longer need the public anon key. With a
database connection the server uses it directly (tested here on SQLite), and
the SQL closes the table to anon/authenticated."""
import re
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

import store

ROOT = Path(__file__).resolve().parents[2]
TANKER = {"user_id": "t-1", "role": "tanker", "tanker_operator_id": "OP-T1"}


@pytest.fixture()
def db(monkeypatch):
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(
            "create table tanker_locations (tanker_operator_id text primary key, user_id text, "
            "tanker_operator_name text, latitude real not null, longitude real not null, accuracy real, "
            "speed real, heading real, recorded_at text, updated_at text)"))
    monkeypatch.setattr(store, "engine", engine)
    return engine


class Boom:
    def table(self, *_a, **_k):
        raise AssertionError("Supabase API must not be used when the database is connected")


def test_location_saved_and_read_over_database(db, as_user, app_module, monkeypatch):
    monkeypatch.setattr(app_module, "supabase", Boom())
    c = as_user(**TANKER)
    assert c.post("/api/tanker/location", json={"latitude": 12.97, "longitude": 77.64, "speed": 8}).get_json()["success"]
    assert c.post("/api/tanker/location", json={"latitude": 12.98, "longitude": 77.65}).get_json()["success"]
    loc = c.get("/api/tanker/location/latest").get_json()["location"]
    assert (loc["tanker_operator_id"], loc["latitude"], loc["longitude"]) == ("OP-T1", 12.98, 77.65)
    with db.connect() as conn:
        assert conn.execute(text("select count(*) from tanker_locations")).scalar() == 1


def test_other_operator_cannot_read_my_location(db, as_user):
    as_user(**TANKER).post("/api/tanker/location", json={"latitude": 12.97, "longitude": 77.64})
    other = as_user(user_id="t-2", role="tanker", tanker_operator_id="OP-T2")
    assert other.get("/api/tanker/location/latest").get_json()["location"] is None


def test_app_never_calls_supabase_table_outside_fallback():
    src = (ROOT / "app.py").read_text()
    assert src.count("supabase.table(") == 2  # only the no-database fallback in the two helpers


def test_sql_closes_tanker_locations_and_checks_views():
    sql = (ROOT / "supabase" / "security_hardening.sql").read_text().lower()
    assert 'drop policy if exists "tanker_locations_anon_all"' in sql
    assert "revoke all on table public.tanker_locations from anon, authenticated" in sql
    assert "security_invoker" in sql and "relrowsecurity" in sql
    migration = (ROOT / "supabase" / "tanker_locations_migration.sql").read_text().lower()
    assert not re.search(r"create policy[^;]*to anon", migration)
