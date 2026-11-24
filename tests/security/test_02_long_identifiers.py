"""Item 2: long identifiers never let a wrong password through, and
passwords bcrypt would truncate are refused."""

SIGNUP = dict(accept_terms="yes", first_name="Ravi", last_name="Kumar", mobile="9000012345",
              username="ravi", role="demand")


def test_long_username_wrong_password_is_rejected(client, app_module):
    long_name = "r" * 60
    email = f"{long_name}@example.com"
    app_module.supabase.auth.add_user(email, "correct-password-1", role="demand", username=long_name)

    res = client.post("/api/login", json={"email": email, "password": "wrong-password-1"})
    assert res.status_code == 401
    with client.session_transaction() as s:
        assert "user_id" not in s

    ok = client.post("/api/login", json={"email": email, "password": "correct-password-1"})
    assert ok.status_code == 200


def test_web_login_long_username_wrong_password(client, app_module):
    email = ("b" * 60) + "@example.com"
    app_module.supabase.auth.add_user(email, "correct-password-1", role="demand")
    res = client.post("/login", data={"login_identifier": email, "password": "wrong-password-1"})
    assert b"Invalid email or password." in res.data
    with client.session_transaction() as s:
        assert "user_id" not in s


def test_signup_rejects_password_over_72_bytes(client, app_module):
    pw = "é" * 37  # 37 characters, 74 bytes
    res = client.post("/api/signup", json=dict(SIGNUP, email="a@example.com", password=pw, confirm_password=pw))
    assert res.status_code == 400
    assert "72 bytes" in res.get_json()["message"]
    assert ("sign_up", "a@example.com") not in app_module.supabase.auth.calls


def test_signup_rejects_overlong_email_and_names(client):
    pw = "good-password-1"
    res = client.post("/api/signup", json=dict(SIGNUP, email=("e" * 250) + "@x.io", password=pw, confirm_password=pw))
    assert res.status_code == 400
    res = client.post("/api/signup", json=dict(SIGNUP, first_name="n" * 101, email="n@example.com", password=pw, confirm_password=pw))
    assert res.status_code == 400


def test_login_with_73_byte_password_is_refused_without_calling_supabase(client, app_module):
    res = client.post("/api/login", json={"email": "c@example.com", "password": "p" * 73})
    assert res.status_code == 401
    assert ("sign_in", "c@example.com") not in app_module.supabase.auth.calls
