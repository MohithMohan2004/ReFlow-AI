"""Shared fixtures for the ReFlow test suite.

Safety rules (from task.md): tests never touch the real data files, never use
the real secrets, and never talk to Supabase, the OCEMS vendor or any other
outside service.

- The environment is fixed *before* app.py is imported: no DATABASE_URL (so no
  Postgres), throwaway secrets, and a dummy Supabase URL/key.
- `database/`, `data/` and `uploads/` are copied to a temporary folder and every
  path constant in app.py is pointed at the copy.
- Supabase is replaced by FakeSupabase; any socket to a non-local address fails.
"""

import os
import shutil
import socket
import sys
import tempfile
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ["DATABASE_URL"] = ""
os.environ["FLASK_SECRET_KEY"] = "test-only-flask-secret-key-0123456789abcdef"
os.environ["OCEMS_KEY_SECRET"] = "test-only-ocems-key-secret-0123456789abcdef"
os.environ["SUPABASE_URL"] = "http://127.0.0.1:9"
os.environ["SUPABASE_KEY"] = "sb_publishable_test_only_key"
os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:9/v1"
os.environ.setdefault("SESSION_COOKIE_SECURE", "0")


# ---------------------------------------------------------------------------
# Block outbound network: only loopback / unix sockets are allowed.
# ---------------------------------------------------------------------------
_real_connect = socket.socket.connect


def _guarded_connect(self, address):
    host = address[0] if isinstance(address, tuple) else address
    if isinstance(host, str) and host not in ("127.0.0.1", "::1", "localhost") and not host.startswith("/"):
        raise ConnectionRefusedError(f"tests may not connect to {host!r}")
    return _real_connect(self, address)


socket.socket.connect = _guarded_connect


def _no_dns(host, *args, **kwargs):
    if host in ("127.0.0.1", "::1", "localhost", None):
        return _real_getaddrinfo(host, *args, **kwargs)
    raise socket.gaierror(f"tests may not resolve {host!r}")


_real_getaddrinfo = socket.getaddrinfo
socket.getaddrinfo = _no_dns


# The OCEMS warmer polls the vendor every minute; never start it in tests.
import ocems_api  # noqa: E402

ocems_api.start_warmer = lambda *a, **k: None


# ---------------------------------------------------------------------------
# Fake Supabase
# ---------------------------------------------------------------------------
class FakeAuthError(Exception):
    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


class FakeAuth:
    """Just enough of supabase.auth for the login/signup routes."""

    def __init__(self):
        self.users = {}  # email -> dict(id, password, user_metadata, email_confirmed)
        self.calls = []

    def add_user(self, email, password, **metadata):
        uid = f"user-{len(self.users) + 1}"
        self.users[email] = {"id": uid, "password": password, "user_metadata": metadata}
        return uid

    def _user(self, record, email):
        return types.SimpleNamespace(id=record["id"], email=email, user_metadata=dict(record["user_metadata"]))

    def sign_in_with_password(self, creds):
        self.calls.append(("sign_in", creds.get("email")))
        record = self.users.get(creds.get("email"))
        if record is None or record["password"] != creds.get("password"):
            raise FakeAuthError("Invalid login credentials", "invalid_credentials")
        return types.SimpleNamespace(user=self._user(record, creds["email"]))

    def sign_up(self, payload):
        self.calls.append(("sign_up", payload.get("email")))
        email = payload["email"]
        if email in self.users:
            raise FakeAuthError("User already registered", "user_already_exists")
        meta = (payload.get("options") or {}).get("data") or {}
        self.add_user(email, payload["password"], **meta)
        return types.SimpleNamespace(user=self._user(self.users[email], email))

    def sign_out(self):
        return None


class FakeTable:
    def __init__(self, store, name):
        self.store, self.name = store, name

    def __getattr__(self, _name):
        def chain(*_a, **_k):
            return self
        return chain

    def execute(self):
        return types.SimpleNamespace(data=list(self.store.get(self.name, [])))


class FakeSupabase:
    def __init__(self):
        self.auth = FakeAuth()
        self.tables = {}

    def table(self, name):
        return FakeTable(self.tables, name)


# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def appmod(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("reflow-data")
    for folder in ("database", "data", "uploads"):
        src = ROOT / folder
        if src.exists():
            shutil.copytree(src, tmp / folder)
        else:
            (tmp / folder).mkdir()

    import app as A

    base = A.BASE_DIR
    for name, value in list(vars(A).items()):
        if isinstance(value, str) and value.startswith(base + os.sep):
            rel = os.path.relpath(value, base)
            if rel.split(os.sep)[0] in ("database", "data", "uploads"):
                setattr(A, name, str(tmp / rel))
    os.makedirs(A.TANKER_DOCUMENT_UPLOAD_FOLDER, exist_ok=True)

    A.supabase = FakeSupabase()
    A.juno_llm_gateway = None
    A.app.config["TESTING"] = True
    A.DATA_ROOT_FOR_TESTS = str(tmp)
    return A


@pytest.fixture()
def app_module(appmod):
    appmod.supabase = FakeSupabase()
    reset = getattr(appmod, "reset_rate_limits", None)
    if reset:
        reset()
    return appmod


@pytest.fixture()
def client(app_module):
    return app_module.app.test_client()


def login_as(client, **session_values):
    with client.session_transaction() as s:
        s.clear()
        s.update(session_values)
    return client


@pytest.fixture()
def as_user(app_module):
    def make(**session_values):
        return login_as(app_module.app.test_client(), **session_values)
    return make
