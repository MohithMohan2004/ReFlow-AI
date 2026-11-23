"""Item 8: the app decodes no JWTs; its only token is Flask's signed session
cookie. Unsigned, tampered, wrong-key and expired cookies must not log in."""
import base64
import json
import time
from pathlib import Path

from flask.sessions import SecureCookieSessionInterface
from itsdangerous import URLSafeTimedSerializer

ROOT = Path(__file__).resolve().parents[2]
ADMIN = {"user_id": "attacker", "role": "superadmin"}


def _logged_in(client, cookie):
    client.set_cookie("session", cookie)
    return client.get("/api/current_user").get_json()["logged_in"]


def _signer(app, secret=None):
    si = SecureCookieSessionInterface()
    if secret is None:
        return si.get_signing_serializer(app)
    return URLSafeTimedSerializer(secret, salt=si.salt, serializer=si.serializer,
                                  signer_kwargs={"key_derivation": si.key_derivation, "digest_method": si.digest_method})


def test_valid_cookie_works(client, app_module):
    assert _logged_in(client, _signer(app_module.app).dumps(ADMIN))


def test_unsigned_cookie_alg_none_style_is_rejected(client):
    body = base64.urlsafe_b64encode(json.dumps(ADMIN).encode()).decode().rstrip("=")
    assert not _logged_in(client, body)
    assert not _logged_in(client, body + "..")


def test_tampered_payload_is_rejected(client, app_module):
    good = _signer(app_module.app).dumps({"user_id": "u1", "role": "demand"})
    payload, ts, sig = good.rsplit(".", 2)
    forged = base64.urlsafe_b64encode(json.dumps(ADMIN).encode()).decode().rstrip("=")
    assert not _logged_in(client, f"{forged}.{ts}.{sig}")


def test_cookie_signed_with_another_key_is_rejected(client, app_module):
    assert not _logged_in(client, _signer(app_module.app, "some-other-secret").dumps(ADMIN))


def test_expired_cookie_is_rejected(client, app_module, monkeypatch):
    lifetime = app_module.app.permanent_session_lifetime.total_seconds()
    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() - lifetime - 60)
    old = _signer(app_module.app).dumps(ADMIN)
    monkeypatch.setattr(time, "time", real_time)
    assert not _logged_in(client, old)


def test_no_jwt_decoding_in_app_code():
    for name in ("app.py", "security.py", "store.py", "ocems_api.py", "config.py"):
        src = (ROOT / name).read_text()
        assert "jwt." not in src and "import jwt" not in src, name
