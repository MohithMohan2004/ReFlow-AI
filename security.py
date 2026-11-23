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


def init_app(app):
    app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
    app.before_request(reject_oversized_body)
    app.before_request(check_rate_limit)
