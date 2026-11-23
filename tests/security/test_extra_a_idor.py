"""Extra A: user A can't read or change user B's orders, invoices, plant
data, transfers, tanker jobs, vehicles or OCEMS connection."""
import csv
import hashlib
from pathlib import Path

import pytest

MARK = "SECRET-LOC-A"          # appears only in buyer A's orders
PHONE = "9000099999"
ORIGIN = {"Origin": "http://localhost"}

BUYER_A = dict(user_id="buyer-A", role="demand", buyer_name="Ravi Kumar", buyer_phone=PHONE, user_phone=PHONE)
BUYER_B = dict(user_id="buyer-B", role="demand", buyer_name="Ravi Kumar", buyer_phone=PHONE, user_phone=PHONE)  # same name+phone!
PLANT_1 = dict(user_id="plant-1", role="stp", stp_id="PSTP001", selected_stp_id="PSTP001")
PLANT_3 = dict(user_id="plant-3", role="stp", stp_id="PSTP003", selected_stp_id="PSTP003")
TANKER_A = dict(user_id="tank-A", role="tanker", tanker_operator_id="OP-A")
TANKER_B = dict(user_id="tank-B", role="tanker", tanker_operator_id="OP-B")


def _write_csv(path, fields, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def _settle(as_user):
    """Let time-based housekeeping (capacity release stamps, expiries) run
    first, so a snapshot compares only what the attacker's request did."""
    as_user(**PLANT_1).get("/api/stp_orders")
    as_user(**TANKER_A).get("/api/tanker/overview")
    as_user(**BUYER_A).get("/api/my_orders")


def _digest(*paths):
    return hashlib.sha256(b"".join(Path(p).read_bytes() for p in paths if Path(p).exists())).hexdigest()


@pytest.fixture()
def world(app_module):
    A = app_module
    base = dict(stp_id="PSTP001", stp_name="Plant One", quantity_kld="10", quality="General", water_type="Treated",
                distance_km="5", location=MARK, buyer_user_id="buyer-A", buyer_name="Ravi Kumar", buyer_phone=PHONE,
                created_at="2026-11-23T10:00:00", payment_status="Paid", invoice_water_rate="20", invoice_tariff="Base rate",
                delivery_lat="12.97", delivery_lon="77.64", tankers_required="1")
    orders = [
        dict(base, order_id="ORD-A1", status="Pending"),
        dict(base, order_id="ORD-A2", status="Out for Delivery", accepted_at="2026-11-23T10:05:00",
             assigned_operator_id="OP-A", assigned_operator_name="A Tankers", pickup_at="2026-11-23T10:30:00"),
        dict(base, order_id="ORD-A3", status="Accepted", accepted_at="2026-11-23T10:05:00",
             offered_operator_id="OP-A", offer_status="Pending", offer_sent_at="2026-11-23T10:06:00",
             offer_expires_at="2099-01-01T00:00:00"),
        dict(base, order_id="ORD-A4", status="Delivered", payment_status="Paid", delivered_at="2026-11-23T11:00:00",
             assigned_operator_id="OP-A"),
        # legacy order from before user ids were stored: same name + phone as BUYER_B
        dict(base, order_id="ORD-L1", status="Pending", payment_status="Pending", buyer_user_id=""),
    ]
    _write_csv(A.ORDERS_FILE, A.ORDER_FIELDS, orders)
    A.ensure_stp_transfers_file()
    transfer = {f: "" for f in A.STP_TRANSFER_FIELDS}
    transfer.update(transfer_id="TR-A", source_stp_id="PSTP001", source_stp_name="Plant One", destination_stp_id="PSTP002",
                    destination_stp_name="Plant Two", quantity_kld="50", status="Out for Delivery",
                    tanker_status="Out for Delivery", requested_at="2026-11-23T09:00:00", assigned_operator_id="OP-A")
    transfer2 = dict(transfer, transfer_id="TR-P", status="Pending", tanker_status="", assigned_operator_id="")
    _write_csv(A.STP_TRANSFERS_FILE, A.STP_TRANSFER_FIELDS, [transfer, transfer2])
    with open(A.TANKER_VEHICLES_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        vfields, vrows = reader.fieldnames, [r for r in reader if r["vehicle_id"] != "V-A"]
    vrows.append(dict(vehicle_id="V-A", operator_id="OP-A", registration_number="KA01AA0001", vehicle_model="Tata",
                      capacity_kl="10", vehicle_status="Active", created_at="2026-11-01"))
    _write_csv(A.TANKER_VEHICLES_FILE, vfields, vrows)
    return [A.ORDERS_FILE, A.STP_TRANSFERS_FILE, A.TANKER_VEHICLES_FILE, A.STP_FILE, A.PRICING_FILE,
            A.DATABASE_PRICING_FILE, A.STATUS_FILE]


READS = [
    (BUYER_B, "/api/order_tracking/ORD-A2"),
    (BUYER_B, "/api/order_tracking/ORD-A2/tanker_location"),
    (BUYER_B, "/api/shared_order_tracking/ORD-A2"),
    (BUYER_B, "/invoice?order_id=ORD-A1"),
    (BUYER_B, "/api/my_orders"),
    (BUYER_B, "/api/track_order?order_id=ORD-A1"),
    (BUYER_B, f"/api/track_order?phone={PHONE}"),
    ({}, "/api/track_order?order_id=ORD-A1"),
    (PLANT_3, "/api/stp_order_tracking/ORD-A2"),
    (PLANT_3, "/api/stp_orders"),
    (PLANT_3, "/api/supply/overview?stp_id=PSTP001"),
    (PLANT_3, "/invoice?order_id=ORD-A1"),
    (TANKER_B, "/api/tanker/overview"),
    (TANKER_B, "/api/tanker_route?order_id=ORD-A2&request_type=demand"),
    (TANKER_B, "/api/order_tracking/ORD-A2/tanker_location"),
]


@pytest.mark.parametrize("who,path", READS)
def test_cross_tenant_reads_leak_nothing(world, as_user, who, path):
    res = as_user(**who).get(path)
    assert MARK not in res.get_data(as_text=True), (path, res.status_code)


def test_owner_reads_still_work(world, as_user):
    a = as_user(**BUYER_A)
    assert MARK in a.get("/api/my_orders").get_data(as_text=True)
    assert a.get("/invoice?order_id=ORD-A1").status_code == 200
    assert MARK in a.get("/api/track_order?order_id=ORD-A1").get_data(as_text=True)
    assert MARK in as_user(**PLANT_1).get("/api/stp_orders").get_data(as_text=True)


WRITES = [
    (BUYER_B, "/pay_now", {"order_id": "ORD-A1"}),
    (BUYER_B, "/confirm_cod", {"order_id": "ORD-A1"}),
    (BUYER_B, "/cancel_cod", {"order_id": "ORD-A1"}),
    (BUYER_B, "/reorder/ORD-A4", {}),
    (BUYER_B, "/cancel_cod", {"order_id": "ORD-L1"}),       # name+phone match is not ownership
    (BUYER_B, "/pay_now", {"order_id": "ORD-L1"}),
    (BUYER_A, "/pay_now", {"order_id": "ORD-A4"}),          # own delivered order: no reset
    (BUYER_A, "/confirm_cod", {"order_id": "ORD-A2"}),       # own order on the road: no reset
    (PLANT_3, "/handle_request", {"request_id": "ORD-A1", "action": "accept"}),
    (PLANT_3, "/update_order_status", {"order_id": "ORD-A1", "status": "Accepted"}),
    (PLANT_3, "/update_capacity", {"stp_id": "PSTP001", "available_capacity_mld": "0", "request_id": "x"}),
    (PLANT_3, "/upload_quality", {"stp_id": "PSTP001", "quality_grade": "Industrial", "request_id": "x"}),
    (PLANT_3, "/handle_transfer_request", {"transfer_id": "TR-P", "action": "accept"}),
    (TANKER_B, "/tanker/order/ORD-A3/pickup", {}),
    (TANKER_B, "/tanker/order/ORD-A2/delivered", {}),
    (TANKER_B, "/tanker/order/ORD-A2/report_incident", {"reason": "accident"}),
    (TANKER_B, "/tanker/transfer/TR-A/report_incident", {"reason": "accident"}),
    (TANKER_B, "/accept_pickup", {"order_id": "ORD-A3"}),
    (TANKER_B, "/reject_pickup", {"order_id": "ORD-A3"}),
    (TANKER_B, "/complete_transfer", {"transfer_id": "TR-A"}),
    (TANKER_B, "/accept_transfer_pickup", {"transfer_id": "TR-A"}),
    (TANKER_B, "/reject_transfer_pickup", {"transfer_id": "TR-A"}),
    (TANKER_B, "/tanker/respond_request", {"order_id": "ORD-A3", "action": "accept"}),
    (TANKER_B, "/api/tanker/vehicles/V-A/remove", {}),
    (BUYER_B, "/admin/order/ORD-A2/refund", {}),
    (PLANT_1, "/admin/add_stp", {"id": "PX", "name": "X", "lat": "1", "lon": "1", "capacity": "1"}),
]


@pytest.mark.parametrize("who,path,form", WRITES)
def test_cross_tenant_writes_change_nothing(world, as_user, who, path, form):
    _settle(as_user)
    before = _digest(*world)
    res = as_user(**who).post(path, data=form, headers=ORIGIN)
    assert _digest(*world) == before, (path, res.status_code, res.get_data(as_text=True)[:200])


@pytest.mark.parametrize("who,path,body", [
    (PLANT_3, "/api/update_pricing", {"stp_id": "PSTP001", "base_price_per_kld": 1}),
    (PLANT_3, "/api/stp/details", {"stp_id": "PSTP001", "stp_name": "Hijacked"}),
])
def test_cross_plant_json_writes_change_nothing(world, as_user, who, path, body):
    _settle(as_user)
    before = _digest(*world)
    as_user(**who).post(path, json=body, headers=ORIGIN)
    assert _digest(*world) == before


def test_api_login_ignores_tanker_id_in_metadata(client, app_module):
    app_module.supabase.auth.add_user("mallory@example.com", "mallory-pass-1", role="tanker",
                                      tanker_operator_id="OP-BLR-0001")
    res = client.post("/api/login", json={"email": "mallory@example.com", "password": "mallory-pass-1"})
    assert res.status_code == 403
    with client.session_transaction() as s:
        assert not s.get("tanker_operator_id")


def _status(app_module, order_id):
    with open(app_module.ORDERS_FILE, newline="", encoding="utf-8") as f:
        return next(r for r in csv.DictReader(f) if r["order_id"] == order_id)["status"]


def test_positive_controls_owners_can_act(world, as_user, app_module):
    """The same requests succeed for the rightful owner, so the denials above
    are real access checks, not malformed requests."""
    as_user(**PLANT_1).post("/handle_request", data={"request_id": "ORD-A1", "action": "reject"}, headers=ORIGIN)
    assert _status(app_module, "ORD-A1") == "Rejected"
    as_user(**TANKER_A).post("/tanker/order/ORD-A2/report_incident", data={"reason": "breakdown"}, headers=ORIGIN)
    assert _status(app_module, "ORD-A2") == "Delivery Failed"
    res = as_user(**PLANT_1).get("/api/stp_order_tracking/ORD-A2")
    assert res.status_code == 200 and MARK in res.get_data(as_text=True)
