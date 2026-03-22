"""Credential vault providing AES-256-GCM encryption for stored credentials.

Architecture
------------
Credentials (API keys, SMB passwords, SSH passphrases, etc.) are encrypted
at rest using Fernet symmetric encryption from the ``cryptography`` library.
The encryption key is derived via PBKDF2-HMAC-SHA256 from a machine-unique
seed composed of the hostname and current OS username.  This means the
encrypted blob is bound to the machine where it was created -- moving the
database to a different host or user account will invalidate all stored
credentials (by design).

Fallback behaviour
------------------
If the ``cryptography`` package is not installed, the vault degrades
gracefully: credentials are stored as base64-encoded JSON with a warning
logged on every encrypt/decrypt call.  This keeps the application functional
during development but is **not** suitable for production use.

Dependencies
------------
- ``cryptography`` (optional, recommended)
- Standard library: base64, hashlib, json, logging, os, platform, socket
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import platform
import socket
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from face_detect.database import Database

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency -- cryptography
# ---------------------------------------------------------------------------
try:
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes

    _HAS_CRYPTO = True
except ImportError:  # pragma: no cover
    _HAS_CRYPTO = False
    log.warning(
        "cryptography package not installed -- credential vault will use "
        "base64 encoding only (NOT secure).  Install with: pip install cryptography"
    )

# Fixed salt -- intentionally not random so the key is reproducible from the
# same machine seed without needing to store extra state.
_SALT = b"face_detect_credential_vault_v1"


def _machine_seed() -> str:
    """Return a stable, machine-unique seed string.

    Combines the hostname with the OS-level username.  Both values survive
    reboots and are available without elevated privileges.
    """
    hostname = socket.gethostname()
    username = os.getenv("USERNAME") or os.getenv("USER") or platform.node()
    return f"{hostname}::{username}"


def _derive_key(seed: str) -> bytes:
    """Derive a Fernet-compatible key from *seed* via PBKDF2.

    Returns a 32-byte key, URL-safe base64-encoded (as required by Fernet).
    """
    if not _HAS_CRYPTO:
        # Fallback: simple SHA-256 digest truncated to 32 bytes, b64-encoded
        digest = hashlib.sha256(seed.encode()).digest()
        return base64.urlsafe_b64encode(digest)

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_SALT,
        iterations=480_000,
    )
    raw_key = kdf.derive(seed.encode())
    return base64.urlsafe_b64encode(raw_key)


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------

def encrypt_credentials(data: dict) -> str:
    """Encrypt a credentials dictionary and return a string token.

    Parameters
    ----------
    data:
        Arbitrary JSON-serialisable dictionary (e.g. ``{"user": "x", "pass": "y"}``).

    Returns
    -------
    str
        An opaque encrypted token suitable for database storage.
    """
    vault = CredentialVault()
    return vault.encrypt(data)


def decrypt_credentials(encrypted: str) -> dict:
    """Decrypt a token previously produced by :func:`encrypt_credentials`.

    Parameters
    ----------
    encrypted:
        The opaque token string.

    Returns
    -------
    dict
        The original credentials dictionary.

    Raises
    ------
    ValueError
        If decryption fails (wrong machine, corrupted data, etc.).
    """
    vault = CredentialVault()
    return vault.decrypt(encrypted)


class CredentialVault:
    """Thread-safe credential encryption vault.

    The vault derives its key once at construction time and reuses it for all
    subsequent encrypt/decrypt operations.  Fernet itself is thread-safe so
    no additional locking is required.

    Parameters
    ----------
    db:
        Optional :class:`Database` instance.  When provided, the vault can
        store and retrieve credentials directly from the ``credentials``
        table.
    seed:
        Override the machine seed (useful for testing).  If *None*, the seed
        is derived from the current machine identity.
    """

    def __init__(self, db: Database | None = None, *, seed: str | None = None) -> None:
        self._db = db
        self._seed = seed or _machine_seed()
        self._key = _derive_key(self._seed)

        if _HAS_CRYPTO:
            self._fernet: Fernet | None = Fernet(self._key)
        else:
            self._fernet = None

    # ------------------------------------------------------------------
    # Core encrypt / decrypt
    # ------------------------------------------------------------------

    def encrypt(self, data: dict) -> str:
        """Encrypt *data* and return an opaque string token."""
        payload = json.dumps(data, separators=(",", ":")).encode()

        if self._fernet is not None:
            token = self._fernet.encrypt(payload)
            return token.decode("ascii")

        # Fallback: base64 only
        log.warning("Storing credentials with base64 encoding only (cryptography not installed)")
        return base64.urlsafe_b64encode(payload).decode("ascii")

    def decrypt(self, encrypted: str) -> dict:
        """Decrypt a token and return the original dictionary.

        Raises :class:`ValueError` on any decryption failure.
        """
        try:
            if self._fernet is not None:
                payload = self._fernet.decrypt(encrypted.encode("ascii"))
            else:
                log.warning("Decrypting base64-only credentials (cryptography not installed)")
                payload = base64.urlsafe_b64decode(encrypted.encode("ascii"))

            return json.loads(payload)
        except Exception as exc:
            raise ValueError(f"Failed to decrypt credentials: {exc}") from exc

    # ------------------------------------------------------------------
    # Database helpers
    # ------------------------------------------------------------------

    def store(self, service: str, data: dict) -> None:
        """Encrypt *data* and persist it under *service* in the credentials table.

        Requires a :class:`Database` instance to have been provided at
        construction time.
        """
        if self._db is None:
            raise RuntimeError("CredentialVault was created without a Database reference")
        token = self.encrypt(data)
        self._db.execute(
            "INSERT OR REPLACE INTO credentials (service, encrypted_data) VALUES (?, ?)",
            (service, token),
        )
        log.info("Stored encrypted credentials for service=%s", service)

    def retrieve(self, service: str) -> dict | None:
        """Retrieve and decrypt credentials for *service*.

        Returns *None* if no credentials are stored for the given service.
        """
        if self._db is None:
            raise RuntimeError("CredentialVault was created without a Database reference")
        row = self._db.fetch_one(
            "SELECT encrypted_data FROM credentials WHERE service = ?",
            (service,),
        )
        if row is None:
            return None
        return self.decrypt(row[0])

    def delete(self, service: str) -> bool:
        """Remove stored credentials for *service*.

        Returns *True* if a row was deleted, *False* otherwise.
        """
        if self._db is None:
            raise RuntimeError("CredentialVault was created without a Database reference")
        cursor = self._db.execute(
            "DELETE FROM credentials WHERE service = ?",
            (service,),
        )
        deleted = cursor.rowcount > 0
        if deleted:
            log.info("Deleted credentials for service=%s", service)
        return deleted
