"""Extra E: security headers on every response; HSTS only over HTTPS."""
import pytest

import security

PATHS = ["/", "/login", "/api/stps", "/api/current_user", "/health", "/static/brand-mark.svg"]


@pytest.mark.parametrize("path", PATHS)
def test_headers_present(client, path):
    h = client.get(path).headers
    csp = h["Content-Security-Policy"]
    for part in ("default-src 'self'", "frame-ancestors 'none'", "object-src 'none'", "base-uri 'self'", "form-action 'self'"):
        assert part in csp
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["X-Frame-Options"] == "DENY"
    assert h["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "camera=()" in h["Permissions-Policy"]


def test_csp_allows_only_known_hosts():
    hosts = {tok for d in security.CONTENT_SECURITY_POLICY.split(";") for tok in d.split()[1:] if tok.startswith("https://")}
    # Fonts are self-hosted (static/fonts): no Google Fonts.
    assert hosts == {"https://cdn.jsdelivr.net", "https://cdnjs.cloudflare.com",
                     "https://tile.openstreetmap.org", "https://*.tile.openstreetmap.org",
                     "https://nominatim.openstreetmap.org", "https://router.project-osrm.org"}
    assert "'unsafe-eval'" not in security.CONTENT_SECURITY_POLICY


def test_hsts_only_over_https(client):
    assert "Strict-Transport-Security" not in client.get("/").headers
    https = client.get("/", headers={"X-Forwarded-Proto": "https", "X-Forwarded-For": "203.0.113.5"})
    assert https.headers["Strict-Transport-Security"].startswith("max-age=31536000")


def test_errors_carry_headers_too(client):
    res = client.get("/no-such-page-xyz")
    assert res.headers.get("X-Content-Type-Options") == "nosniff"


def test_cdn_files_have_subresource_integrity():
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    for t in root.glob("templates/*.html"):
        for tag in re.findall(r"<(?:script|link)[^>]+(?:src|href)=\"https://(?:cdn\.jsdelivr\.net|cdnjs\.cloudflare\.com|unpkg\.com)[^>]*>", t.read_text()):
            assert 'integrity="sha' in tag and 'crossorigin="anonymous"' in tag, (t.name, tag)


def _script_src(res):
    import re
    return re.search(r"script-src([^;]*)", res.headers["Content-Security-Policy"]).group(1)


def test_script_src_has_no_unsafe_inline(client):
    for path in ("/", "/login", "/signup", "/api/stps"):
        src = _script_src(client.get(path))
        assert "'unsafe-inline'" not in src and "'unsafe-eval'" not in src and "'nonce-" in src


def test_every_inline_script_carries_this_requests_nonce(as_user):
    import re
    pages = [(as_user(), "/login"), (as_user(), "/signup"),
             (as_user(user_id="s", role="superadmin"), "/admin"),
             (as_user(user_id="s", role="superadmin"), "/admin/tanker/operator/NOPE")]
    for c, path in pages:
        res = c.get(path)
        if res.status_code != 200:
            continue
        html = res.get_data(as_text=True)
        nonce = re.search(r"'nonce-([^']+)'", res.headers["Content-Security-Policy"]).group(1)
        scripts = re.findall(r"<script\b[^>]*>", html)
        assert scripts, path
        for tag in scripts:
            assert f'nonce="{nonce}"' in tag, (path, tag)


def test_nonce_changes_per_request(client):
    import re
    a = re.search(r"'nonce-([^']+)'", client.get("/login").headers["Content-Security-Policy"]).group(1)
    b = re.search(r"'nonce-([^']+)'", client.get("/login").headers["Content-Security-Policy"]).group(1)
    assert a != b and len(a) >= 20


def test_spa_shell_inline_script_allowed_by_hash(client, app_module):
    import security
    html = open(app_module.SPA_INDEX, encoding="utf-8").read()
    for h in security.inline_script_hashes(html):
        assert h in _script_src(client.get("/"))


def test_no_inline_event_handlers_in_templates():
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    for t in root.glob("templates/*.html"):
        assert not re.search(r"\son[a-z]+\s*=\s*[\"']", t.read_text()), t.name
