"""Item 10: no response is built from the Host header, and API / logged-in
responses are never cacheable."""
import pytest

EVIL = "evil.example"
DEMAND = {"user_id": "buyer-1", "role": "demand", "buyer_name": "Ravi Kumar"}
API_PATHS = ["/api/current_user", "/api/stps", "/api/my_orders", "/api/profile", "/api/stp_pricing/PSTP001"]
PAGES = ["/", "/login", "/signup", "/track", "/demand", "/profile", "/invoice?order_id=nope", "/admin", "/supply"]


@pytest.mark.parametrize("path", PAGES + API_PATHS)
def test_spoofed_host_never_reflected(as_user, path):
    for c in (as_user(), as_user(**DEMAND)):
        res = c.get(path, headers={"Host": EVIL, "X-Forwarded-Host": EVIL})
        assert EVIL not in res.get_data(as_text=True)
        assert EVIL not in res.headers.get("Location", "")


@pytest.mark.parametrize("path", API_PATHS)
def test_every_api_response_is_no_store(as_user, path):
    for c in (as_user(), as_user(**DEMAND)):
        assert c.get(path).headers.get("Cache-Control") == "no-store"


def test_api_errors_and_429_are_no_store(client):
    res = client.post("/api/login", json={})
    assert res.headers.get("Cache-Control") == "no-store"


def test_logged_in_pages_are_no_store(as_user):
    c = as_user(**DEMAND)
    for path in ("/demand", "/track", "/profile"):
        res = c.get(path)
        assert res.status_code == 200, path
        assert res.headers.get("Cache-Control") == "no-store", path


def test_hashed_assets_keep_long_cache(client, app_module):
    import os
    assets = os.listdir(os.path.join(app_module.app.root_path, "static", "app", "assets"))
    res = client.get("/static/app/assets/" + sorted(assets)[0])
    assert "immutable" in res.headers.get("Cache-Control", "")
