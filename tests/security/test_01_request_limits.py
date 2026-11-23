"""Item 1: oversized bodies get 413, floods of an expensive route get 429."""
from pathlib import Path


def test_oversized_body_is_rejected(client, app_module):
    big = b"x" * (app_module.app.config["MAX_CONTENT_LENGTH"] + 1)
    res = client.post("/api/chat", data=big, content_type="application/json")
    assert res.status_code == 413


def test_flood_of_expensive_route_gets_429(client):
    statuses = [client.get("/api/search_place?q=a").status_code for _ in range(40)]
    assert 429 in statuses
    assert statuses.index(429) == 30  # first 30 in the window are served


def test_login_flood_gets_429_with_retry_after(client):
    last = None
    for _ in range(11):
        last = client.post("/api/login", json={"email": "x@example.com", "password": "wrong-password"})
    assert last.status_code == 429
    assert int(last.headers["Retry-After"]) > 0


def test_gunicorn_serves_http1_only_with_limits():
    cmd = (Path(__file__).resolve().parents[2] / "Dockerfile").read_text()
    for flag in ("--http-protocols h1", "--limit-request-line", "--limit-request-fields",
                 "--limit-request-field_size", "--timeout 75"):
        assert flag in cmd, flag


def test_production_image_ships_every_module_and_flag():
    """deploy/Dockerfile (what Azure runs) copies an explicit file list: every
    local module app.py imports must be in it, and the gunicorn limits too."""
    import ast
    import re
    root = Path(__file__).resolve().parents[2]
    docker = (root / "deploy/Dockerfile").read_text()
    copied = set()
    for line in docker.splitlines():
        if line.startswith("COPY") and "--from=" not in line:
            copied.update(part.rstrip("/") for part in line.split()[1:-1] if not part.startswith("--"))
    local_modules = {p.stem for p in root.glob("*.py")} | {p.name for p in root.iterdir() if p.is_dir() and (p / "__init__.py").exists()}
    imported = set()
    for node in ast.walk(ast.parse((root / "app.py").read_text())):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    for module in imported & local_modules:
        assert f"{module}.py" in copied or module in copied, f"deploy/Dockerfile doesn't copy {module}"
    for flag in ("--http-protocols h1", "--limit-request-line", "--limit-request-fields", "--limit-request-field_size"):
        assert flag in docker, flag
