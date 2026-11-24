"""Extra A follow-up: a plant account only works after an admin approves it."""
import pytest

ORIGIN = {"Origin": "http://localhost"}
SIGNUP = dict(accept_terms="yes", first_name="Mallory", last_name="M", mobile="9000012345", username="mallory", role="stp",
              stp_id="PSTP001", password="plant-pass-1", confirm_password="plant-pass-1")
ADMIN = dict(user_id="adm-1", role="admin", user_email="admin@example.com")


@pytest.fixture()
def fresh(app_module):
    app_module.save_stp_accounts([])
    return app_module


def _row(app_module, email):
    return next(r for r in app_module.load_stp_accounts() if r["email"] == email)


def _login(client, email, password="plant-pass-1"):
    return client.post("/api/login", json={"email": email, "password": password})


def test_signup_files_pending_request_and_cannot_sign_in(client, fresh):
    res = client.post("/api/signup", json=dict(SIGNUP, email="mallory@example.com"))
    assert res.status_code == 201 and "approve" in res.get_json()["message"]
    assert _row(fresh, "mallory@example.com")["status"] == "pending"
    res = _login(client, "mallory@example.com")
    assert res.status_code == 403 and "waiting for approval" in res.get_json()["message"]
    with client.session_transaction() as s:
        assert "user_id" not in s


def test_web_signup_and_login_also_wait(client, fresh):
    res = client.post("/signup", data=dict(SIGNUP, email="web-plant@example.com"))
    assert res.status_code == 302 and res.headers["Location"].endswith("/login")
    assert b"approve your access" in client.get("/login").data
    page = client.post("/login", data={"login_identifier": "web-plant@example.com", "password": "plant-pass-1"})
    assert b"waiting for approval" in page.data


def test_pending_plant_user_cannot_touch_the_plant(client, fresh, as_user):
    client.post("/api/signup", json=dict(SIGNUP, email="m2@example.com"))
    _login(client, "m2@example.com")
    res = client.post("/api/update_pricing", json={"stp_id": "PSTP001", "base_price_per_kld": 1}, headers=ORIGIN)
    assert res.status_code in (401, 403)


def test_admin_approval_then_login_uses_the_approved_plant(client, fresh, as_user):
    client.post("/api/signup", json=dict(SIGNUP, email="owner@example.com"))
    row = _row(fresh, "owner@example.com")
    # the user later edits their own metadata to point at another plant
    fresh.supabase.auth.users["owner@example.com"]["user_metadata"]["stp_id"] = "PSTP002"
    res = as_user(**ADMIN).post(f"/admin/stp_account/{row['link_id']}/approved", headers=ORIGIN)
    assert res.status_code == 302 and _row(fresh, "owner@example.com")["status"] == "approved"
    assert _login(client, "owner@example.com").status_code == 200
    with client.session_transaction() as s:
        assert s["stp_id"] == "PSTP001"


def test_existing_account_without_request_gets_queued(client, fresh):
    fresh.supabase.auth.add_user("old-plant@example.com", "plant-pass-1", role="stp", stp_id="PSTP003")
    assert _login(client, "old-plant@example.com").status_code == 403
    assert _row(fresh, "old-plant@example.com")["status"] == "pending"
    assert _row(fresh, "old-plant@example.com")["stp_id"] == "PSTP003"


def test_rejected_request_says_so(client, fresh, as_user):
    client.post("/api/signup", json=dict(SIGNUP, email="nope@example.com"))
    as_user(**ADMIN).post(f"/admin/stp_account/{_row(fresh, 'nope@example.com')['link_id']}/rejected", headers=ORIGIN)
    assert "not approved" in _login(client, "nope@example.com").get_json()["message"]


def test_revoking_signs_out_an_open_session(as_user, fresh):
    plant = as_user(user_id="p-rev", role="stp", stp_id="PSTP001", selected_stp_id="PSTP001")
    assert plant.get("/api/stp_orders").status_code == 200
    as_user(**ADMIN).post("/admin/stp_account/PLA-p-rev/rejected", headers=ORIGIN)
    assert plant.get("/api/stp_orders").status_code == 401
    with plant.session_transaction() as s:
        assert "user_id" not in s


def test_session_without_approval_is_signed_out(app_module, fresh):
    from tests.conftest import login_as
    c = login_as(app_module.app.test_client(), user_id="p-old", role="stp", stp_id="PSTP001")
    assert c.get("/api/supply/overview").status_code == 401


def test_only_approvals_admins_can_decide(client, fresh, as_user):
    client.post("/api/signup", json=dict(SIGNUP, email="x@example.com"))
    link = _row(fresh, "x@example.com")["link_id"]
    as_user(user_id="b", role="demand").post(f"/admin/stp_account/{link}/approved", headers=ORIGIN)
    as_user(user_id="p", role="stp", stp_id="PSTP002").post(f"/admin/stp_account/{link}/approved", headers=ORIGIN)
    assert _row(fresh, "x@example.com")["status"] == "pending"
    assert as_user(**ADMIN).get(f"/admin/stp_account/{link}/approved").status_code == 405


def test_admin_page_lists_requests(client, fresh, as_user):
    client.post("/api/signup", json=dict(SIGNUP, email="listme@example.com"))
    page = as_user(**ADMIN).get("/admin").get_data(as_text=True)
    assert "Plant accounts" in page and "listme@example.com" in page
