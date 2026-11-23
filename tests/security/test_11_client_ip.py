"""Item 11: a fake X-Forwarded-For chain can't dodge the rate limiter. Only
the last hop (added by the Azure ingress) counts."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REAL = "203.0.113.7"   # what the ingress appends: the client's real address


def test_fake_forwarded_chain_still_blocked(client):
    codes = []
    for i in range(12):
        spoofed = f"10.{i}.{i}.{i}, 198.51.100.{i}"
        codes.append(client.post("/api/login", json={"email": f"u{i}@example.com", "password": "wrong-password"},
                                 headers={"X-Forwarded-For": f"{spoofed}, {REAL}"}).status_code)
    assert 429 in codes and codes.index(429) == 10


def test_different_real_clients_are_counted_separately(client):
    for i in range(10):
        client.post("/api/login", json={"email": f"a{i}@example.com", "password": "x" * 8},
                    headers={"X-Forwarded-For": REAL})
    other = client.post("/api/login", json={"email": "b@example.com", "password": "x" * 8},
                        headers={"X-Forwarded-For": "203.0.113.99"})
    assert other.status_code != 429


def test_remote_addr_is_the_last_hop(app_module):
    from werkzeug.middleware.proxy_fix import ProxyFix
    from werkzeug.test import EnvironBuilder

    pf = app_module.app.wsgi_app
    assert isinstance(pf, ProxyFix)
    assert (pf.x_for, pf.x_proto, pf.x_host, pf.x_port, pf.x_prefix) == (1, 1, 0, 0, 0)

    seen = {}

    def capture(environ, start_response):
        seen.update(ip=environ["REMOTE_ADDR"], scheme=environ["wsgi.url_scheme"], host=environ["HTTP_HOST"])
        start_response("200 OK", [])
        return [b""]

    same = ProxyFix(capture, x_for=pf.x_for, x_proto=pf.x_proto, x_host=pf.x_host, x_port=pf.x_port, x_prefix=pf.x_prefix)
    env = EnvironBuilder(path="/", headers={"X-Forwarded-For": f"1.1.1.1, {REAL}", "X-Forwarded-Proto": "https",
                                            "X-Forwarded-Host": "evil.example"}).get_environ()
    same(env, lambda *a: None)
    assert seen == {"ip": REAL, "scheme": "https", "host": "localhost"}


def test_no_raw_forwarded_header_reads():
    for name in ("app.py", "security.py"):
        src = (ROOT / name).read_text()
        assert not re.search(r"""headers(\.get)?\(?\[?["']X-(Forwarded-For|Real-IP)""", src, re.I), name
