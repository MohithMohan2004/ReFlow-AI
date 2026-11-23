"""Item 17: user and vendor text is never rendered as a template or as HTML."""
import re
from pathlib import Path

import ocems_api

ROOT = Path(__file__).resolve().parents[2]
EVIL = "{{7*7}}<script>alert(1)</script>"
SUPER = {"user_id": "s-1", "role": "superadmin", "user_name": "Super"}


def test_plant_name_shown_as_text(as_user, app_module):
    admin = as_user(**SUPER)
    res = admin.post("/admin/add_stp", data={"id": "PXSS1", "name": EVIL, "lat": "12.9", "lon": "77.6", "capacity": "1"},
                     headers={"Origin": "http://localhost"})
    assert res.status_code in (302, 303)
    page = admin.get("/admin").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in page
    assert "{{7*7}}&lt;script&gt;alert(1)&lt;/script&gt;" in page   # literal, escaped, not evaluated
    api = admin.get("/api/stps")
    assert api.mimetype == "application/json"  # data, rendered as text by React
    # clean up the shared temp data
    app_module.save_stps([s for s in app_module.load_stps() if s["stp_id"] != "PXSS1"])


def test_no_template_built_from_input():
    src = (ROOT / "app.py").read_text()
    assert "render_template_string" not in src and "Template(" not in src and "Markup(" not in src
    for t in ROOT.glob("templates/*.html"):
        text = t.read_text()
        assert "autoescape false" not in text, t
        for m in re.finditer(r"\{\{([^}]*)\|\s*safe\s*\}\}", text):
            assert t.name == "_tabbar.html" and "_icons[icon]" in m.group(1), (t, m.group(0))


def test_role_art_is_a_constant():
    src = (ROOT / "frontend/src/pages/Landing.tsx").read_text()
    assert re.search(r"const ROLE_ART\s*[:=]", src)
    assert src.count("dangerouslySetInnerHTML") == 1 and "ROLE_ART[art]" in src


def test_vendor_parameter_names_are_sanitised():
    assert ocems_api._canonical('<img src=x onerror="alert(1)">') == "img srcx onerroralert"
    assert ocems_api._canonical("BOD (mg/l)") == "BOD"
    assert ocems_api._canonical("NH3-N [mg/l]") == "NH3-N"
    parsed = ocems_api.parse_csv('Date,Time,<b onmouseover=x>Flow</b>\n2026-11-23,10:00,5\n')
    assert all("<" not in p and ">" not in p and '"' not in p for p in parsed["parameters"])


def test_ocems_page_escapes_vendor_names():
    src = (ROOT / "templates/supply_ocems.html").read_text()
    assert "function esc(" in src
    for line in src.splitlines():
        if "innerHTML" in line or "'<" in line or '"<' in line:
            assert not re.search(r"\+ p \+|\+ m\.name \+", line), line
