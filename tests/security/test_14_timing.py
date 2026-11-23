"""Item 14: a missing account and a wrong password look identical, and no
secret is compared with == ."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


class Err(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


@pytest.fixture()
def auth_errors(app_module, monkeypatch):
    def sign_in(creds):
        raise Err("user_not_found" if creds["email"].startswith("missing") else "invalid_credentials")
    monkeypatch.setattr(app_module.supabase.auth, "sign_in_with_password", sign_in)


def test_api_login_same_answer(client, auth_errors):
    a = client.post("/api/login", json={"email": "missing@example.com", "password": "whatever-1"})
    b = client.post("/api/login", json={"email": "exists@example.com", "password": "whatever-1"})
    assert (a.status_code, a.get_json()) == (b.status_code, b.get_json())


def test_web_login_same_answer(client, auth_errors):
    a = client.post("/login", data={"login_identifier": "missing@example.com", "password": "whatever-1"})
    b = client.post("/login", data={"login_identifier": "exists@example.com", "password": "whatever-1"})
    assert a.status_code == b.status_code
    assert a.data == b.data
    assert b"Invalid email or password." in a.data


def test_no_secret_compared_with_equals():
    for name in ("app.py", "ocems_api.py", "security.py", "store.py"):
        src = (ROOT / name).read_text()
        bad = re.findall(r"\b\w*(?:api_key|token|secret|signature|credential)\w*\s*[!=]=\s*\w+", src, re.I)
        bad = [b for b in bad if not re.search(r"is_link|== *None|!= *None", b)]
        assert bad == [], (name, bad)
