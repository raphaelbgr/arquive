"""Local filesystem media source — indexes only media files.

Only indexes images, videos, audio, and documents. Skips system files,
hidden files, and non-media extensions.

Dependencies: Standard library only (pathlib, mimetypes, os, logging, datetime)
"""

from __future__ import annotations

import logging
import mimetypes
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from face_detect.database import Database

log = logging.getLogger(__name__)

mimetypes.init()

# Only index these extensions
_MEDIA_EXTENSIONS: frozenset[str] = frozenset({
    # Images
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".tif",
    ".svg", ".heic", ".heif", ".avif", ".ico", ".raw", ".cr2", ".nef",
    ".arw", ".dng", ".orf", ".rw2",
    # Videos
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".wmv", ".flv",
    ".mpg", ".mpeg", ".3gp", ".ts", ".vob", ".ogv", ".mts",
    # Audio
    ".mp3", ".flac", ".wav", ".aac", ".ogg", ".wma", ".m4a", ".opus",
    ".aiff", ".alac",
    # Documents
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".txt", ".rtf", ".odt", ".ods", ".odp",
})

# Always skip these filenames
_SKIP_FILES: frozenset[str] = frozenset({
    "desktop.ini", "thumbs.db", ".ds_store", "icon\r", ".localized",
    ".nomedia", ".gitignore", ".gitkeep", "folder.jpg", "albumart.jpg",
})

_DEFAULT_EXCLUDE_DIRS: frozenset[str] = frozenset({
    ".git", ".svn", "__pycache__", "node_modules", ".Trash",
    "$RECYCLE.BIN", "System Volume Information", "@eaDir",
    ".thumbnails", ".cache", "Thumbs",
})


class LocalSource:
    """Index media files from a local directory tree."""

    def __init__(
        self,
        library_id: int,
        path: str,
        db: Database,
        exclude_dirs: set[str] | None = None,
    ) -> None:
        self.library_id = library_id
        self.root = Path(path).resolve()
        self._db = db
        self._exclude_dirs = _DEFAULT_EXCLUDE_DIRS | frozenset(exclude_dirs or ())

    def scan(self) -> int:
        """Walk the directory tree and index media files only.  Returns count."""
        if not self.root.is_dir():
            log.error("Scan path does not exist: %s", self.root)
            return 0

        log.info("Starting local scan: library_id=%d path=%s", self.library_id, self.root)
        count = 0

        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d not in self._exclude_dirs]

            for fname in filenames:
                # Skip non-media and system files early (no stat() call)
                lower_name = fname.lower()
                if lower_name in _SKIP_FILES:
                    continue
                if lower_name.startswith("."):
                    continue

                ext = os.path.splitext(lower_name)[1]
                if ext not in _MEDIA_EXTENSIONS:
                    continue

                filepath = Path(dirpath) / fname
                try:
                    if self._index_file(filepath, ext):
                        count += 1
                except Exception:
                    log.debug("Failed to index: %s", filepath)

        with self._db._lock:
            self._db.conn.execute(
                "UPDATE libraries SET file_count = ?, last_scanned = datetime('now') WHERE id = ?",
                (count, self.library_id),
            )
            self._db.conn.commit()

        log.info("Local scan complete: library_id=%d indexed=%d", self.library_id, count)
        return count

    def _index_file(self, filepath: Path, ext: str) -> bool:
        """Index a single media file.  Returns True if newly indexed/updated."""
        stat = filepath.stat()

        # Skip tiny files (likely corrupt or placeholders)
        if stat.st_size < 100:
            return False

        modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        file_path_str = str(filepath)

        # Skip if already indexed with same mtime
        existing = self._db.conn.execute(
            "SELECT modified_at FROM files WHERE path = ?", (file_path_str,)
        ).fetchone()
        if existing and existing["modified_at"] == modified_at:
            return False

        mime_type, _ = mimetypes.guess_type(file_path_str)
        created_at = datetime.fromtimestamp(
            getattr(stat, "st_birthtime", stat.st_ctime), tz=timezone.utc
        ).isoformat()

        self._db.upsert_file(
            path=file_path_str,
            name=filepath.name,
            extension=ext,
            mime_type=mime_type or "application/octet-stream",
            size=stat.st_size,
            modified_at=modified_at,
            created_at=created_at,
            indexed_at=datetime.now(timezone.utc).isoformat(),
            library_id=self.library_id,
        )
        return True
