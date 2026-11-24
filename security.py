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
    "forgot_password": ({"POST"}, 5, 600),
    "reset_password": ({"POST"}, 10, 600),
    "api_tanker_status": ({"POST"}, 10, 60),
    "admin_mfa": ({"POST"}, 10, 60),
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
    """Sliding-window counter per key, shared by every gunicorn worker in the
    container through a small SQLite file (pentest PT-02: in-memory counters
    were per worker, so 2 workers allowed nearly twice the limit)."""

    def __init__(self, path=None):
        import os
        import tempfile
        self.path = path or os.path.join(tempfile.gettempdir(), "reflow-ratelimit.sqlite3")
        self._local = threading.local()
        self._calls = 0

    def _conn(self):
        import os
        import sqlite3
        conn = getattr(self._local, "conn", None)
        if conn is None or getattr(self._local, "pid", None) != os.getpid():
            conn = sqlite3.connect(self.path, timeout=5, isolation_level=None)
            conn.execute("pragma journal_mode=wal")
            conn.execute("create table if not exists hits (k text not null, t real not null)")
            conn.execute("create index if not exists hits_k_t on hits (k, t)")
            self._local.conn, self._local.pid = conn, os.getpid()
        return conn

    def hit(self, key, limit, window):
        """Record one request. Returns seconds to wait, or 0 if allowed."""
        import sqlite3
        now = time.time()
        try:
            conn = self._conn()
            conn.execute("begin immediate")
            try:
                conn.execute("delete from hits where k = ? and t <= ?", (key, now - window))
                count, first = conn.execute("select count(*), min(t) from hits where k = ?", (key,)).fetchone()
                if count >= limit:
                    return max(1, int(first + window - now) + 1)
                conn.execute("insert into hits (k, t) values (?, ?)", (key, now))
                self._calls += 1
                if self._calls % 500 == 0:
                    conn.execute("delete from hits where t <= ?", (now - 3600,))
                return 0
            finally:
                conn.execute("commit")
        except sqlite3.Error as e:
            # Never take the site down because the counter file is busy.
            print("SECURITY rate limiter unavailable:", type(e).__name__, e, flush=True)
            return 0

    def reset(self):
        self._conn().execute("delete from hits")


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


MAX_JSON_DEPTH = 64


def json_depth_exceeds(raw, limit=MAX_JSON_DEPTH):
    """True when brackets nest deeper than `limit` (strings skipped). Linear
    scan; stops Python's json parser from hitting its recursion limit
    (pentest PT-01: a 200 KB "[[[[…" body gave a 500)."""
    if raw.count(b"[") + raw.count(b"{") <= limit:   # fast path: can't be deeper
        return False
    depth = 0
    in_string = escaped = False
    for byte in raw:
        if in_string:
            if escaped:
                escaped = False
            elif byte == 0x5C:      # backslash
                escaped = True
            elif byte == 0x22:      # quote
                in_string = False
        elif byte == 0x22:
            in_string = True
        elif byte in (0x5B, 0x7B):  # [ {
            depth += 1
            if depth > limit:
                return True
        elif byte in (0x5D, 0x7D):
            depth -= 1
    return False


def reject_oversized_body():
    """Refuse a too-large body before any view runs. (Werkzeug also enforces
    MAX_CONTENT_LENGTH while reading, but some views catch every exception and
    would turn that 413 into a 500.)"""
    length = request.content_length
    if length is not None and length > MAX_CONTENT_LENGTH:
        return make_response("Request body too large.", 413)
    if request.is_json and length:
        if json_depth_exceeds(request.get_data(cache=True)):
            return make_response(jsonify({"success": False, "error": "Request body is nested too deeply."}), 400)
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
# Allow-list built from every external resource the pages use (fonts are
# self-hosted in static/fonts):
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
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
    "font-src 'self' data:",
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


# ---------------------------------------------------------------------------
# Pentest PT-10: one cross-process data lock
# The app keeps its data as whole files/tables and updates them read-modify-
# write. gunicorn runs several worker processes, and threading locks don't
# reach across processes, so two requests in different workers could each
# read the old table and the second write silently undid the first. Every
# request that may change data now runs under this file lock (shared by all
# workers and the background timeout worker in the container). The app runs
# one replica (MAX_REPLICAS=1); scaling out needs a database lock instead.
# ---------------------------------------------------------------------------

import contextlib as _contextlib
import threading as _threading

DATA_LOCK_TIMEOUT = 30
_lock_state = _threading.local()

# Endpoints proven (call-graph check in the pentest) to never write data, plus
# slow ones that take the lock themselves around their only write.
LOCK_FREE_ENDPOINTS = {
    "static", "health", "home", "current_user", "logout", "api_logout", "api_tanker_status",
    "chatbot", "supply_ocems", "api_ocems_summary", "api_demand_ocems",
    "api_ocems_export_start", "api_ocems_export_status",
    # self-locking: login/signup (plant request), OCEMS connect (vendor test
    # first), geocoding and routing (auto_reset_capacity / transfers file)
    "login", "api_login", "signup", "api_signup", "api_ocems_connection_submit",
    # read-only; calls GitHub, so it must never hold the lock
    "api_app_latest",
    # OCEMS alerts: may wait on the vendor feed; lock only around their writes
    "api_ocems_alerts", "api_ocems_alerts_read",
    # password reset: only end_all_sessions writes, and it locks itself
    "forgot_password", "reset_password",
    "api_search_place", "api_tanker_route",
}


class DataLockTimeout(Exception):
    pass


def _lock_path():
    import os
    import tempfile
    return os.path.join(tempfile.gettempdir(), "reflow-data.lock")


def acquire_data_lock(timeout=DATA_LOCK_TIMEOUT):
    """Take the lock (re-entrant within a thread)."""
    depth = getattr(_lock_state, "depth", 0)
    if depth:
        _lock_state.depth = depth + 1
        return
    try:
        import fcntl
    except ImportError:          # Windows dev machine: single process
        _lock_state.depth, _lock_state.fd = 1, None
        return
    handle = open(_lock_path(), "a+")
    deadline = time.monotonic() + timeout
    while True:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.monotonic() > deadline:
                handle.close()
                raise DataLockTimeout()
            time.sleep(0.01)
    _lock_state.depth, _lock_state.fd = 1, handle


def release_data_lock():
    depth = getattr(_lock_state, "depth", 0)
    if depth > 1:
        _lock_state.depth = depth - 1
        return
    if depth == 1:
        handle = getattr(_lock_state, "fd", None)
        _lock_state.depth, _lock_state.fd = 0, None
        if handle is not None:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_UN)
            handle.close()


@_contextlib.contextmanager
def data_lock(timeout=DATA_LOCK_TIMEOUT):
    acquire_data_lock(timeout)
    try:
        yield
    finally:
        release_data_lock()


def lock_request():
    from flask import g
    if (request.endpoint or "static") in LOCK_FREE_ENDPOINTS:
        return None
    try:
        acquire_data_lock()
    except DataLockTimeout:
        audit("data_lock_timeout", endpoint=request.endpoint)
        return make_response("The server is busy. Try again in a moment.", 503)
    g._holds_data_lock = True
    return None


def unlock_request(_exc=None):
    from flask import g
    if g.pop("_holds_data_lock", False):
        release_data_lock()


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
    app.before_request(lock_request)
    app.teardown_request(unlock_request)
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


# ---------------------------------------------------------------------------
# Admin two-step sign-in: TOTP (RFC 6238), standard library only.
# Works with Google Authenticator, Microsoft Authenticator, Authy, 1Password…
# ---------------------------------------------------------------------------

TOTP_PERIOD = 30
TOTP_DIGITS = 6
MFA_MAX_FAILURES = 5
MFA_LOCK_SECONDS = 15 * 60
MFA_PENDING_SECONDS = 5 * 60
ADMIN_SESSION_SECONDS = 12 * 3600


def new_totp_secret():
    import base64
    import secrets
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def totp_code(secret, step):
    import base64
    import hashlib
    import hmac
    import struct
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** TOTP_DIGITS)
    return str(number).zfill(TOTP_DIGITS)


def totp_match(secret, code, last_step=-1, now=None):
    """The time step the code belongs to (now, or one step either side for
    clock drift), or None. A step at or before last_step is refused, so a
    code can't be used twice."""
    import hmac
    import time
    code = "".join(ch for ch in str(code or "") if ch.isdigit())
    if len(code) != TOTP_DIGITS:
        return None
    step = int((time.time() if now is None else now) // TOTP_PERIOD)
    for candidate in (step - 1, step, step + 1):
        if candidate <= int(last_step) or candidate < 0:
            continue
        if hmac.compare_digest(totp_code(secret, candidate), code):
            return candidate
    return None


def otpauth_uri(secret, account):
    from urllib.parse import quote
    return (f"otpauth://totp/ReFlow:{quote(account)}?secret={secret}"
            f"&issuer=ReFlow&digits={TOTP_DIGITS}&period={TOTP_PERIOD}")


def _mfa_fernet():
    import base64
    import hashlib
    import os
    from cryptography.fernet import Fernet, MultiFernet
    keys = []
    for name in ("MFA_KEY_SECRET", "FLASK_SECRET_KEY"):
        value = (os.getenv(name) or "").strip()
        if value:
            digest = hashlib.sha256(("reflow-admin-mfa:" + value).encode()).digest()
            keys.append(Fernet(base64.urlsafe_b64encode(digest)))
    return MultiFernet(keys)


def encrypt_mfa_secret(secret):
    return _mfa_fernet().encrypt(secret.encode()).decode()


def decrypt_mfa_secret(token):
    try:
        return _mfa_fernet().decrypt(str(token or "").encode()).decode()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Pentest PT-08: numbers from requests must be finite
# Python's float() accepts "nan", "inf" and "1e309"; NaN slips past every
# "< 0" check and is written to JSON as NaN, which browsers can't parse.
# ---------------------------------------------------------------------------

def finite_float(value, minimum=None, maximum=None):
    """float(value), but ValueError for NaN/Infinity or outside the range."""
    import math
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("not a finite number")
    if minimum is not None and number < minimum:
        raise ValueError("too small")
    if maximum is not None and number > maximum:
        raise ValueError("too large")
    return number
