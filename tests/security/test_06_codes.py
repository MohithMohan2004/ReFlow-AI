"""Item 6: the app issues no OTP, reset or magic-link codes of its own (Supabase
Auth owns those; the forgot-password flow only hands Supabase's one-time
token back to Supabase). The one guessable lookup, tanker status by operator ID +
phone, is rate limited."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_app_makes_no_codes_of_its_own():
    src = (ROOT / "app.py").read_text()
    # The only allowed uses: asking Supabase to email a reset link, and
    # giving Supabase its own token back (plus the route's name).
    for allowed in (r"supabase\.auth\.reset_password_for_email\(", r"auth\.verify_otp\(",
                    r"def reset_password\(", r"url_for\(.reset_password.\)"):
        src = re.sub(allowed, "", src)
    assert not re.search(r"\botp\b|verify_otp|reset_password|magic.?link|verification_code", src, re.I)


def test_tanker_status_lookup_is_rate_limited(client):
    codes = [client.post("/api/tanker/status", json={"operator_id": f"OP-{i}", "phone": "9000012345"}).status_code
             for i in range(12)]
    assert codes[:10] == [404] * 10
    assert codes[10] == 429
