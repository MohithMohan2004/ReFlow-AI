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


def audit(event, **fields):
    """One line per security event on stdout (collected by Azure logs).
    Values are cut short and stripped of control characters so a crafted
    email or path can't forge log lines. Never pass passwords or keys."""
    from flask import has_request_context, session
    data = {"event": event}
    if has_request_context():
        data.update(ip=client_ip(), method=request.method, path=request.path,
                    user=session.get("user_id") or "-", role=session.get("role") or "-")
    data.update(fields)
    clean = " ".join(
        f"{k}={''.join(ch if ch.isprintable() and ch != ' ' else '_' for ch in str(v))[:120]}"
        for k, v in data.items()
    )
    print("SECURITY " + clean, flush=True)


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
        audit("rate_limited", endpoint=request.endpoint)
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


# ---------------------------------------------------------------------------
# Extra D: CSRF. Every state-changing request from a browser must come from
# this site. Browsers always send Origin (or at least Referer) on cross-site
# POSTs, so a forged request is refused. Requests with neither header come
# from non-browser clients (scripts, the Flutter client), which carry no
# victim's cookies; SameSite=Lax is the second layer.
# ---------------------------------------------------------------------------

SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def _trusted_origins():
    import os
    extra = os.getenv("CSRF_TRUSTED_ORIGINS", "")
    return {o.strip().rstrip("/").lower() for o in extra.split(",") if o.strip()}


def check_same_origin():
    if request.method in SAFE_METHODS:
        return None
    from urllib.parse import urlsplit
    origin = request.headers.get("Origin")
    source = origin if origin is not None else request.headers.get("Referer")
    if source is None:
        return None
    source = source.strip()
    parts = urlsplit(source)
    ok = (
        source.lower() != "null"
        and parts.scheme in ("http", "https")
        and (
            parts.netloc.lower() == request.host.lower()
            or f"{parts.scheme}://{parts.netloc}".lower() in _trusted_origins()
        )
    )
    if ok:
        return None
    audit("csrf_blocked", origin=source)
    message = "This request came from another site and was blocked."
    if request.path.startswith("/api/") or request.is_json:
        return make_response(jsonify({"success": False, "error": message, "message": message}), 403)
    return make_response(message, 403)


# ---------------------------------------------------------------------------
# Extra E: security headers
# Allow-list built from every external resource the pages use: Google Fonts,
# Leaflet / leaflet.heat (jsDelivr), Chart.js (cdnjs), OpenStreetMap tiles,
# Nominatim geocoding and OSRM routing called from the browser.
# Inline scripts run only with this request's nonce (Jinja pages) or a
# hash of the built SPA shell's own bootstrap script: no 'unsafe-inline' for
# scripts, so injected markup can't run code. Styles keep 'unsafe-inline'
# because the templates use style="" attributes (no script runs from CSS).
# ---------------------------------------------------------------------------

CONTENT_SECURITY_POLICY = "; ".join([
    "default-src 'self'",
    "script-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net",
    "font-src 'self' data: https://fonts.gstatic.com",
    "img-src 'self' data: blob: https://tile.openstreetmap.org https://*.tile.openstreetmap.org",
    "connect-src 'self' https://nominatim.openstreetmap.org https://router.project-osrm.org",
    "frame-src 'none'",
    "frame-ancestors 'none'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "manifest-src 'self'",
    "worker-src 'self' blob:",
])


SPA_SCRIPT_HASHES = []   # filled by remember_spa_scripts() at startup


def csp_nonce():
    """This request's script nonce (one per request, made on first use)."""
    from flask import g
    import secrets
    nonce = getattr(g, "csp_nonce", None)
    if not nonce:
        nonce = g.csp_nonce = secrets.token_urlsafe(18)
    return nonce


def inline_script_hashes(html):
    """CSP hashes of every inline <script> body in a static HTML page."""
    import base64
    import hashlib
    bodies = _re_mod().findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, _re_mod().S)
    return ["'sha256-" + base64.b64encode(hashlib.sha256(b.encode("utf-8")).digest()).decode() + "'" for b in bodies]


def _re_mod():
    import re
    return re


def remember_spa_scripts(index_path):
    """Allow the built React shell's own inline bootstrap script by hash.
    Called once at startup; a new build means a new deploy and a restart."""
    global SPA_SCRIPT_HASHES
    try:
        with open(index_path, encoding="utf-8") as f:
            SPA_SCRIPT_HASHES = inline_script_hashes(f.read())
    except OSError:
        SPA_SCRIPT_HASHES = []


def content_security_policy():
    extra = " ".join([f"'nonce-{csp_nonce()}'", *SPA_SCRIPT_HASHES])
    return CONTENT_SECURITY_POLICY.replace("script-src 'self'", f"script-src 'self' {extra}", 1)


def set_security_headers(response):
    headers = response.headers
    headers.setdefault("Content-Security-Policy", content_security_policy())
    headers.setdefault("X-Content-Type-Options", "nosniff")
    headers.setdefault("X-Frame-Options", "DENY")
    headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    headers.setdefault("Permissions-Policy", "geolocation=(self), camera=(), microphone=(), payment=(), usb=()")
    headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    if request.is_secure:  # https, as reported by the Azure ingress (item 11)
        headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


def init_app(app):
    # Item 11: exactly one proxy (the Azure Container Apps ingress) sits in
    # front of gunicorn. Trust only the last X-Forwarded-For entry (the one the
    # ingress appended) and X-Forwarded-Proto; never the forwarded Host.
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=0, x_port=0, x_prefix=0)

    app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
    app.jinja_env.globals["csp_nonce"] = csp_nonce
    app.before_request(reject_oversized_body)
    app.before_request(check_same_origin)
    app.before_request(check_rate_limit)
    app.after_request(set_cache_headers)
    app.after_request(set_security_headers)


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
