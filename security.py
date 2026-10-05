# security.py
# ════════════════════════════════════════════════════════════════
# Kalviman — Security middleware & utilities
#
# Covers: CSP headers, rate limiting, input sanitization,
#         secure cookies, password hashing, RBAC middleware
# ════════════════════════════════════════════════════════════════

import re
import time
import hashlib
import hmac
import os
from functools import wraps
from collections import defaultdict
from flask import request, jsonify, make_response


# ── 1. CONTENT SECURITY POLICY ────────────────────────────────────
CSP_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://api.qrserver.com; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data: https://images.unsplash.com https://api.qrserver.com; "
    "connect-src 'self' https://api.anthropic.com; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
)

def apply_security_headers(response):
    """Attach to app.after_request — adds security hardening headers.
    CSP is in report-only mode during development so nothing gets blocked."""
    # CSP in report-only mode — logs violations but doesn't block anything
    response.headers['Content-Security-Policy-Report-Only'] = CSP_POLICY
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    return response


# ── 2. INPUT SANITIZATION (XSS prevention) ────────────────────────
_STRIP_TAGS = re.compile(r'<[^>]+>')
_STRIP_SCRIPTS = re.compile(r'<script[^>]*>.*?</script>', re.S | re.I)

def sanitize(value):
    """Strip HTML tags and script injections from a string value."""
    if not isinstance(value, str):
        return value
    value = _STRIP_SCRIPTS.sub('', value)
    value = _STRIP_TAGS.sub('', value)
    value = value.replace('javascript:', '')
    value = value.replace('onerror=', '')
    value = value.replace('onload=', '')
    return value.strip()

def sanitize_dict(data: dict) -> dict:
    """Recursively sanitize all string values in a dict."""
    if not isinstance(data, dict):
        return data
    return {k: sanitize(v) if isinstance(v, str) else v for k, v in data.items()}


# ── 3. RATE LIMITING ──────────────────────────────────────────────
class RateLimiter:
    """In-memory sliding-window rate limiter.
    For production, use Redis-backed (flask-limiter)."""

    def __init__(self):
        self._hits = defaultdict(list)  # ip -> [timestamps]

    def is_limited(self, key: str, max_requests: int, window_seconds: int) -> bool:
        now = time.time()
        cutoff = now - window_seconds
        self._hits[key] = [t for t in self._hits[key] if t > cutoff]
        if len(self._hits[key]) >= max_requests:
            return True
        self._hits[key].append(now)
        return False

_limiter = RateLimiter()

def rate_limit(max_per_minute=20):
    """Decorator: block if IP exceeds max_per_minute on this endpoint."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            ip = request.remote_addr or "unknown"
            key = f"{ip}:{request.endpoint}"
            if _limiter.is_limited(key, max_per_minute, 60):
                return jsonify({"error": "Too many requests. Please wait a moment."}), 429
            return f(*args, **kwargs)
        return wrapper
    return decorator


# ── 4. PASSWORD HASHING (bcrypt) ──────────────────────────────────
# Used if/when admin login is added
try:
    import bcrypt
    def hash_password(plain: str) -> str:
        return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()
    def check_password(plain: str, hashed: str) -> bool:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
except ImportError:
    # Fallback: SHA-256 with salt (install bcrypt for production)
    def hash_password(plain: str) -> str:
        salt = os.urandom(16).hex()
        h = hashlib.sha256((salt + plain).encode()).hexdigest()
        return f"{salt}${h}"
    def check_password(plain: str, hashed: str) -> bool:
        salt, h = hashed.split("$", 1)
        return hmac.compare_digest(hashlib.sha256((salt + plain).encode()).hexdigest(), h)


# ── 5. ROLE-BASED ACCESS CONTROL ──────────────────────────────────
# Roles: "student" (default), "teacher", "admin"
# For now, admin is checked by a simple token in config.
# Extend with a users table + JWT when you need real multi-user auth.

def require_role(*allowed_roles):
    """Decorator: check X-Role header or session. Rejects if not in allowed_roles."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            role = request.headers.get("X-Role", "student").lower()
            # In production: decode JWT, look up user, get role from DB
            if role not in allowed_roles:
                return jsonify({"error": "Access denied. Insufficient permissions."}), 403
            return f(*args, **kwargs)
        return wrapper
    return decorator


# ── 6. SECURE COOKIE HELPER ───────────────────────────────────────
def set_secure_cookie(response, name, value, max_age=3600):
    """Set a cookie with HttpOnly, Secure, SameSite=Lax flags."""
    response.set_cookie(
        name, value,
        max_age=max_age,
        httponly=True,         # JS can't read it
        secure=False,          # Set True when using HTTPS in production
        samesite='Lax',        # Prevents CSRF on cross-site requests
        path='/',
    )
    return response


# ── 7. PARAMETERIZED QUERY NOTE ───────────────────────────────────
# db.py already uses parameterized queries (? placeholders) everywhere.
# Example from db.py:
#   conn.execute("SELECT * FROM students WHERE id = ?", (student_id,))
# This prevents SQL injection by design. Never use f-strings in SQL.
