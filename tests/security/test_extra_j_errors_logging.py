"""Extra J: no debug mode or stack traces for users, security events are
logged, and logs never contain passwords or OCEMS keys."""
import socket

import ocems_api


def test_debug_off(app_module):
    assert app_module.app.debug is False
    src = open(app_module.__file__).read()
    assert "debug=True" not in src


def test_unhandled_error_shows_no_traceback(app_module, monkeypatch):
    def boom():
        raise RuntimeError("secret-internal-detail /home/app/db.py line 42")
    monkeypatch.setitem(app_module.app.view_functions, "api_stps", boom)
    monkeypatch.setitem(app_module.app.config, "TESTING", False)
    monkeypatch.setitem(app_module.app.config, "PROPAGATE_EXCEPTIONS", False)
    res = app_module.app.test_client().get("/api/stps")
    body = res.get_data(as_text=True)
    assert res.status_code == 500
    assert "Traceback" not in body and "secret-internal-detail" not in body


def test_failed_login_logged_without_password(client, capsys):
    client.post("/api/login", json={"email": "victim@example.com", "password": "Sup3r-Secret-Pass"})
    out = capsys.readouterr().out
    assert "SECURITY event=login_failed" in out and "account=victim@example.com" in out
    assert "Sup3r-Secret-Pass" not in out


def test_permission_denied_and_csrf_logged(as_user, capsys):
    as_user(user_id="b", role="demand").get("/admin")
    as_user(user_id="a", role="admin").post("/admin/order/X/refund", headers={"Origin": "http://localhost"})
    as_user(user_id="b", role="demand").post("/api/profile", json={}, headers={"Origin": "https://evil.example"})
    out = capsys.readouterr().out
    assert "event=permission_denied" in out and "need=admin:incidents" in out
    assert "event=csrf_blocked" in out and "origin=https://evil.example" in out


def test_log_lines_cannot_be_forged(client, capsys):
    client.post("/api/login", json={"email": "x@example.com\nSECURITY event=login_ok user=admin", "password": "whatever-1"})
    out = capsys.readouterr().out
    assert "\nSECURITY event=login_ok" not in out


def test_ocems_logs_never_contain_the_key(monkeypatch, capsys):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))])

    class R:
        status_code, content, text, headers, encoding = 200, b"Date,pH\n", "Date,pH\n", {}, "utf-8"
    monkeypatch.setattr(ocems_api.requests, "get", lambda *a, **k: R())
    ocems_api._get_csv("https://x.tratasoft.com", "HEADER-KEY-123456", "/api/data/single")
    ocems_api._get_csv("https://x.tratasoft.com", "https://x.tratasoft.com/data&single?key=LINK-KEY-654321", None)
    out = capsys.readouterr().out
    assert "HEADER-KEY-123456" not in out and "LINK-KEY-654321" not in out
