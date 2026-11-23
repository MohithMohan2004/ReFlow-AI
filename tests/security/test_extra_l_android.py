"""Android app: no backups of WebView data (session cookie), no plain HTTP in
the production build."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ANDROID = ROOT / "mobile/android/app/src/main"


def test_backups_disabled():
    manifest = (ANDROID / "AndroidManifest.xml").read_text()
    assert 'android:allowBackup="false"' in manifest
    assert 'android:fullBackupContent="false"' in manifest
    rules = (ANDROID / "res/xml/data_extraction_rules.xml").read_text()
    assert rules.count('<exclude domain="root" />') == 2


def test_production_build_is_https_only():
    cfg = json.loads((ANDROID / "assets/capacitor.config.json").read_text())
    assert cfg["server"]["url"].startswith("https://")
    assert cfg["server"].get("cleartext") is False
    assert not cfg.get("android", {}).get("allowMixedContent")
    assert not cfg.get("android", {}).get("webContentsDebuggingEnabled")
