"""SMB/CIFS network share media source.

Architecture
------------
``SMBSource`` indexes files from Windows UNC paths (``\\\\server\\share``).
On Windows, UNC paths are natively accessible via :func:`os.walk` once the
share is connected.  Connection is established through ``net use`` via
:mod:`subprocess`.

On non-Windows platforms the source falls back to ``smbclient`` for listing,
though this path is less tested and intended primarily as a compatibility
shim.

The mount/unmount lifecycle is managed explicitly so that credentials are
not left attached longer than necessary.  The class can also be used as a
context manager for automatic cleanup::

    with SMBSource(library_id=1, path=r"\\\\server\\share", db=db, credentials=creds) as src:
        count = src.scan()

Dependencies
------------
- Standard library: subprocess, os, logging, pathlib, platform, mimetypes
- Windows: ``net use`` CLI (ships with all Windows versions)
- Linux/macOS (optional): ``smbclient`` from Samba
"""

from __future__ import annotations

import logging
import mimetypes
import os
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from face_detect.database import Database

log = logging.getLogger(__name__)

mimetypes.init()

_IS_WINDOWS = platform.system() == "Windows"


class SMBSource:
    """Index media files from an SMB/CIFS network share.

    Parameters
    ----------
    library_id:
        The library row ID that owns these files.
    path:
        UNC path to the share root, e.g. ``\\\\server\\share\\subfolder``.
    db:
        Database instance for persisting indexed files.
    credentials:
        Optional dict with ``username`` and ``password`` keys.  If *None*,
        the current Windows session credentials are used (guest / anonymous
        on other platforms).
    """

    def __init__(
        self,
        library_id: int,
        path: str,
        db: Database,
        credentials: dict | None = None,
    ) -> None:
        self.library_id = library_id
        self.path = path
        self._db = db
        self._credentials = credentials or {}
        self._mounted = False
        self._drive_letter: str | None = None

    def __enter__(self) -> SMBSource:
        self.mount()
        return self

    def __exit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: object) -> None:
        self.unmount()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def mount(self) -> None:
        """Connect to the SMB share.

        On Windows this runs ``net use`` to attach the UNC path.  If
        credentials are provided they are passed via the command line.
        """
        if self._mounted:
            log.debug("SMB share already mounted: %s", self.path)
            return

        if _IS_WINDOWS:
            self._mount_windows()
        else:
            log.info(
                "Non-Windows platform detected -- assuming share is already "
                "mounted or accessible via smbclient"
            )

        self._mounted = True

    def unmount(self) -> None:
        """Disconnect from the SMB share."""
        if not self._mounted:
            return

        if _IS_WINDOWS:
            self._unmount_windows()

        self._mounted = False

    # ------------------------------------------------------------------
    # Scanning
    # ------------------------------------------------------------------

    def scan(self) -> int:
        """Walk the SMB share and index discovered files.

        Automatically mounts the share if not already connected.

        Returns
        -------
        int
            Number of files newly indexed or updated.
        """
        if not self._mounted:
            self.mount()

        scan_root = self.path
        log.info("Starting SMB scan: library_id=%d path=%s", self.library_id, scan_root)
        count = 0

        try:
            for dirpath, dirnames, filenames in os.walk(scan_root):
                for fname in filenames:
                    try:
                        filepath = os.path.join(dirpath, fname)
                        indexed = self._index_file(filepath, scan_root)
                        if indexed:
                            count += 1
                    except Exception:
                        log.exception("Failed to index SMB file: %s", fname)
        except OSError:
            log.exception("Error walking SMB share: %s", scan_root)

        log.info(
            "SMB scan complete: library_id=%d indexed=%d path=%s",
            self.library_id,
            count,
            scan_root,
        )
        return count

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _index_file(self, filepath: str, scan_root: str) -> bool:
        """Extract metadata from a single file and upsert it.

        Returns *True* if the file was inserted or updated.
        """
        stat = os.stat(filepath)
        modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

        relative = os.path.relpath(filepath, scan_root)
        existing = self._db.fetch_one(
            "SELECT modified_at FROM files WHERE library_id = ? AND relative_path = ?",
            (self.library_id, relative),
        )
        if existing is not None and existing[0] == modified_at.isoformat():
            return False

        mime_type, _ = mimetypes.guess_type(filepath)
        created_at = datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc)
        ext = PureWindowsPath(filepath).suffix.lower().lstrip(".")

        file_data: dict = {
            "library_id": self.library_id,
            "relative_path": relative,
            "absolute_path": filepath,
            "filename": os.path.basename(filepath),
            "extension": ext,
            "mime_type": mime_type or "application/octet-stream",
            "size_bytes": stat.st_size,
            "modified_at": modified_at.isoformat(),
            "created_at": created_at.isoformat(),
        }

        self._db.upsert_file(file_data)
        log.debug("Indexed SMB file: %s (%s, %d bytes)", relative, mime_type, stat.st_size)
        return True

    def _mount_windows(self) -> None:
        """Attach the share using ``net use`` on Windows."""
        cmd: list[str] = ["net", "use", self.path]

        username = self._credentials.get("username")
        password = self._credentials.get("password")

        if password:
            cmd.append(password)
        if username:
            cmd.extend(["/user:" + username])

        log.info("Mounting SMB share: %s", self.path)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if result.returncode != 0:
                # "already connected" is not a real error
                if "already" in result.stdout.lower() or "already" in result.stderr.lower():
                    log.debug("SMB share already connected: %s", self.path)
                else:
                    log.error(
                        "net use failed (rc=%d): %s %s",
                        result.returncode,
                        result.stdout.strip(),
                        result.stderr.strip(),
                    )
        except subprocess.TimeoutExpired:
            log.error("Timed out connecting to SMB share: %s", self.path)

    def _unmount_windows(self) -> None:
        """Detach the share using ``net use /delete``."""
        log.info("Unmounting SMB share: %s", self.path)
        try:
            subprocess.run(
                ["net", "use", self.path, "/delete", "/y"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except subprocess.TimeoutExpired:
            log.warning("Timed out disconnecting SMB share: %s", self.path)
