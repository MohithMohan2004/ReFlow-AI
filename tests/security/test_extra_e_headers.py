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
    assert hosts == {"https://cdn.jsdelivr.net", "https://cdnjs.cloudflare.com", "https://fonts.googleapis.com",
                     "https://fonts.gstatic.com", "https://tile.openstreetmap.org", "https://*.tile.openstreetmap.org",
                     "https://nominatim.openstreetmap.org", "https://router.project-osrm.org"}
    assert "'unsafe-eval'" not in security.CONTENT_SECURITY_POLICY


def test_hsts_only_over_https(client):
    assert "Strict-Transport-Security" not in client.get("/").headers
    https = client.get("/", headers={"X-Forwarded-Proto": "https", "X-Forwarded-For": "203.0.113.5"})
    assert https.headers["Strict-Transport-Security"].startswith("max-age=31536000")


def test_errors_carry_headers_too(client):
    res = client.get("/no-such-page-xyz")
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
