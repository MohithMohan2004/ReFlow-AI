"""Admin two-step sign-in (TOTP): a password alone never opens the console."""
import base64
import csv
import time

import pytest

import security

ORIGIN = {"Origin": "http://localhost"}


@pytest.fixture()
def admin(app_module):
    app_module.save_admin_mfa([])
    app_module.supabase.auth.add_user("boss@example.com", "boss-pass-12", app_metadata={"role": "superadmin"})
    return app_module


def _password(client):
    return client.post("/login", data={"login_identifier": "boss@example.com", "password": "boss-pass-12"})


def _pending_secret(client):
    with client.session_transaction() as s:
        return s["mfa_pending"].get("enroll_secret")


def _code(secret, offset=0):
    return security.totp_code(secret, int(time.time() // 30) + offset)


def _enrol(client):
    _password(client)
    client.get("/admin/mfa")
    secret = _pending_secret(client)
    assert client.post("/admin/mfa", data={"code": _code(secret)}, headers=ORIGIN).headers["Location"].endswith("/admin")
    return secret


def test_rfc6238_vectors():
    secret = base64.b32encode(b"12345678901234567890").decode().rstrip("=")
    assert security.totp_code(secret, 59 // 30) == "287082"
    assert security.totp_code(secret, 1111111109 // 30) == "081804"
    assert security.totp_code(secret, 20000000000 // 30) == "353130"


def test_password_alone_does_not_open_console(client, admin):
    res = _password(client)
    assert res.headers["Location"].endswith("/admin/mfa")
    with client.session_transaction() as s:
        assert "user_id" not in s and "role" not in s
    assert client.get("/admin").status_code == 302 and "/login" in client.get("/admin").headers["Location"]


def test_enrolment_then_login_with_code(client, admin, app_module):
    page = (_password(client), client.get("/admin/mfa"))[1].get_data(as_text=True)
    secret = _pending_secret(client)
    assert "Set up two-step sign-in" in page and secret[:4] in page
    bad = client.post("/admin/mfa", data={"code": "000000" if _code(secret) != "000000" else "111111"}, headers=ORIGIN)
    assert "That code" in bad.get_data(as_text=True)
    ok = client.post("/admin/mfa", data={"code": _code(secret)}, headers=ORIGIN)
    assert ok.headers["Location"].endswith("/admin")
    assert client.get("/admin").status_code == 200
    with open(app_module.ADMIN_MFA_FILE, newline="") as f:
        row = next(csv.DictReader(f))
    assert secret not in row["secret_enc"] and security.decrypt_mfa_secret(row["secret_enc"]) == secret


def test_returning_admin_needs_code_and_codes_work_once(admin, app_module):
    secret = _enrol(app_module.app.test_client())
    c = app_module.app.test_client()
    _password(c)
    page = c.get("/admin/mfa").get_data(as_text=True)
    assert "Enter your code" in page and secret[:4] not in page          # secret never shown again
    used = _code(secret)                                                 # same step as enrolment
    assert "That code" in c.post("/admin/mfa", data={"code": used}, headers=ORIGIN).get_data(as_text=True)
    assert c.post("/admin/mfa", data={"code": _code(secret, 1)}, headers=ORIGIN).headers["Location"].endswith("/admin")


def test_five_wrong_codes_lock(admin, app_module):
    secret = _enrol(app_module.app.test_client())
    c = app_module.app.test_client()
    _password(c)
    wrong = "123456" if _code(secret, 1) != "123456" else "654321"
    for _ in range(5):
        res = c.post("/admin/mfa", data={"code": wrong}, headers=ORIGIN)
    assert "Too many wrong codes" in res.get_data(as_text=True)
    c2 = app_module.app.test_client()
    _password(c2)
    res = c2.post("/admin/mfa", data={"code": _code(secret, 1)}, headers=ORIGIN)
    assert "Too many wrong codes" in res.get_data(as_text=True)
    with c2.session_transaction() as s:
        assert "user_id" not in s


def test_pending_sign_in_expires(client, admin, monkeypatch):
    _password(client)
    later = time.time() + security.MFA_PENDING_SECONDS + 5
    monkeypatch.setattr(time, "time", lambda: later)
    assert b"timed out" in client.get("/admin/mfa").data


def test_admin_session_without_code_or_too_old_is_ended(app_module):
    from tests.conftest import login_as
    c = login_as(app_module.app.test_client(), user_id="old-admin", role="superadmin")   # pre-MFA session
    assert c.get("/admin").status_code == 302
    with c.session_transaction() as s:
        assert "user_id" not in s
    old = login_as(app_module.app.test_client(), user_id="a", role="admin", mfa_ok=True,
                   auth_at=time.time() - security.ADMIN_SESSION_SECONDS - 60)
    assert old.get("/api/track_order?order_id=x").status_code == 401


def test_api_login_refuses_admins(client, admin):
    res = client.post("/api/login", json={"email": "boss@example.com", "password": "boss-pass-12"})
    assert res.status_code == 403 and "website" in res.get_json()["message"]


def test_code_posts_are_rate_limited(client, admin):
    _password(client)
    codes = [client.post("/admin/mfa", data={"code": "000000"}, headers=ORIGIN).status_code for _ in range(12)]
    assert 429 in codes
