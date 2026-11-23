"""Extra A follow-up: roles come from app_metadata; a user editing their own
user_metadata can never become an admin."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _login(client, email):
    return client.post("/api/login", json={"email": email, "password": "role-pass-1"})


@pytest.mark.parametrize("claimed", ["superadmin", "admin", "SuperAdmin"])
def test_admin_claim_in_user_metadata_is_refused(client, app_module, claimed, capsys):
    app_module.supabase.auth.add_user("eve@example.com", "role-pass-1", role=claimed)
    assert _login(client, "eve@example.com").status_code == 403
    with client.session_transaction() as s:
        assert "user_id" not in s
    assert "event=admin_role_claim_refused" in capsys.readouterr().out
    page = client.post("/login", data={"login_identifier": "eve@example.com", "password": "role-pass-1"})
    assert b"valid system role" in page.data


def test_admin_from_app_metadata_works(client, app_module):
    app_module.supabase.auth.add_user("boss@example.com", "role-pass-1", app_metadata={"role": "superadmin"})
    res = client.post("/login", data={"login_identifier": "boss@example.com", "password": "role-pass-1"})
    assert res.status_code == 302 and res.headers["Location"].endswith("/admin/mfa")
    with client.session_transaction() as s:
        assert s["mfa_pending"]["values"]["role"] == "superadmin"   # admin after the code step


def test_app_metadata_wins_over_edited_user_metadata(client, app_module):
    app_module.supabase.auth.add_user("buyer@example.com", "role-pass-1", app_metadata={"role": "demand"}, role="tanker")
    assert _login(client, "buyer@example.com").status_code == 200
    with client.session_transaction() as s:
        assert s["role"] == "demand"


def test_public_role_fallback_for_accounts_not_yet_migrated(client, app_module):
    app_module.supabase.auth.add_user("legacy@example.com", "role-pass-1", role="demand")
    assert _login(client, "legacy@example.com").status_code == 200


def test_sql_copies_only_public_roles():
    sql = (ROOT / "supabase/roles_app_metadata.sql").read_text().lower()
    assert "before insert on auth.users" in sql
    assert "in ('demand', 'stp', 'tanker')" in sql
    executable = "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))
    writes = executable.split("select id, email")[0]       # steps 1-2, before the report query
    assert "admin" not in writes
