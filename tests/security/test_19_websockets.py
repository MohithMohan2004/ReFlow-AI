"""Item 19: the app has no WebSocket endpoints and the browser opens none
(live tracking is HTTP polling), so cross-site WebSocket hijacking has no target."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATTERN = re.compile(r"socketio|websocket|wss?://|\.channel\(|supabase.*realtime|EventSource", re.I)


def test_no_websockets_anywhere(app_module):
    files = [ROOT / "app.py", ROOT / "security.py", ROOT / "requirements.txt",
             *ROOT.glob("frontend/src/**/*.ts*"), *ROOT.glob("templates/*.html")]
    assert [str(p) for p in files if PATTERN.search(p.read_text(errors="ignore"))] == []
    assert not [r.rule for r in app_module.app.url_map.iter_rules() if re.search(r"socket|ws\b|realtime", r.rule)]
