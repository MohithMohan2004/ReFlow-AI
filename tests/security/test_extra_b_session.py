"""Extra B: session cookie flags, lifetime, and a fresh session on login."""
from datetime import timedelta

import security


def test_secure_flag_defaults_on(monkeypatch):
    monkeypatch.delenv("SESSION_COOKIE_SECURE", raising=False)
    assert security.env_flag("SESSION_COOKIE_SECURE", True) is True
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    assert security.env_flag("SESSION_COOKIE_SECURE", True) is False
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "garbage")
    assert security.env_flag("SESSION_COOKIE_SECURE", True) is True


def test_cookie_flags_and_lifetime(app_module):
    cfg = app_module.app.config
    assert cfg["SESSION_COOKIE_HTTPONLY"] is True
    assert cfg["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert cfg["PERMANENT_SESSION_LIFETIME"] <= timedelta(days=7)


def test_set_cookie_header_has_flags(client, app_module, monkeypatch):
    monkeypatch.setitem(app_module.app.config, "SESSION_COOKIE_SECURE", True)
    app_module.supabase.auth.add_user("b1@example.com", "buyer-pass-1", role="demand")
    res = client.post("/api/login", json={"email": "b1@example.com", "password": "buyer-pass-1"})
    cookie = res.headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=Lax" in cookie and "Expires=" in cookie


def test_login_starts_a_fresh_session(as_user, app_module):
    c = as_user(user_id="old-user", role="superadmin", selected_stp_id="PSTP009", pending_order_draft={"x": 1})
    app_module.supabase.auth.add_user("b2@example.com", "buyer-pass-1", role="demand")
    c.post("/api/login", json={"email": "b2@example.com", "password": "buyer-pass-1"})
    with c.session_transaction() as s:
        assert s["role"] == "demand" and s["user_id"] != "old-user"
        assert "selected_stp_id" not in s and "pending_order_draft" not in s


def test_logout_clears_session(as_user):
    c = as_user(user_id="u1", role="demand")
    c.post("/api/logout", headers={"Origin": "http://localhost"})
    with c.session_transaction() as s:
        assert dict(s) == {}
