"""Extra F: uploaded documents get random names, are checked by content and
size, live outside static/, and are served only through the admin route."""
import csv
import io
import os
import re

import pytest

TANKER = {"user_id": "t-f", "role": "tanker", "tanker_operator_id": "OP-F"}
ORIGIN = {"Origin": "http://localhost"}
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


@pytest.fixture()
def vehicle(app_module):
    path = app_module.TANKER_VEHICLES_FILE
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields, rows = reader.fieldnames, [r for r in reader if r["vehicle_id"] != "V-F"]
    rows.append({"vehicle_id": "V-F", "operator_id": "OP-F", "registration_number": "KA01FF0001",
                 "vehicle_model": "Tata", "capacity_kl": "10", "vehicle_status": "Active", "created_at": "2026-11-23"})
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    return "V-F"


def _upload(c, content, name="rc.pdf"):
    return c.post("/tanker/vehicle/V-F/document/rc/upload", data={"document": (io.BytesIO(content), name)},
                  content_type="multipart/form-data", headers=ORIGIN)


def _docs(app_module):
    with open(app_module.TANKER_VEHICLE_DOCUMENTS_FILE, newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r.get("vehicle_id") == "V-F"]


def test_random_stored_name_outside_static(as_user, vehicle, app_module):
    assert _upload(as_user(**TANKER), PDF, name="../../static/evil.pdf").status_code in (200, 302)
    doc = _docs(app_module)[-1]
    assert re.fullmatch(r"doc_[0-9a-f]{32}\.pdf", doc["stored_filename"])
    assert "OP-F" not in doc["stored_filename"]
    stored = os.path.join(app_module.TANKER_DOCUMENT_UPLOAD_FOLDER, doc["stored_filename"])
    assert os.path.isfile(stored)
    assert "static" not in os.path.relpath(stored, app_module.DATA_ROOT_FOR_TESTS).split(os.sep)


def test_too_big_or_wrong_type_refused(as_user, vehicle):
    c = as_user(**TANKER)
    assert _upload(c, PDF + b"0" * (5 * 1024 * 1024)).status_code in (400, 413)
    assert _upload(c, b"MZ\x90\x00 not a pdf").status_code == 400


def test_only_admins_can_open_documents(as_user, vehicle, app_module):
    _upload(as_user(**TANKER), PDF)
    doc_id = _docs(app_module)[-1]["document_id"]
    assert as_user(**TANKER).get(f"/admin/tanker/document/{doc_id}/view").status_code in (302, 403)
    assert as_user(user_id="b", role="demand").get(f"/admin/tanker/document/{doc_id}/view").status_code in (302, 403)
    res = as_user(user_id="a", role="admin").get(f"/admin/tanker/document/{doc_id}/view")
    assert res.status_code == 200 and res.mimetype == "application/pdf"
    assert res.headers["X-Content-Type-Options"] == "nosniff"
