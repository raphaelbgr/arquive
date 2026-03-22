"""FTP/FTPS media source for indexing files on remote FTP servers.

Architecture
------------
``FTPSource`` connects to an FTP server using Python's standard
:mod:`ftplib` and recursively walks the directory tree starting from the
configured path.  File metadata (name, size, modification time) is extracted
from ``MLSD`` responses when available, falling back to ``LIST`` parsing for
legacy servers.

TLS is enabled by default via :class:`ftplib.FTP_TLS`.  Set ``use_tls=False``
to connect over plain FTP (not recommended).

Dependencies
------------
- Standard library: ftplib, logging, os, posixpath
"""

from __future__ import annotations

import ftplib
import logging
import os
import posixpath
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from face_detect.database import Database

log = logging.getLogger(__name__)


class FTPSource:
    """Index media files from an FTP or FTPS server.

    Parameters
    ----------
    library_id:
        The library row ID that owns these files.
    host:
        FTP server hostname or IP address.
    path:
        Remote directory to scan (e.g. ``/media/photos``).
    db:
        Database instance for persisting indexed files.
    credentials:
        Optional dict with ``username`` and ``password`` keys.  Defaults
        to anonymous login when *None*.
    use_tls:
        When *True* (the default) connect via FTPS (explicit TLS).
    port:
        FTP server port.  Defaults to 21.
    """

    def __init__(
        self,
        library_id: int,
        host: str,
        path: str,
        db: Database,
        credentials: dict | None = None,
        use_tls: bool = True,
        port: int = 21,
    ) -> None:
        self.library_id = library_id
        self.host = host
        self.port = port
        self.remote_path = path.rstrip("/") or "/"
        self._db = db
        self._credentials = credentials or {}
        self._use_tls = use_tls
        self._ftp: ftplib.FTP | ftplib.FTP_TLS | None = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Establish the FTP(S) connection and authenticate."""
        username = self._credentials.get("username", "anonymous")
        password = self._credentials.get("password", "anonymous@")

        log.info(
            "Connecting to FTP%s server %s:%d as %s",
            "S" if self._use_tls else "",
            self.host,
            self.port,
            username,
        )

        if self._use_tls:
            ftp = ftplib.FTP_TLS()
            ftp.connect(self.host, self.port, timeout=30)
            ftp.login(username, password)
            ftp.prot_p()  # Switch to protected (encrypted) data connection
            self._ftp = ftp
        else:
            ftp = ftplib.FTP()
            ftp.connect(self.host, self.port, timeout=30)
            ftp.login(username, password)
            self._ftp = ftp

        log.info("FTP connection established: %s", self._ftp.getwelcome())

    def disconnect(self) -> None:
        """Gracefully close the FTP connection."""
        if self._ftp is not None:
            try:
                self._ftp.quit()
            except (ftplib.error_reply, OSError):
                try:
                    self._ftp.close()
                except OSError:
                    pass
            finally:
                self._ftp = None
            log.info("FTP connection closed: %s", self.host)

    def __enter__(self) -> FTPSource:
        self.connect()
        return self

    def __exit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: object) -> None:
        self.disconnect()

    # ------------------------------------------------------------------
    # Scanning
    # ------------------------------------------------------------------

    def scan(self) -> int:
        """Recursively walk the remote path and index all files.

        Automatically connects if not already connected.

        Returns
        -------
        int
            Number of files newly indexed or updated.
        """
        if self._ftp is None:
            self.connect()

        assert self._ftp is not None  # for type checker

        log.info(
            "Starting FTP scan: library_id=%d host=%s path=%s",
            self.library_id,
            self.host,
            self.remote_path,
        )

        count = self._walk_directory(self.remote_path)

        log.info(
            "FTP scan complete: library_id=%d indexed=%d host=%s",
            self.library_id,
            count,
            self.host,
        )
        return count

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _walk_directory(self, directory: str) -> int:
        """Recursively list *directory* and index files."""
        assert self._ftp is not None
        count = 0

        try:
            entries = list(self._ftp.mlsd(directory, facts=["type", "size", "modify"]))
        except ftplib.error_perm:
            # MLSD not supported -- fall back to NLST
            log.debug("MLSD not supported, falling back to NLST for %s", directory)
            entries = self._nlst_fallback(directory)

        for name, facts in entries:
            if name in (".", ".."):
                continue

            full_path = posixpath.join(directory, name)
            entry_type = facts.get("type", "file").lower()

            if entry_type == "dir":
                try:
                    count += self._walk_directory(full_path)
                except ftplib.error_perm:
                    log.warning("Permission denied descending into: %s", full_path)
            elif entry_type == "file":
                try:
                    indexed = self._index_entry(full_path, name, facts)
                    if indexed:
                        count += 1
                except Exception:
                    log.exception("Failed to index FTP file: %s", full_path)

        return count

    def _nlst_fallback(self, directory: str) -> list[tuple[str, dict]]:
        """Use NLST when MLSD is unavailable.

        Returns entries in the same ``(name, facts)`` format as MLSD but
        with empty facts (metadata unavailable).
        """
        assert self._ftp is not None
        entries: list[tuple[str, dict]] = []

        try:
            names = self._ftp.nlst(directory)
        except ftplib.error_perm:
            return entries

        for full in names:
            name = posixpath.basename(full)
            if name in (".", ".."):
                continue
            # We cannot distinguish files from dirs via NLST alone; assume
            # file and let directory descent fail gracefully.
            entries.append((name, {"type": "file"}))

        return entries

    def _index_entry(self, full_path: str, filename: str, facts: dict) -> bool:
        """Upsert a single remote file into the database.

        Returns *True* if the row was written.
        """
        relative = full_path
        if full_path.startswith(self.remote_path):
            relative = full_path[len(self.remote_path):].lstrip("/")

        # Parse modification time from MLSD facts (format: YYYYMMDDHHMMSS).
        modify_str = facts.get("modify", "")
        modified_at_iso = self._parse_ftp_timestamp(modify_str)

        existing = self._db.fetch_one(
            "SELECT modified_at FROM files WHERE library_id = ? AND relative_path = ?",
            (self.library_id, relative),
        )
        if existing is not None and existing[0] == modified_at_iso:
            return False

        size_bytes = int(facts.get("size", 0))
        ext = os.path.splitext(filename)[1].lower().lstrip(".")

        file_data: dict = {
            "library_id": self.library_id,
            "relative_path": relative,
            "absolute_path": f"ftp://{self.host}{full_path}",
            "filename": filename,
            "extension": ext,
            "mime_type": "",  # Cannot reliably determine over FTP
            "size_bytes": size_bytes,
            "modified_at": modified_at_iso,
            "created_at": modified_at_iso,  # FTP provides modify only
        }

        self._db.upsert_file(file_data)
        log.debug("Indexed FTP file: %s (%d bytes)", relative, size_bytes)
        return True

    @staticmethod
    def _parse_ftp_timestamp(ts: str) -> str:
        """Convert an FTP MLSD timestamp to ISO 8601 UTC.

        MLSD timestamps are in the format ``YYYYMMDDHHMMSS`` (always UTC).
        Returns an empty string if the timestamp cannot be parsed.
        """
        if not ts or len(ts) < 14:
            return ""
        try:
            dt = datetime(
                year=int(ts[0:4]),
                month=int(ts[4:6]),
                day=int(ts[6:8]),
                hour=int(ts[8:10]),
                minute=int(ts[10:12]),
                second=int(ts[12:14]),
                tzinfo=timezone.utc,
            )
            return dt.isoformat()
        except (ValueError, IndexError):
            return ""
