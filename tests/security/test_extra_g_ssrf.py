"""Extra G: the OCEMS URL can only reach the vendor's public servers."""
import socket

import pytest

import ocems_api


@pytest.mark.parametrize("url", [
    "http://x.tratasoft.com",                  # not https
    "https://tratasoft.com",                   # bare vendor domain
    "https://x.tratasoft.com.evil.com",        # suffix trick
    "https://evil.com/x.tratasoft.com",
    "https://x.tratasoft.com:8443",            # custom port
    "https://127.0.0.1",
    "https://169.254.169.254",                 # cloud metadata
    "https://localhost",
])
def test_bad_urls_rejected(url):
    with pytest.raises(ocems_api.OcemsApiError):
        ocems_api.normalise_base_url(url)


def test_userinfo_trick_is_rebuilt_to_vendor_host():
    assert ocems_api.normalise_base_url("https://evil.com@x.tratasoft.com/api") == "https://x.tratasoft.com"


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.5", "169.254.169.254", "192.168.1.1", "::1", "fd00::1", "100.64.0.1"])
def test_vendor_name_resolving_to_internal_ip_is_refused(monkeypatch, ip):
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(family, socket.SOCK_STREAM, 6, "", (ip, 443))])
    called = []
    monkeypatch.setattr(ocems_api.requests, "get", lambda *a, **k: called.append(a) or None)
    with pytest.raises(ocems_api.OcemsApiError):
        ocems_api._get_csv("https://evil.tratasoft.com", "key", "/api/data/single")
    assert called == []


def test_public_ip_passes_check_and_redirects_stay_off(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))])
    seen = {}

    class R:
        status_code, content, text, headers, encoding = 200, b"Date,pH\n", "Date,pH\n", {"Content-Type": "text/csv"}, "utf-8"

    def fake_get(url, **kw):
        seen.update(kw, url=url)
        return R()
    monkeypatch.setattr(ocems_api.requests, "get", fake_get)
    ocems_api._get_csv("https://x.tratasoft.com", "key", "/api/data/single")
    assert seen["url"] == "https://x.tratasoft.com/api/data/single"
    assert seen["allow_redirects"] is False and seen["timeout"]
