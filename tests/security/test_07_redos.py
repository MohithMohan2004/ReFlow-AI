"""Item 7: every regex that runs on user or vendor text finishes a 50,000
character hostile string in under 100 ms."""
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest

import ocems_api

ROOT = Path(__file__).resolve().parents[2]
N = 50_000
HOSTILE = [
    "(" + " " * N + "x", "(" * N, "[" + "a " * (N // 2), "1" * N, "1." * (N // 2),
    "stp " * (N // 4), "stp" * (N // 3) + " to", "a@" + "." * N + "@", "s" + " " * N + "x",
]


def _fast(fn):
    for s in HOSTILE:
        start = time.perf_counter()
        fn(s)
        took = time.perf_counter() - start
        assert took < 0.1, f"{fn} took {took * 1000:.0f} ms on {s[:20]!r}…"


def test_ocems_label_parsing_is_linear():
    _fast(ocems_api._split_label)
    _fast(ocems_api._canonical)
    _fast(ocems_api.TIME_WORDS.search)
    for pattern, _name in ocems_api.CANONICAL:
        _fast(pattern.search)


def test_ocems_unit_still_parsed():
    assert ocems_api._split_label("BOD (mg/l)") == ("BOD (mg/l)", "mg/l")
    assert ocems_api._split_label("Flow [ m3/hr ] ")[1] == "m3/hr"
    assert ocems_api._split_label("pH")[1] == ""


def test_chatbot_patterns_are_linear(app_module):
    _fast(app_module.CHAT_QUANTITY.search)
    _fast(app_module.CHAT_LOCATION_AFTER_STP.search)
    assert app_module.CHAT_QUANTITY.search("need 2.5 kld").groups() == ("2.5", "kld")


def test_chatbot_caps_message_before_matching(client):
    start = time.perf_counter()
    res = client.post("/api/chat", json={"message": "1" * N + " stp " * 1000})
    assert res.status_code in (200, 400)
    assert time.perf_counter() - start < 3


@pytest.mark.skipif(not (shutil.which("node") or Path.home().joinpath(".local/node/bin/node").exists()),
                    reason="node not installed")
def test_frontend_email_regex_is_linear():
    node = shutil.which("node") or str(Path.home() / ".local/node/bin/node")
    src = (ROOT / "frontend/src/pages/register/shared.tsx").read_text()
    regex = re.search(r"export const EMAIL_RE = (/.*/);", src).group(1)
    script = (f"const re={regex}; const t=Date.now();"
              f"re.test('a@'+'.'.repeat({N})+'@'); re.test('a@'+'a.'.repeat({N // 2})+'@');"
              "console.log(Date.now()-t, re.test('ravi.kumar@example.com'), re.test('a@b'))")
    took, ok, bad = subprocess.run([node, "-e", script], capture_output=True, text=True, check=True).stdout.split()
    assert int(took) < 100 and ok == "true" and bad == "false"
