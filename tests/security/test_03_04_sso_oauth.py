"""Items 3 and 4: there is no SAML/SSO and no OAuth login, so neither a
signature-wrapping bypass nor an email-claim spoof has a code path. These
tests fail if such a path is added without revisiting the report."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCES = [ROOT / "app.py", ROOT / "security.py", ROOT / "requirements.txt",
           *ROOT.glob("chatbot/**/*.py"), *ROOT.glob("frontend/src/**/*.ts*"), *ROOT.glob("templates/*.html")]


def _grep(pattern):
    rx = re.compile(pattern, re.I)
    return [str(p.relative_to(ROOT)) for p in SOURCES if rx.search(p.read_text(errors="ignore"))]


def test_no_saml_or_sso_code(app_module):
    assert _grep(r"saml|onelogin|xmlsec|sign_in_with_sso") == []
    assert not [r.rule for r in app_module.app.url_map.iter_rules() if re.search(r"saml|sso|acs|metadata", r.rule, re.I)]


def test_no_oauth_login_path(app_module):
    assert _grep(r"sign_in_with_oauth|exchange_code_for_session|provider_token|signInWithOAuth") == []
    assert not [r.rule for r in app_module.app.url_map.iter_rules() if re.search(r"oauth|callback", r.rule, re.I)]


def test_session_identity_is_the_supabase_user_id_not_the_email(client, app_module):
    uid = app_module.supabase.auth.add_user("owner@example.com", "owner-password-1", role="demand")
    client.post("/api/login", json={"email": "owner@example.com", "password": "owner-password-1"})
    with client.session_transaction() as s:
        assert s["user_id"] == uid
