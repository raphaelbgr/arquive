"""SSH tunnel media source for indexing files on remote hosts.

Architecture
------------
``SSHSource`` connects to a remote machine over SSH and lists files using
the ``find`` command.  File metadata is extracted from ``stat`` output
transmitted over the same SSH session.

The implementation shells out to the system ``ssh`` binary, relying on the
user's ``~/.ssh/config`` for host aliases, key files, and connection
parameters.  This avoids pulling in paramiko as a dependency while still
providing robust connectivity through OpenSSH's battle-tested client.

Future enhancements
-------------------
- Stream file thumbnails / small files back via ``scp`` or ``sftp``.
- Optional paramiko backend for environments without a system SSH client.
- Persistent connection multiplexing via ``ControlMaster``.

Dependencies
------------
- Standard library: subprocess, logging, os, shlex
- System: ``ssh`` binary (OpenSSH client)
"""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from face_detect.database import Database

log = logging.getLogger(__name__)


class SSHSource:
    """Index media files on a remote host via SSH.

    Parameters
    ----------
    library_id:
        The library row ID that owns these files.
    path:
        Absolute path on the remote host to scan.
    db:
        Database instance for persisting indexed files.
    ssh_alias:
        SSH config alias **or** ``user@host`` string.  When empty, the
        host is inferred from *credentials* (``host`` key).
    credentials:
        Optional dict that may contain ``host``, ``port``, ``username``,
        and ``key_file`` keys.  Values provided here override what is in
        ``~/.ssh/config``.
    """

    def __init__(
        self,
        library_id: int,
        path: str,
        db: Database,
        ssh_alias: str = "",
        credentials: dict | None = None,
    ) -> None:
        self.library_id = library_id
        self.remote_path = path
        self._db = db
        self._ssh_alias = ssh_alias
        self._credentials = credentials or {}
        self._ssh_target = self._resolve_target()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(self) -> int:
        """List remote files via SSH and index them in the database.

        Returns
        -------
        int
            Number of files indexed.
        """
        log.info(
            "Starting SSH scan: library_id=%d target=%s path=%s",
            self.library_id,
            self._ssh_target,
            self.remote_path,
        )

        files = self.list_files()
        count = 0

        for entry in files:
            try:
                indexed = self._index_entry(entry)
                if indexed:
                    count += 1
            except Exception:
                log.exception("Failed to index remote entry: %s", entry)

        log.info(
            "SSH scan complete: library_id=%d indexed=%d target=%s",
            self.library_id,
            count,
            self._ssh_target,
        )
        return count

    def list_files(self) -> list[dict]:
        """Run ``find`` + ``stat`` over SSH to enumerate remote files.

        Returns a list of dicts with keys: ``relative_path``, ``size_bytes``,
        ``modified_epoch``.
        """
        # GNU stat format: %s = size, %Y = mtime epoch, %n = filename
        # The find command outputs one file per line with stat metadata.
        remote_cmd = (
            f"find {shlex.quote(self.remote_path)} -type f "
            f"-exec stat --format='%s|%Y|%n' {{}} +"
        )

        ssh_cmd = self._build_ssh_command(remote_cmd)
        log.debug("SSH command: %s", " ".join(ssh_cmd))

        try:
            result = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except FileNotFoundError:
            log.error("ssh binary not found -- is OpenSSH installed?")
            return []
        except subprocess.TimeoutExpired:
            log.error("SSH file listing timed out for %s", self._ssh_target)
            return []

        if result.returncode != 0:
            log.error(
                "SSH command failed (rc=%d): %s",
                result.returncode,
                result.stderr.strip(),
            )
            return []

        entries: list[dict] = []
        for line in result.stdout.strip().splitlines():
            parts = line.split("|", maxsplit=2)
            if len(parts) != 3:
                continue
            try:
                size_bytes = int(parts[0])
                modified_epoch = int(parts[1])
                absolute_path = parts[2]
            except (ValueError, IndexError):
                log.debug("Skipping unparseable stat line: %s", line)
                continue

            # Compute path relative to the scan root.
            if absolute_path.startswith(self.remote_path):
                relative = absolute_path[len(self.remote_path):].lstrip("/")
            else:
                relative = absolute_path

            entries.append({
                "relative_path": relative,
                "absolute_path": absolute_path,
                "size_bytes": size_bytes,
                "modified_epoch": modified_epoch,
            })

        log.info("Listed %d files on %s:%s", len(entries), self._ssh_target, self.remote_path)
        return entries

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_target(self) -> str:
        """Determine the SSH target (alias or user@host) from config."""
        if self._ssh_alias:
            return self._ssh_alias

        host = self._credentials.get("host", "")
        username = self._credentials.get("username", "")
        if username and host:
            return f"{username}@{host}"
        if host:
            return host

        log.warning("No SSH alias or host provided -- connection will likely fail")
        return "localhost"

    def _build_ssh_command(self, remote_cmd: str) -> list[str]:
        """Build the ``ssh`` invocation list."""
        cmd: list[str] = ["ssh"]

        # Optional port override.
        port = self._credentials.get("port")
        if port:
            cmd.extend(["-p", str(port)])

        # Optional identity file.
        key_file = self._credentials.get("key_file")
        if key_file:
            cmd.extend(["-i", os.path.expanduser(key_file)])

        # Disable strict host key checking for automated scans (user can
        # override via ssh_config).
        cmd.extend([
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=10",
        ])

        cmd.append(self._ssh_target)
        cmd.append(remote_cmd)
        return cmd

    def _index_entry(self, entry: dict) -> bool:
        """Insert or update a single remote file entry.

        Returns *True* if the row was written.
        """
        relative = entry["relative_path"]
        modified_at_iso = self._epoch_to_iso(entry["modified_epoch"])

        existing = self._db.fetch_one(
            "SELECT modified_at FROM files WHERE library_id = ? AND relative_path = ?",
            (self.library_id, relative),
        )
        if existing is not None and existing[0] == modified_at_iso:
            return False

        filename = os.path.basename(relative)
        ext = os.path.splitext(filename)[1].lower().lstrip(".")

        file_data: dict = {
            "library_id": self.library_id,
            "relative_path": relative,
            "absolute_path": entry["absolute_path"],
            "filename": filename,
            "extension": ext,
            "mime_type": "",  # Cannot reliably guess remotely
            "size_bytes": entry["size_bytes"],
            "modified_at": modified_at_iso,
            "created_at": modified_at_iso,  # Remote ctime rarely available
        }

        self._db.upsert_file(file_data)
        log.debug("Indexed remote file: %s (%d bytes)", relative, entry["size_bytes"])
        return True

    @staticmethod
    def _epoch_to_iso(epoch: int) -> str:
        """Convert a Unix epoch to an ISO 8601 UTC string."""
        from datetime import datetime, timezone

        return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
