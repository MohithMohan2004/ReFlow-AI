"""Item 13: nothing that grants access is made with `random`; short uuid4
labels are always paired with an ownership check."""
import csv
import re
import time
from pathlib import Path

import ocems_api

ROOT = Path(__file__).resolve().parents[2]


def _orders(app_module):
    with open(app_module.ORDERS_FILE, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _add_order(app_module, order_id, buyer):
    rows = _orders(app_module)
    row = {k: "" for k in app_module.ORDER_FIELDS}
    row.update(order_id=order_id, stp_id="PSTP001", stp_name="Plant", quantity_kld="10", buyer_user_id=buyer,
               buyer_name="Ravi Kumar", buyer_phone="9000012345", status="Pending", created_at="2026-11-23T10:00:00",
               payment_status="Paid", location="Indiranagar 560038", invoice_water_rate="20", invoice_tariff="Base rate")
    with open(app_module.ORDERS_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=app_module.ORDER_FIELDS)
        w.writeheader()
        for r in rows + [row]:
            w.writerow({k: r.get(k, "") for k in app_module.ORDER_FIELDS})


def test_no_random_module_in_security_paths():
    src = (ROOT / "app.py").read_text()
    uses = [m.group(0) for m in re.finditer(r"random\.\w+\(", src)]
    # traffic factor for the road graph + seeded synthetic OCEMS demo readings only
    assert set(uses) <= {"random.uniform(", "random.Random("}
    for path in ROOT.glob("frontend/src/**/*.ts*"):
        if "Math.random" in path.read_text():
            assert path.name == "toast.tsx", path  # toast list key, not a secret


def test_export_job_ids_are_unguessable_and_owned():
    src = (ROOT / "ocems_api.py").read_text()
    assert "os.urandom(32)" in src
    job = "f" * 24
    with ocems_api._exports_lock:
        ocems_api._exports[job] = {"owner": "PSTP001", "status": "done", "csv": "a", "error": None,
                                   "filename": "x.csv", "expires": time.monotonic() + 600}
    assert ocems_api.get_export(job, "PSTP002") is None
    assert ocems_api.get_export(job, "PSTP001") is not None


def test_invoice_id_alone_does_not_open_someone_elses_invoice(app_module, as_user):
    _add_order(app_module, "ORD-TOK13AAAA", "buyer-A")
    mine = as_user(user_id="buyer-A", role="demand").get("/invoice?order_id=ORD-TOK13AAAA")
    assert mine.status_code == 200
    theirs = as_user(user_id="buyer-B", role="demand").get("/invoice?order_id=ORD-TOK13AAAA")
    assert theirs.status_code in (403, 404)
    assert b"9000012345" not in theirs.data
    anon = as_user().get("/invoice?order_id=ORD-TOK13AAAA")
    assert b"9000012345" not in anon.data


def test_uploaded_documents_are_not_publicly_served(app_module, client):
    for prefix in ("/uploads/tanker_documents/", "/static/uploads/", "/tanker_documents/"):
        assert client.get(prefix + "x.pdf").status_code == 404
