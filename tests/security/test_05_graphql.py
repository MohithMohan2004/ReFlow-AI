"""Item 5: the app never uses GraphQL, and the hardening SQL removes the
Supabase GraphQL endpoint from the public roles."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_app_never_calls_graphql(app_module):
    for path in [ROOT / "app.py", *ROOT.glob("frontend/src/**/*.ts*"), *ROOT.glob("templates/*.html")]:
        assert "graphql" not in path.read_text(errors="ignore").lower(), path
    assert not [r.rule for r in app_module.app.url_map.iter_rules() if "graphql" in r.rule]


def test_hardening_sql_revokes_graphql_from_public_roles():
    sql = (ROOT / "supabase" / "security_hardening.sql").read_text().lower()
    assert re.search(r"revoke usage on schema graphql from anon, authenticated", sql)
