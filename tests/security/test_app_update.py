"""Android "update available": /api/app/latest serves the newest GitHub
release (cached) and only ever points the app at github.com."""
import pytest

RELEASE = {
    "tag_name": "v1.7", "name": "ReFlow 1.7", "published_at": "2026-11-25T10:00:00Z",
    "html_url": "https://github.com/MohithMohan2004/ReFlow-AI/releases/tag/v1.7",
    "assets": [{"name": "ReFlow-v1.7.apk",
                "browser_download_url": "https://github.com/MohithMohan2004/ReFlow-AI/releases/download/v1.7/ReFlow-v1.7.apk"}],
}


class Resp:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status

    def json(self):
        return self.data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


@pytest.fixture()
def github(app_module, monkeypatch):
    calls = []
    state = {"resp": Resp(RELEASE)}

    def fake_get(url, **_kw):
        calls.append(url)
        if isinstance(state["resp"], Exception):
            raise state["resp"]
        return state["resp"]

    monkeypatch.setattr(app_module.requests, "get", fake_get)
    app_module._app_release_cache.update(at=0.0, data=None)
    yield calls, state
    app_module._app_release_cache.update(at=0.0, data=None)


def test_latest_release(client, github):
    calls, _ = github
    body = client.get("/api/app/latest").get_json()
    assert body["version"] == "1.7"
    assert body["download_url"].endswith("/ReFlow-v1.7.apk")
    assert calls == ["https://api.github.com/repos/MohithMohan2004/ReFlow-AI/releases/latest"]


def test_cached_and_survives_github_outage(client, app_module, github):
    calls, state = github
    client.get("/api/app/latest")
    client.get("/api/app/latest")
    assert len(calls) == 1
    app_module._app_release_cache["at"] = 0.0          # cache expired
    state["resp"] = ConnectionError("github down")
    assert client.get("/api/app/latest").get_json()["version"] == "1.7"


def test_never_points_outside_github(client, github):
    _, state = github
    state["resp"] = Resp(dict(RELEASE, html_url="https://evil.test/x",
                              assets=[{"name": "a.apk", "browser_download_url": "https://evil.test/a.apk"}]))
    assert client.get("/api/app/latest").status_code == 503


def test_bad_tag_ignored(client, github):
    _, state = github
    state["resp"] = Resp(dict(RELEASE, tag_name="<script>"))
    assert client.get("/api/app/latest").status_code == 503


def test_every_page_loads_the_prompt(client):
    assert b"app-update.js" in client.get("/login").data
    assert b"app-update.js" in client.get("/signup").data
