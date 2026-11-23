"""Item 18: no uploaded XML/XLSX is parsed, uploads are checked by content,
and openpyxl refuses external entities (defusedxml)."""
import csv
import io
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TANKER = {"user_id": "t-x", "role": "tanker", "tanker_operator_id": "OP-XXE"}
XXE = ('<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
       '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c t="inlineStr"><is><t>&x;</t></is></c></row></sheetData></worksheet>')


def _xxe_xlsx():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><!DOCTYPE t [<!ENTITY x SYSTEM "file:///etc/passwd">]><Types>&x;</Types>')
        z.writestr("xl/worksheets/sheet1.xml", XXE)
    return buf.getvalue()


@pytest.fixture()
def vehicle(app_module):
    path = app_module.TANKER_VEHICLES_FILE
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields, rows = reader.fieldnames, list(reader)
    rows.append({"vehicle_id": "V-XXE", "operator_id": "OP-XXE", "registration_number": "KA01XX0001",
                 "vehicle_model": "Tata", "capacity_kl": "10", "vehicle_status": "Active", "created_at": "2026-11-23"})
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    return "V-XXE"


def _upload(client, vehicle, name, content):
    return client.post(f"/tanker/vehicle/{vehicle}/document/insurance/upload",
                       data={"document": (io.BytesIO(content), name)}, content_type="multipart/form-data",
                       headers={"Origin": "http://localhost"})


def test_xxe_xlsx_rejected_by_name_and_by_content(as_user, vehicle, app_module):
    c = as_user(**TANKER)
    assert "insurance" in app_module.ALLOWED_TANKER_DOCUMENT_TYPES
    assert _upload(c, vehicle, "fleet.xlsx", _xxe_xlsx()).status_code == 400
    assert _upload(c, vehicle, "fleet.pdf", _xxe_xlsx()).status_code == 400      # renamed zip
    assert _upload(c, vehicle, "doc.pdf", XXE.encode()).status_code == 400        # renamed xml
    assert _upload(c, vehicle, "doc.pdf", b"<html><body>%PDF-1.4</body></html>").status_code == 400


def test_real_pdf_still_accepted(as_user, vehicle):
    res = _upload(as_user(**TANKER), vehicle, "insurance.pdf", b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n")
    assert res.status_code in (200, 302)


def test_openpyxl_ignores_external_entities(tmp_path):
    import openpyxl
    from openpyxl.xml import DEFUSEDXML
    assert DEFUSEDXML
    f = tmp_path / "x.xlsx"
    f.write_bytes(_xxe_xlsx())
    with pytest.raises(Exception) as e:
        openpyxl.load_workbook(f)
    assert "root:" not in str(e.value)


def test_defusedxml_pinned_and_no_xml_parsers_in_app():
    assert "defusedxml==" in (ROOT / "requirements.txt").read_text()
    src = (ROOT / "app.py").read_text()
    for needle in ("xml.etree", "lxml", "minidom", "read_xml", "read_excel", "request.files.get(\"file\")"):
        assert needle not in src, needle
