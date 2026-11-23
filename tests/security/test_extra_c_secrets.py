"""Extra C: no default secret key; in production the OCEMS key secret is
required before new keys are stored (existing keys keep working)."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

import ocems_api

ROOT = Path(__file__).resolve().parents[2]
PLANT = {"user_id": "p-c", "role": "stp", "stp_id": "PSTP001", "selected_stp_id": "PSTP001"}


def test_app_refuses_to_start_without_flask_secret(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "FLASK_SECRET_KEY"}
    env["FLASK_SECRET_KEY"] = ""
    # config.py alone: importing app.py would do far more than this test needs
    res = subprocess.run([sys.executable, "-c", "import dotenv; dotenv.load_dotenv=lambda *a, **k: None; import config"],
                         cwd=ROOT, env=env, capture_output=True, text=True)
    assert res.returncode != 0 and "FLASK_SECRET_KEY is not set" in res.stderr


def test_production_without_ocems_secret_fails_closed(monkeypatch, as_user):
    old = ocems_api.encrypt_key("k-1")
    monkeypatch.setenv("CONTAINER_APP_NAME", "reflow")
    monkeypatch.delenv("OCEMS_KEY_SECRET", raising=False)
    assert ocems_api.missing_production_key_secret()
    with pytest.raises(ocems_api.OcemsApiError):
        ocems_api.encrypt_key("k-2")
    res = as_user(**PLANT).post("/api/ocems/connection", json={"base_url": "https://x.tratasoft.com", "api_key": "k"},
                                headers={"Origin": "http://localhost"})
    assert res.status_code == 503
    monkeypatch.setenv("OCEMS_KEY_SECRET", "test-only-ocems-key-secret-0123456789abcdef")
    assert ocems_api.decrypt_key(old) == "k-1"


def test_local_without_ocems_secret_still_works(monkeypatch):
    monkeypatch.delenv("CONTAINER_APP_NAME", raising=False)
    monkeypatch.delenv("REFLOW_ENV", raising=False)
    monkeypatch.delenv("OCEMS_KEY_SECRET", raising=False)
    assert not ocems_api.missing_production_key_secret()
    assert ocems_api.decrypt_key(ocems_api.encrypt_key("k-3")) == "k-3"
