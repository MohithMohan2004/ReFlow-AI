"""Legal pages, required consent (checked on the server, recorded with the
document version), and the end of the demo card checkout."""
import csv

import pytest

ORIGIN = {"Origin": "http://localhost"}
SIGNUP = dict(first_name="Ravi", last_name="Kumar", mobile="9000012345", username="ravik", role="demand",
              password="ravi-pass-123", confirm_password="ravi-pass-123")


def consent_rows(app_module):
    try:
        with open(app_module.CONSENT_LOG_FILE, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        return []


@pytest.mark.parametrize("path", ["/privacy", "/terms", "/cookies", "/refunds", "/accessibility"])
def test_legal_pages_are_public(client, path):
    res = client.get(path)
    assert res.status_code == 200 and b'id="root"' in res.data


def test_web_signup_needs_the_tick(client, app_module):
    res = client.post("/signup", data=dict(SIGNUP, email="no-tick@example.com"), headers=ORIGIN)
    assert b"agree to the Terms of Use" in res.data
    assert "no-tick@example.com" not in app_module.supabase.auth.users

    before = len(consent_rows(app_module))
    res = client.post("/signup", data=dict(SIGNUP, email="tick@example.com", accept_terms="yes"), headers=ORIGIN)
    assert res.status_code == 302
    meta = app_module.supabase.auth.users["tick@example.com"]["user_metadata"]
    assert meta["terms_version"] == app_module.LEGAL_VERSION
    rows = consent_rows(app_module)
    assert len(rows) == before + 1 and rows[-1]["kind"] == "signup" and rows[-1]["version"] == app_module.LEGAL_VERSION


def test_api_signup_needs_the_tick(client, app_module):
    res = client.post("/api/signup", json=dict(SIGNUP, email="api-no@example.com"), headers=ORIGIN)
    assert res.status_code == 400 and "api-no@example.com" not in app_module.supabase.auth.users
    res = client.post("/api/signup", json=dict(SIGNUP, email="api-yes@example.com", accept_terms=True), headers=ORIGIN)
    assert res.status_code == 201


@pytest.mark.parametrize("path", ["/stp/register", "/tanker/register/independent", "/tanker/register/contracted"])
def test_registrations_need_the_tick(client, path):
    res = client.post(path, data={"phone": "9000012345", "email": "x@example.com"}, headers=ORIGIN)
    assert res.status_code == 400
    assert "Terms of Use" in res.get_json()["error"]


def test_card_checkout_is_gone(as_user):
    c = as_user(user_id="buyer-1", role="demand")
    assert c.post("/pay_now", data={"order_id": "ANY"}, headers=ORIGIN).status_code == 410


def _draft(c, order_id):
    with c.session_transaction() as s:
        s["pending_order_draft"] = {"order_id": order_id, "buyer_user_id": "buyer-1", "stp_id": "PSTP001",
                                    "stp_name": "Test plant", "quantity_kld": "12", "status": "Draft"}


def _order(app_module, order_id):
    with open(app_module.ORDERS_FILE, newline="", encoding="utf-8") as f:
        return next((r for r in csv.DictReader(f) if r["order_id"] == order_id), None)


def test_order_needs_the_tick_and_records_method(as_user, app_module):
    c = as_user(user_id="buyer-1", role="demand")
    _draft(c, "ORD-LEGAL-1")
    res = c.post("/confirm_cod", data={"order_id": "ORD-LEGAL-1", "method": "bank_transfer"}, headers=ORIGIN)
    assert res.status_code == 400 and _order(app_module, "ORD-LEGAL-1") is None

    res = c.post("/confirm_cod", data={"order_id": "ORD-LEGAL-1", "method": "bank_transfer", "accept_terms": "yes"}, headers=ORIGIN)
    assert res.status_code == 302
    assert _order(app_module, "ORD-LEGAL-1")["payment_status"] == "Bank Transfer"
    assert consent_rows(app_module)[-1]["subject"] == "buyer-1:ORD-LEGAL-1"

    _draft(c, "ORD-LEGAL-2")
    c.post("/confirm_cod", data={"order_id": "ORD-LEGAL-2", "accept_terms": "yes"}, headers=ORIGIN)
    assert _order(app_module, "ORD-LEGAL-2")["payment_status"] == "Cash on Delivery"


def test_failed_delivery_is_never_billed(app_module):
    assert app_module.refund_terms_for({"payment_status": "Paid", "subtotal": "100"}) == (app_module.REFUND_NOT_CHARGED, "0.00")
    assert app_module.refund_terms_for({"payment_status": "Bank Transfer"}) == (app_module.REFUND_NOT_CHARGED, "0.00")


def test_order_page_has_no_card_form_and_says_not_a_tax_invoice():
    from pathlib import Path
    html = (Path(__file__).resolve().parents[2] / "templates" / "invoice.html").read_text()
    assert "cardNumber" not in html and "cc-number" not in html
    assert "not a tax invoice" in html
    assert 'name="accept_terms"' in html and "required" in html


def test_no_google_fonts_anywhere():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    files = list((root / "templates").glob("*.html")) + [root / "frontend" / "index.html", root / "static" / "design-system.css"]
    assert not [f.name for f in files if "fonts.googleapis" in f.read_text() or "fonts.gstatic" in f.read_text()]
