"""Forgot password: Supabase emails a one-time link; ReFlow shows the form
and spends the token only when the new password is submitted."""
import re

import pytest

ORIGIN = {"Origin": "http://localhost"}


@pytest.fixture()
def auth(app_module, monkeypatch):
    fake = app_module.supabase.auth
    fake.add_user("ravi@example.com", "old-password-1", app_metadata={"role": "demand"})
    monkeypatch.setattr(app_module, "fresh_supabase_auth", lambda: fake)
    return fake


def _request_link(client, auth, email="ravi@example.com"):
    client.post("/forgot-password", data={"email": email}, headers=ORIGIN)
    return list(auth.reset_tokens)[-1]


def _reset(client, token, password="new-password-1", confirm=None):
    return client.post("/reset-password", headers=ORIGIN, data={
        "token_hash": token, "password": password,
        "confirm_password": password if confirm is None else confirm})


def test_same_reply_for_known_and_unknown_addresses(client, auth):
    known = client.post("/forgot-password", data={"email": "ravi@example.com"}, headers=ORIGIN)
    unknown = client.post("/forgot-password", data={"email": "nobody@example.com"}, headers=ORIGIN)
    assert known.status_code == unknown.status_code == 200
    strip = lambda r, who: re.sub(rb'nonce="[^"]+"', b"", r.data).replace(who, b"X@")
    assert strip(known, b"ravi@") == strip(unknown, b"nobody@")


def test_supabase_error_is_not_revealed(client, auth, monkeypatch):
    def boom(*_a, **_k):
        raise Exception("For security purposes, you can only request this after 60 seconds.")
    monkeypatch.setattr(auth, "reset_password_for_email", boom)
    res = client.post("/forgot-password", data={"email": "ravi@example.com"}, headers=ORIGIN)
    assert res.status_code == 200 and b"sent it a link" in res.data


def test_full_reset_changes_password_and_ends_sessions(client, app_module, auth):
    uid = auth.users["ravi@example.com"]["id"]
    epoch = app_module.session_epoch(uid)
    token = _request_link(client, auth)

    page = client.get(f"/reset-password?token_hash={token}&type=recovery")
    assert page.status_code == 200 and b"Choose a new password" in page.data
    assert token in auth.reset_tokens  # opening the link doesn't spend it

    res = _reset(client, token)
    assert res.status_code == 302 and res.headers["Location"].endswith("/login")
    assert auth.users["ravi@example.com"]["password"] == "new-password-1"
    assert app_module.session_epoch(uid) == epoch + 1

    # The link works once.
    again = _reset(client, token, "another-pass-1")
    assert b"expired or was already used" in again.data
    assert auth.users["ravi@example.com"]["password"] == "new-password-1"


def test_bad_input_keeps_the_token(client, auth):
    token = _request_link(client, auth)
    assert b"at least 8" in _reset(client, token, "short").data
    assert b"do not match" in _reset(client, token, "new-password-1", "new-password-2").data
    assert b"at most 72" in _reset(client, token, "x" * 80).data
    assert token in auth.reset_tokens
    assert _reset(client, token).status_code == 302


def test_forged_or_missing_token_refused(client, auth):
    assert b"expired or was already used" in _reset(client, "madeuptoken").data
    assert b"expired or was already used" in client.get("/reset-password").data
    assert b"expired or was already used" in client.get("/reset-password?token_hash=<script>").data
    assert auth.users["ravi@example.com"]["password"] == "old-password-1"


def test_same_password_sends_user_to_sign_in(client, auth):
    token = _request_link(client, auth)
    res = _reset(client, token, "old-password-1")
    assert res.status_code == 302 and res.headers["Location"].endswith("/login")


def test_reset_request_is_rate_limited(client, auth):
    codes = [client.post("/forgot-password", data={"email": f"r{i}@example.com"}, headers=ORIGIN).status_code
             for i in range(7)]
    assert 429 in codes


def test_login_page_links_to_reset(client):
    assert b'href="/forgot-password"' in client.get("/login").data
