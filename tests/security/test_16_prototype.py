"""Item 16: role/key lookups can't reach Object.prototype, parsed JSON can't
pollute it, and production dependencies have no known high/critical issues
(the audit itself is run by hand)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_LOCAL = Path.home() / ".local/node/bin/node"
NODE = str(_LOCAL) if _LOCAL.exists() else (shutil.which("node") or "")
pytestmark = pytest.mark.skipif(not NODE, reason="node not installed")

SCRIPT = r"""
import { own, safeRecord } from "%s";
const ROLES = { demand: "/demand", stp: "/supply" };
const out = {};
out.normal = own(ROLES, "demand");
out.proto = own(ROLES, "__proto__") === undefined;
out.ctor = own(ROLES, "constructor") === undefined;
out.tostr = own(ROLES, "toString") === undefined;
const evil = JSON.parse('{"__proto__": {"polluted": "yes"}, "constructor": {"prototype": {"polluted": "yes"}}, "ok": 1}');
const clean = safeRecord(evil);
const spread = { ...evil };
out.notPolluted = ({}).polluted === undefined && Object.prototype.polluted === undefined;
out.cleanKeys = Object.keys(clean);
out.cleanProto = Object.getPrototypeOf(clean) === null;
console.log(JSON.stringify(out));
"""


def test_lookups_and_json_cannot_pollute(tmp_path):
    script = tmp_path / "check.mts"
    script.write_text(SCRIPT % (ROOT / "frontend/src/lib/lookup.ts").as_uri())
    res = subprocess.run([NODE, "--no-warnings", str(script)], capture_output=True, text=True, check=True)
    out = json.loads(res.stdout)
    assert out == {"normal": "/demand", "proto": True, "ctor": True, "tostr": True,
                   "notPolluted": True, "cleanKeys": ["ok"], "cleanProto": True}


def test_role_lookups_use_own():
    for rel in ("src/pages/Landing.tsx", "src/pages/Profile.tsx", "src/components/UserMenu.tsx", "src/components/ChatWidget.tsx"):
        src = (ROOT / "frontend" / rel).read_text()
        for table in ("HOME_FOR_ROLE[", "ROLE_META[", "SUGGESTIONS[role]"):
            assert table not in src, (rel, table)


def test_react_router_outside_vulnerable_range():
    lock = json.loads((ROOT / "frontend/package-lock.json").read_text())
    version = lock["packages"]["node_modules/react-router"]["version"]
    assert tuple(map(int, version.split("."))) > (7, 17, 0)
