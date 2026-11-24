"""Item 20: look-alike identities normalise to the same string and can't
create a second account or sign in as someone else."""
import security

BASE = dict(accept_terms="yes", first_name="Big", last_name="Bird", mobile="9000012345", role="demand",
            password="bird-password-1", confirm_password="bird-password-1")


def test_normalize_identity():
    assert security.normalize_identity("ᴮᴵᴳᴮᴵᴿᴰ") == "bigbird"
    assert security.normalize_identity("ＢＩＧＢＩＲＤ") == "bigbird"
    assert security.normalize_identity("  BigBird ") == "bigbird"
    assert security.normalize_identity("ﬁsh") == "fish"


def test_superscript_lookalike_cannot_sign_up_when_bigbird_exists(client, app_module):
    app_module.supabase.auth.add_user("bigbird@example.com", "original-password", role="demand", username="bigbird")
    res = client.post("/api/signup", json=dict(BASE, email="ᴮᴵᴳᴮᴵᴿᴰ@example.com", username="ᴮᴵᴳᴮᴵᴿᴰ"))
    assert res.status_code == 400
    assert "already registered" in res.get_json()["message"]
    assert list(app_module.supabase.auth.users) == ["bigbird@example.com"]


def test_web_signup_lookalike_also_refused(client, app_module):
    app_module.supabase.auth.add_user("bigbird@example.com", "original-password", role="demand")
    client.post("/signup", data=dict(BASE, email="ＢＩＧＢＩＲＤ@example.com", username="bigbird2"))
    assert list(app_module.supabase.auth.users) == ["bigbird@example.com"]


def test_cyrillic_lookalikes_rejected(client, app_module):
    res = client.post("/api/signup", json=dict(BASE, email="bіgbird@example.com", username="newbird"))  # Cyrillic і
    assert res.status_code == 400 and "plain letters" in res.get_json()["message"]
    res = client.post("/api/signup", json=dict(BASE, email="new@example.com", username="bіgbird"))
    assert res.status_code == 400 and "Usernames" in res.get_json()["message"]
    assert app_module.supabase.auth.users == {}


def test_lookalike_login_reaches_only_the_real_account(client, app_module):
    app_module.supabase.auth.add_user("bigbird@example.com", "original-password", role="demand")
    wrong = client.post("/api/login", json={"email": "ᴮᴵᴳᴮᴵᴿᴰ@example.com", "password": "guess-password"})
    assert wrong.status_code == 401
    assert ("sign_in", "bigbird@example.com") in app_module.supabase.auth.calls  # same account, same password check


def test_password_reset_request_reaches_only_the_real_account(client, app_module):
    """The reset flow (Supabase one-time link) normalises look-alikes to the
    real address; it can't be pointed at a second, look-alike account."""
    app_module.supabase.auth.add_user("bigbird@example.com", "bird-password-1")
    client.post("/forgot-password", data={"email": "ＢＩＧＢＩＲＤ@example.com"})
    assert ("reset_email", "bigbird@example.com") == app_module.supabase.auth.calls[-1][:2]


def test_profile_username_change_is_normalised_and_checked(as_user):
    c = as_user(user_id="u-20", role="demand", first_name="Big")
    assert c.post("/api/profile", json={"first_name": "Big", "username": "bіgbird"}).status_code == 400
    assert c.post("/api/profile", json={"first_name": "Big", "username": "ᴮᴵᴳᴮᴵᴿᴰ"}).status_code == 200
    with c.session_transaction() as s:
        assert s.get("username") == "bigbird"
