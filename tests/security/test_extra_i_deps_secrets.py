"""Extra I: every dependency is pinned, secret files are ignored, and no
tracked file contains a credential."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_every_requirement_pinned_exactly():
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            assert re.fullmatch(r"[A-Za-z0-9_.-]+(\[[a-z,]+\])?==[0-9][0-9A-Za-z.]*", line), line
    assert re.search(r"^pytest==", (ROOT / "requirements-dev.txt").read_text(), re.M)


def test_frontend_dependencies_pinned_exactly():
    import json
    pkg = json.loads((ROOT / "frontend/package.json").read_text())
    for name, version in pkg.get("dependencies", {}).items():
        assert re.fullmatch(r"\d+\.\d+\.\d+", version), (name, version)


def test_secret_files_are_ignored():
    for path in (".env", ".env.azure", "mobile/android/keystore.properties", "data/profile_overrides.json"):
        assert subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT).returncode == 0, path


def test_no_credentials_in_tracked_files():
    import importlib.util
    spec = importlib.util.spec_from_file_location("scan", ROOT / "scripts/secret_scan.py")
    source = (ROOT / "scripts/secret_scan.py").read_text()
    rules_src = source[source.index("RULES = {"):source.index("SKIP = ")]
    ns = {"re": re}
    exec(rules_src, ns)
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    hits = []
    for rel in files:
        p = ROOT / rel
        if rel.startswith(("static/app/", "frontend/package-lock")) or p.suffix in (".png", ".jpg", ".ico", ".xlsx", ".pdf", ".pkl", ".graphml", ".woff2", ".jar", ".apk"):
            continue
        try:
            text = p.read_text(errors="ignore")
        except (OSError, IsADirectoryError):
            continue
        for rule, rx in ns["RULES"].items():
            for m in rx.finditer(text):
                value = m.group(0)
                if "os.getenv" in value or "<" in value or "test_only" in value or "test-only" in value:
                    continue
                hits.append((rel, rule))
    assert hits == []
