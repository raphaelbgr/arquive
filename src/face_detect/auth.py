"""Authentication module for Arquive.

Supports three security levels:
  - ``simple-password``: single shared password, JWT in httpOnly cookie
  - ``user-account``: per-user credentials with roles (admin / viewer)
  - ``forever``: no authentication required

Passwords are hashed with bcrypt.  Sessions are JWT tokens signed with
HS256 and stored in httpOnly cookies (1-year default TTL).  Session
revocation works via a ``jwt_issued_after`` timestamp in the settings
table — tokens issued before that timestamp are rejected.

Dependencies: PyJWT, bcrypt, flask
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any

from flask import Request, jsonify, request

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Password hashing — bcrypt with fallback to hashlib if bcrypt unavailable
# ---------------------------------------------------------------------------

try:
    import bcrypt

    def hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    def verify_password(password: str, hashed: str) -> bool:
        return bcrypt.checkpw(password.encode(), hashed.encode())

except ImportError:
    log.warning("bcrypt not installed — falling back to PBKDF2 (install bcrypt for production)")

    def hash_password(password: str) -> str:  # type: ignore[misc]
        salt = secrets.token_hex(16)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000)
        return f"pbkdf2:{salt}:{dk.hex()}"

    def verify_password(password: str, hashed: str) -> bool:  # type: ignore[misc]
        _, salt, stored = hashed.split(":")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000)
        return hmac.compare_digest(dk.hex(), stored)

# ---------------------------------------------------------------------------
# JWT — using PyJWT with fallback to a minimal HMAC-based token
# ---------------------------------------------------------------------------

try:
    import jwt as pyjwt

    def create_token(payload: dict, secret: str, expires_delta: timedelta) -> str:
        payload = {**payload, "exp": datetime.now(timezone.utc) + expires_delta, "iat": datetime.now(timezone.utc)}
        return pyjwt.encode(payload, secret, algorithm="HS256")

    def decode_token(token: str, secret: str) -> dict | None:
        try:
            return pyjwt.decode(token, secret, algorithms=["HS256"])
        except (pyjwt.ExpiredSignatureError, pyjwt.InvalidTokenError):
            return None

except ImportError:
    import base64
    import json as _json

    log.warning("PyJWT not installed — using minimal HMAC tokens (install PyJWT for production)")

    def create_token(payload: dict, secret: str, expires_delta: timedelta) -> str:  # type: ignore[misc]
        payload = {**payload, "exp": int(time.time() + expires_delta.total_seconds()), "iat": int(time.time())}
        data = base64.urlsafe_b64encode(_json.dumps(payload).encode()).decode()
        sig = hmac.new(secret.encode(), data.encode(), "sha256").hexdigest()
        return f"{data}.{sig}"

    def decode_token(token: str, secret: str) -> dict | None:  # type: ignore[misc]
        try:
            data, sig = token.rsplit(".", 1)
            expected = hmac.new(secret.encode(), data.encode(), "sha256").hexdigest()
            if not hmac.compare_digest(sig, expected):
                return None
            payload = _json.loads(base64.urlsafe_b64decode(data))
            if payload.get("exp", 0) < time.time():
                return None
            return payload
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Duration parsing
# ---------------------------------------------------------------------------

def parse_duration(s: str) -> timedelta:
    """Parse a duration string like '365d', '24h', '30m', or 'forever'."""
    if s == "forever":
        return timedelta(days=36500)
    s = s.strip().lower()
    if s.endswith("d"):
        return timedelta(days=int(s[:-1]))
    if s.endswith("h"):
        return timedelta(hours=int(s[:-1]))
    if s.endswith("m"):
        return timedelta(minutes=int(s[:-1]))
    return timedelta(days=int(s))


# ---------------------------------------------------------------------------
# AuthManager — stateless, works with Database for storage
# ---------------------------------------------------------------------------

class AuthManager:
    """Manages authentication state.

    Requires a ``Database`` instance for user/settings storage and a
    ``Config`` instance for auth configuration.
    """

    def __init__(self, db: Any, config: Any) -> None:
        self.db = db
        self.config = config
        self._ensure_jwt_secret()

    @property
    def sec_level(self) -> str:
        return self.config.auth.sec_level

    @property
    def jwt_secret(self) -> str:
        return self.db.get_setting("jwt_secret", "")

    def _ensure_jwt_secret(self) -> None:
        """Generate and persist a JWT signing secret if none exists."""
        if not self.db.get_setting("jwt_secret"):
            secret = secrets.token_urlsafe(48)
            self.db.set_setting("jwt_secret", secret)
            log.info("Generated new JWT signing secret")

    def _token_ttl(self) -> timedelta:
        return parse_duration(self.config.auth.session_duration)

    # --- Simple-password mode ---

    def set_password(self, password: str) -> None:
        self.db.set_setting("server_password_hash", hash_password(password))

    def check_password(self, password: str) -> bool:
        stored = self.db.get_setting("server_password_hash")
        if not stored:
            return False
        return verify_password(password, stored)

    def get_or_create_password(self) -> str | None:
        """Return existing password hint or generate a random one.

        Returns the cleartext password ONLY when it was just generated
        (so the CLI can print it).  Returns None if a password already exists.
        """
        if self.db.get_setting("server_password_hash"):
            return None
        password = secrets.token_urlsafe(12)
        self.set_password(password)
        return password

    # --- User-account mode ---

    def create_user(self, username: str, password: str, role: str = "user") -> int:
        return self.db.add_user(username, hash_password(password), role)

    def authenticate_user(self, username: str, password: str) -> dict | None:
        user = self.db.get_user(username)
        if not user:
            return None
        if not verify_password(password, user["password_hash"]):
            return None
        self.db.update_user_login(username)
        return user

    # --- Token management ---

    def issue_token(self, subject: str, role: str = "user") -> str:
        return create_token(
            {"sub": subject, "role": role},
            self.jwt_secret,
            self._token_ttl(),
        )

    def validate_token(self, token: str) -> dict | None:
        payload = decode_token(token, self.jwt_secret)
        if not payload:
            return None
        # Check revocation: tokens issued before jwt_issued_after are invalid
        issued_after = self.db.get_setting("jwt_issued_after")
        if issued_after:
            iat = payload.get("iat", 0)
            cutoff = datetime.fromisoformat(issued_after).replace(tzinfo=timezone.utc).timestamp()
            # Use <= so tokens issued in the same second as revocation are also rejected
            if iat <= cutoff:
                return None
        return payload

    def revoke_all_sessions(self) -> None:
        """Invalidate all existing tokens by bumping the issued-after cutoff."""
        self.db.set_setting("jwt_issued_after", datetime.now(timezone.utc).isoformat())
        log.info("All sessions revoked")

    # --- Flask integration ---

    def login_required(self, f):
        """Flask route decorator — rejects unauthenticated requests."""
        @wraps(f)
        def decorated(*args, **kwargs):
            if self.sec_level == "forever":
                return f(*args, **kwargs)
            token = request.cookies.get("arquive_token") or _bearer_token(request)
            if not token:
                return jsonify({"error": "Authentication required"}), 401
            payload = self.validate_token(token)
            if not payload:
                return jsonify({"error": "Invalid or expired token"}), 401
            request.user = payload  # type: ignore[attr-defined]
            return f(*args, **kwargs)
        return decorated

    def admin_required(self, f):
        """Flask route decorator — requires admin role."""
        @wraps(f)
        @self.login_required
        def decorated(*args, **kwargs):
            user = getattr(request, "user", {})
            if user.get("role") != "admin":
                return jsonify({"error": "Admin access required"}), 403
            return f(*args, **kwargs)
        return decorated


def _bearer_token(req: Request) -> str | None:
    auth = req.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None
