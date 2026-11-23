"""Extra D: state-changing requests from another site are refused, and no
GET request changes anything."""
import pytest

SUPER = {"user_id": "s-d", "role": "superadmin"}
BUYER = {"user_id": "b-d", "role": "demand"}


@pytest.mark.parametrize("headers", [
    {"Origin": "https://evil.example"},
    {"Origin": "null"},
    {"Referer": "https://evil.example/page"},
    {"Origin": "https://localhost.evil.example"},
    {"Origin": "http://evil.example", "Referer": "http://localhost/admin"},  # Origin wins
])
def test_cross_site_posts_blocked(as_user, app_module, headers):
    c = as_user(**SUPER)
    n = len(app_module.load_stps())
    stp_id = app_module.load_stps()[0]["stp_id"]
    assert c.post(f"/admin/delete_stp/{stp_id}", headers=headers).status_code == 403
    assert c.post("/api/profile", json={"first_name": "X"}, headers=headers).status_code == 403
    assert c.post("/api/logout", headers=headers).status_code == 403
    assert len(app_module.load_stps()) == n


def test_same_origin_and_headerless_requests_allowed(as_user):
    c = as_user(**BUYER)
    assert c.post("/api/profile", json={"first_name": "Ravi"}, headers={"Origin": "http://localhost"}).status_code == 200
    assert c.post("/api/profile", json={"first_name": "Ravi"}, headers={"Referer": "http://localhost/profile"}).status_code == 200
    assert c.post("/api/profile", json={"first_name": "Ravi"}).status_code == 200   # non-browser client


def test_trusted_extra_origin(as_user, monkeypatch):
    monkeypatch.setenv("CSRF_TRUSTED_ORIGINS", "https://app.example.org")
    c = as_user(**BUYER)
    assert c.post("/api/profile", json={"first_name": "Ravi"}, headers={"Origin": "https://app.example.org"}).status_code == 200


def test_admin_actions_are_post_only(as_user, app_module):
    c = as_user(**SUPER)
    stps = app_module.load_stps()
    victim = stps[-1]["stp_id"]
    assert c.get(f"/admin/delete_stp/{victim}").status_code == 405
    assert c.get("/admin/tanker/OP-X/status/approved").status_code == 405
    assert c.get("/admin/stp/REG-X/status/approved").status_code == 405
    assert len(app_module.load_stps()) == len(stps)
    res = c.post(f"/admin/delete_stp/{victim}", headers={"Origin": "http://localhost"})
    assert res.status_code == 302
    assert victim not in {s["stp_id"] for s in app_module.load_stps()}
    app_module.save_stps(stps)  # restore the shared temp data


def test_no_get_route_changes_state(app_module):
    """Every route whose name suggests a change must refuse GET."""
    verbs = ("delete", "remove", "update", "accept", "reject", "approve", "cancel", "pay", "confirm",
             "upload", "review", "refund", "report", "complete", "respond", "create", "reorder", "logout_all")
    for rule in app_module.app.url_map.iter_rules():
        name = rule.endpoint.lower()
        if set(name.split("_")) & set(verbs):
            assert "GET" not in rule.methods or name in {"logout"}, (rule.rule, rule.methods)
