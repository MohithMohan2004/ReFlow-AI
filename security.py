"""Request-level security controls for ReFlow.

Kept out of app.py so each control is small and testable on its own.
"""

import threading
import time
from collections import deque

from flask import jsonify, make_response, request


# ---------------------------------------------------------------------------
# Item 1: request size limit and rate limiting
# ---------------------------------------------------------------------------

# 5 MB PDF upload (the largest legitimate body) plus multipart overhead.
MAX_CONTENT_LENGTH = 6 * 1024 * 1024

# endpoint -> (methods counted, max requests, window seconds)
# Only expensive or guessable endpoints are limited; normal page use stays far
# below these numbers. The app runs as a single replica (MAX_REPLICAS=1), so an
# in-process limiter sees every request.
RATE_LIMITS = {
    "login": ({"POST"}, 10, 60),
    "api_login": ({"POST"}, 10, 60),
    "signup": ({"POST"}, 5, 600),
    "api_signup": ({"POST"}, 5, 600),
    "api_tanker_status": ({"POST"}, 10, 60),
    "chatbot": ({"POST"}, 20, 60),
    "api_search_place": ({"GET"}, 30, 60),
    "api_tanker_route": ({"GET"}, 30, 60),
    "create_order": ({"POST"}, 20, 60),
    "api_ocems_export_start": ({"POST"}, 5, 600),
    "api_ocems_connection_submit": ({"POST"}, 10, 600),
    "stp_register": ({"POST"}, 5, 600),
    "tanker_register_contracted": ({"POST"}, 5, 600),
    "tanker_register_independent": ({"POST"}, 5, 600),
}

# Per-account limit for sign-in, on top of the per-IP one, so one account
# can't be brute-forced from many addresses.
ACCOUNT_LOGIN_LIMIT = (20, 900)


class RateLimiter:
    """Sliding-window counter per key, in memory and thread-safe."""

    def __init__(self, max_keys=50_000):
        self._hits = {}
        self._lock = threading.Lock()
        self._max_keys = max_keys

    def hit(self, key, limit, window):
        """Record one request. Returns seconds to wait, or 0 if allowed."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                if len(self._hits) >= self._max_keys:
                    self._prune(now)
                hits = self._hits[key] = deque()
            while hits and hits[0] <= now - window:
                hits.popleft()
            if len(hits) >= limit:
                return max(1, int(hits[0] + window - now) + 1)
            hits.append(now)
            return 0

    def _prune(self, now, longest_window=3600):
        for key in [k for k, v in self._hits.items() if not v or v[-1] <= now - longest_window]:
            del self._hits[key]
        if len(self._hits) >= self._max_keys:
            self._hits.clear()

    def reset(self):
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def client_ip():
    """The caller's address. ProxyFix (item 11) has already replaced
    remote_addr with the address the Azure ingress saw."""
    return request.remote_addr or "unknown"


def _too_many(retry_after):
    message = "Too many requests. Wait a moment and try again."
    if request.path.startswith("/api/") or request.is_json:
        body = jsonify({"success": False, "error": message, "message": message})
    else:
        body = message
    response = make_response(body, 429)
    response.headers["Retry-After"] = str(retry_after)
    return response


def _login_account():
    data = request.get_json(silent=True) if request.is_json else None
    source = data if isinstance(data, dict) else request.form
    value = source.get("login_identifier") or source.get("email") or ""
    return str(value).strip().lower()[:254]


def check_rate_limit():
    rule = RATE_LIMITS.get(request.endpoint or "")
    if not rule or request.method not in rule[0]:
        return None
    _methods, limit, window = rule
    wait = limiter.hit(f"{request.endpoint}:ip:{client_ip()}", limit, window)
    if not wait and request.endpoint in ("login", "api_login"):
        account = _login_account()
        if account:
            wait = limiter.hit(f"login:acct:{account}", *ACCOUNT_LOGIN_LIMIT)
    if wait:
        return _too_many(wait)
    return None


def reject_oversized_body():
    """Refuse a too-large body before any view runs. (Werkzeug also enforces
    MAX_CONTENT_LENGTH while reading, but some views catch every exception and
    would turn that 413 into a 500.)"""
    length = request.content_length
    if length is not None and length > MAX_CONTENT_LENGTH:
        return make_response("Request body too large.", 413)
    return None


# ---------------------------------------------------------------------------
# Item 10: never let a shared cache keep API data or a logged-in page
# ---------------------------------------------------------------------------

def set_cache_headers(response):
    """/api/* and every page shown to a logged-in user: no-store. Hashed
    assets under /static/app/assets/ keep their year-long cache (app.py)."""
    if request.path.startswith("/static/"):
        return response
    from flask import session
    private = request.path.startswith("/api/") or (
        session.get("user_id") and response.mimetype == "text/html"
    )
    if private:
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        response.vary.add("Cookie")
    return response


def init_app(app):
    # Item 11: exactly one proxy (the Azure Container Apps ingress) sits in
    # front of gunicorn. Trust only the last X-Forwarded-For entry (the one the
    # ingress appended) and X-Forwarded-Proto; never the forwarded Host.
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=0, x_port=0, x_prefix=0)

    app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
    app.before_request(reject_oversized_body)
    app.before_request(check_rate_limit)
    app.after_request(set_cache_headers)


# ---------------------------------------------------------------------------
# Item 2: length limits on identity fields
# ---------------------------------------------------------------------------

MAX_EMAIL_LENGTH = 254          # RFC 5321 path limit
MAX_PASSWORD_BYTES = 72         # bcrypt (Supabase Auth) ignores anything after 72 bytes
MIN_PASSWORD_LENGTH = 8
MAX_NAME_LENGTH = 100
MAX_USERNAME_LENGTH = 32
MAX_MOBILE_LENGTH = 15


def password_too_long(password):
    return len(str(password or "").encode("utf-8")) > MAX_PASSWORD_BYTES


def signup_field_error(email, password, username="", first_name="", last_name="", mobile=""):
    """Server-side limits for signup. Returns a message, or None if fine."""
    if len(email) > MAX_EMAIL_LENGTH:
        return "Email address is too long."
    if password_too_long(password):
        return "Password must be at most 72 bytes (about 72 letters or digits)."
    if len(username) > MAX_USERNAME_LENGTH:
        return f"Username must be at most {MAX_USERNAME_LENGTH} characters."
    if len(first_name) > MAX_NAME_LENGTH or len(last_name) > MAX_NAME_LENGTH:
        return f"Names must be at most {MAX_NAME_LENGTH} characters."
    if len(mobile) > MAX_MOBILE_LENGTH:
        return "Mobile number is too long."
    return None


def login_fields_invalid(email, password):
    """True when sign-in input can't belong to any valid account."""
    return len(email) > MAX_EMAIL_LENGTH or password_too_long(password)


# ---------------------------------------------------------------------------
# Item 18 / Extra F: uploads are checked by content
# ---------------------------------------------------------------------------

def looks_like_pdf(stream):
    """True if the file starts with the PDF signature (within the first 1 KB,
    as the PDF spec allows). Leaves the stream at the start."""
    position = stream.tell()
    head = stream.read(1024)
    stream.seek(position)
    return b"%PDF-" in head[:1024] and not head.lstrip().startswith((b"PK", b"<?xml", b"<"))


# ---------------------------------------------------------------------------
# Item 20: one normalisation for every identity string
# ---------------------------------------------------------------------------

import re as _re
import unicodedata as _unicodedata

USERNAME_RE = _re.compile(r"[a-z0-9][a-z0-9._-]{3,31}")
EMAIL_ASCII_RE = _re.compile(r"[a-z0-9!#$%&'*+/=?^_`{|}~.-]+@[a-z0-9-]+(\.[a-z0-9-]+)+")


def normalize_identity(value):
    """NFKC + casefold + strip: "ᴮᴵᴳᴮᴵᴿᴰ" and "ＢＩＧＢＩＲＤ" both become
    "bigbird". Use it wherever an email or username is stored, looked up or
    compared, before any uniqueness check."""
    return _unicodedata.normalize("NFKC", str(value or "")).casefold().strip()


def identity_error(email, username=None):
    """Reject look-alike characters: emails must be plain ASCII after
    normalising (no Cyrillic "а" for Latin "a"), usernames a-z 0-9 . _ -"""
    if email and not EMAIL_ASCII_RE.fullmatch(email):
        return "Enter an email address using plain letters (a-z), digits and . _ + -"
    if username is not None and not USERNAME_RE.fullmatch(username):
        return "Usernames are 4-32 characters: letters, digits, dot, underscore or hyphen."
    return None


# ---------------------------------------------------------------------------
# Extra B: settings from the environment
# ---------------------------------------------------------------------------

def env_flag(name, default):
    """Read a yes/no setting: 0/false/no/off -> False, 1/true/yes/on -> True."""
    import os
    value = str(os.getenv(name, "")).strip().lower()
    if value in ("0", "false", "no", "off"):
        return False
    if value in ("1", "true", "yes", "on"):
        return True
    return default
