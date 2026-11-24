"""Optional two-step sign-in for demand / plant / tanker accounts (Profile)."""
import time

import pytest

import security

ORIGIN = {"Origin": "http://localhost"}


def _code(secret, offset=0):
    return security.totp_code(secret, int(time.time() // 30) + offset)


@pytest.fixture()
def buyer(app_module):
    app_module.save_admin_mfa([])
    app_module.supabase.auth.add_user("buyer@example.com", "buyer-pass-12", role="demand")
    return app_module


def _password(client):
    return client.post("/login", data={"login_identifier": "buyer@example.com", "password": "buyer-pass-12"})


def _turn_on(client):
    """Sign in with the password and turn two-step on from Profile."""
    assert _password(client).headers["Location"].endswith("/demand")
    assert client.get("/api/mfa").get_json()["enabled"] is False
    setup = client.post("/api/mfa/setup", json={}, headers=ORIGIN).get_json()
    secret = setup["secret"].replace(" ", "")
    assert setup["otpauth"].startswith("otpauth://totp/ReFlow:") and secret in setup["otpauth"]
    res = client.post("/api/mfa/enable", json={"code": _code(secret)}, headers=ORIGIN)
    assert res.status_code == 200
    assert client.get("/api/mfa").get_json()["enabled"] is True
    return secret


def test_off_by_default_password_is_enough(client, buyer):
    assert _password(client).headers["Location"].endswith("/demand")
    status = client.get("/api/mfa").get_json()
    assert status["enabled"] is False and status["required"] is False


def test_wrong_setup_code_does_not_turn_it_on(client, buyer):
    _password(client)
    secret = client.post("/api/mfa/setup", json={}, headers=ORIGIN).get_json()["secret"].replace(" ", "")
    wrong = "000000" if _code(secret) != "000000" else "111111"
    assert client.post("/api/mfa/enable", json={"code": wrong}, headers=ORIGIN).status_code == 400
    assert client.get("/api/mfa").get_json()["enabled"] is False


def test_turned_on_sign_in_needs_code(buyer, app_module):
    secret = _turn_on(app_module.app.test_client())
    c = app_module.app.test_client()
    res = _password(c)
    assert res.headers["Location"].endswith("/mfa")
    with c.session_transaction() as s:
        assert "user_id" not in s and "role" not in s
    assert c.get("/api/my_orders").status_code in (302, 401)
    page = c.get("/mfa").get_data(as_text=True)
    assert "Enter your code" in page and "Admin console" not in page
    ok = c.post("/mfa", data={"code": _code(secret, 1)}, headers=ORIGIN)
    assert ok.headers["Location"].endswith("/demand")
    with c.session_transaction() as s:
        assert s["role"] == "demand" and s["mfa_ok"] is True


def test_user_cannot_use_admin_code_page(buyer, app_module):
    _turn_on(app_module.app.test_client())
    c = app_module.app.test_client()
    _password(c)
    assert b"timed out" in c.get("/admin/mfa").data


def test_api_login_needs_code_when_on(buyer, app_module):
    secret = _turn_on(app_module.app.test_client())
    c = app_module.app.test_client()
    body = {"email": "buyer@example.com", "password": "buyer-pass-12"}
    res = c.post("/api/login", json=body)
    assert res.status_code == 401 and res.get_json()["mfa_required"] is True
    with c.session_transaction() as s:
        assert "user_id" not in s
    assert c.post("/api/login", json={**body, "code": _code(secret, 1)}).status_code == 200


def test_turning_off_needs_a_current_code(buyer, app_module):
    c = app_module.app.test_client()
    secret = _turn_on(c)
    assert c.post("/api/mfa/disable", json={}, headers=ORIGIN).status_code == 400
    assert c.get("/api/mfa").get_json()["enabled"] is True
    assert c.post("/api/mfa/disable", json={"code": _code(secret, 1)}, headers=ORIGIN).status_code == 200
    assert c.get("/api/mfa").get_json()["enabled"] is False
    c2 = app_module.app.test_client()
    assert _password(c2).headers["Location"].endswith("/demand")


def test_admins_cannot_turn_it_off(app_module):
    from tests.conftest import login_as
    c = login_as(app_module.app.test_client(), user_id="adm", role="admin", mfa_ok=True, auth_at=time.time())
    assert c.get("/api/mfa").get_json()["required"] is True
    assert c.post("/api/mfa/disable", json={"code": "123456"}, headers=ORIGIN).status_code == 403


# ---- Existing plant and tanker accounts --------------------------------------

def _enrol_directly(app_module, user_id, email):
    secret = security.new_totp_secret()
    app_module._save_mfa_enrolment(user_id, email, secret, int(time.time() // 30) - 5)
    return secret


@pytest.fixture()
def plant(app_module):
    app_module.save_admin_mfa([])
    uid = app_module.supabase.auth.add_user("plant@example.com", "plant-pass-12", role="stp", stp_id="PSTP001")
    app_module.save_stp_accounts([{"link_id": f"PLA-{uid}", "user_id": uid, "email": "plant@example.com",
                                   "stp_id": "PSTP001", "status": "approved"}])
    return uid


@pytest.fixture()
def tanker(app_module, monkeypatch):
    app_module.save_admin_mfa([])
    uid = app_module.supabase.auth.add_user("fleet@example.com", "fleet-pass-12", role="tanker")
    operator = {"operator_id": "OP-T-1", "operator_name": "Test Fleet", "phone": "9000012345",
                "verification_status": "approved", "email": "fleet@example.com"}
    monkeypatch.setattr(app_module, "get_tanker_operator_by_email",
                        lambda e: operator if e == "fleet@example.com" else None)
    return uid


def test_existing_plant_signs_in_as_usual(app_module, plant):
    c = app_module.app.test_client()
    res = c.post("/login", data={"login_identifier": "plant@example.com", "password": "plant-pass-12"})
    assert "/supply" in res.headers["Location"] and "stp_id=PSTP001" in res.headers["Location"]


def test_plant_with_code_returns_to_its_own_plant_page(app_module, plant):
    secret = _enrol_directly(app_module, plant, "plant@example.com")
    c = app_module.app.test_client()
    res = c.post("/login", data={"login_identifier": "plant@example.com", "password": "plant-pass-12"})
    assert res.headers["Location"].endswith("/mfa")
    res = c.post("/mfa", data={"code": _code(secret)}, headers=ORIGIN)
    assert res.headers["Location"] == "/supply?stp_id=PSTP001"
    with c.session_transaction() as s:
        assert s["role"] == "stp" and s["stp_id"] == "PSTP001"


def test_existing_tanker_signs_in_as_usual_and_with_code(app_module, tanker):
    c = app_module.app.test_client()
    form = {"login_identifier": "fleet@example.com", "password": "fleet-pass-12"}
    assert c.post("/login", data=form).headers["Location"].endswith("/tanker")
    secret = _enrol_directly(app_module, tanker, "fleet@example.com")
    c2 = app_module.app.test_client()
    assert c2.post("/login", data=form).headers["Location"].endswith("/mfa")
    assert c2.post("/mfa", data={"code": _code(secret)}, headers=ORIGIN).headers["Location"].endswith("/tanker")
    with c2.session_transaction() as s:
        assert s["tanker_operator_id"] == "OP-T-1"


def test_wrong_password_unchanged(client, buyer):
    page = client.post("/login", data={"login_identifier": "buyer@example.com", "password": "nope-nope-12"})
    assert b"Invalid email or password" in page.data or b"incorrect" in page.data.lower()
