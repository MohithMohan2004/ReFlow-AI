"""Item 15: only authenticated encryption (Fernet) is used, every decrypt
failure gives one generic error, and keys can be rotated."""
import base64
import re
from pathlib import Path

import pytest

import ocems_api

ROOT = Path(__file__).resolve().parents[2]


def test_no_raw_cbc_anywhere():
    for path in [ROOT / "app.py", ROOT / "ocems_api.py", ROOT / "store.py", ROOT / "security.py",
                 *ROOT.glob("scripts/*.py"), *ROOT.glob("chatbot/**/*.py")]:
        src = path.read_text()
        assert not re.search(r"Cipher\(|modes\.CBC|AES\.new|Crypto\.Cipher", src), path


def test_round_trip():
    token = ocems_api.encrypt_key("secret-api-key-123")
    assert ocems_api.decrypt_key(token) == "secret-api-key-123"


@pytest.mark.parametrize("mangle", [
    lambda t: t[:-4] + ("AAAA" if not t.endswith("AAAA") else "BBBB"),        # MAC broken
    lambda t: base64.urlsafe_b64encode(base64.urlsafe_b64decode(t)[:-33] + b"\x00" * 33).decode(),  # padding/IV area
    lambda t: t[:20],                                                          # truncated
    lambda t: "not-a-token",
    lambda t: "",
])
def test_tampered_token_gives_generic_error(mangle):
    token = ocems_api.encrypt_key("secret-api-key-123")
    with pytest.raises(ocems_api.OcemsApiError) as e:
        ocems_api.decrypt_key(mangle(token))
    assert str(e.value) == ocems_api.KEY_UNREADABLE


def test_rotation_from_flask_secret_to_ocems_secret(monkeypatch):
    monkeypatch.delenv("OCEMS_KEY_SECRET", raising=False)
    old = ocems_api.encrypt_key("k-1")                 # stored before OCEMS_KEY_SECRET existed
    monkeypatch.setenv("OCEMS_KEY_SECRET", "brand-new-ocems-secret")
    assert ocems_api.decrypt_key(old) == "k-1"          # still readable
    new = ocems_api.rotate_key(old)
    monkeypatch.setenv("FLASK_SECRET_KEY", "flask-key-rotated-too")
    assert ocems_api.decrypt_key(new) == "k-1"          # readable with OCEMS_KEY_SECRET alone
    with pytest.raises(ocems_api.OcemsApiError):
        ocems_api.decrypt_key(old)
