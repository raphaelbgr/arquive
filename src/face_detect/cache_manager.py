"""LRU cache manager for transcoded video segments, thumbnails, and sprites.

Architecture
------------
Two-tier storage:
  - **Main DB** (faces.db via Database): permanent metadata, settings
  - **Cache DB** (cache.db inside cache directory): segment tracking,
    access timestamps, lock state.  Disposable — rebuilt if lost.

Eviction: LRU by ``last_accessed`` timestamp.  ``preload/`` segments
are never evicted unless manually cleared.

Lock registry: Observable pattern for coordinating file handle release
when the cache location changes or files need deletion.

Dependencies: sqlite3, threading, pathlib, shutil, tempfile
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)

CACHE_DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS segments (
    id INTEGER PRIMARY KEY,
    file_hash TEXT NOT NULL,
    quality TEXT NOT NULL,
    segment_index INTEGER NOT NULL,
    is_preload BOOLEAN DEFAULT 0,
    path TEXT NOT NULL,
    size_bytes INTEGER,
    last_accessed TEXT DEFAULT (datetime('now')),
    locked_by TEXT,
    UNIQUE(file_hash, quality, segment_index)
);

CREATE TABLE IF NOT EXISTS thumbnails (
    id INTEGER PRIMARY KEY,
    file_hash TEXT UNIQUE NOT NULL,
    path TEXT NOT NULL,
    size_bytes INTEGER,
    generated_at TEXT DEFAULT (datetime('now'))
);
"""


class LockRegistry:
    """Observable that notifies subscribers when files need releasing.

    Subscribers register with ``subscribe(callback)`` where *callback*
    receives the path being released.  When the cache manager needs
    to move/delete a file, it calls ``request_release(path)`` which
    invokes all subscribers synchronously.
    """

    def __init__(self) -> None:
        self._subscribers: list[Callable[[str], None]] = []
        self._lock = threading.Lock()

    def subscribe(self, callback: Callable[[str], None]) -> None:
        with self._lock:
            self._subscribers.append(callback)

    def request_release(self, path: str) -> None:
        with self._lock:
            for cb in self._subscribers:
                try:
                    cb(path)
                except Exception:
                    log.exception("Lock release callback failed for %s", path)


class CacheManager:
    """Manages the transcode/thumbnail cache with LRU eviction."""

    def __init__(self, cache_dir: str = "", limit_bytes: int = 20 * 1024**3) -> None:
        if not cache_dir:
            cache_dir = str(Path(tempfile.gettempdir()) / "arquive_cache")
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.limit_bytes = limit_bytes
        self.enabled = True
        self.lock_registry = LockRegistry()

        self._db_path = self.cache_dir / "cache.db"
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.executescript(CACHE_DB_SCHEMA)
        self._conn.commit()
        self._lock = threading.Lock()

    # --- Directories ---

    @property
    def segments_dir(self) -> Path:
        d = self.cache_dir / "segments"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def thumbnails_dir(self) -> Path:
        d = self.cache_dir / "thumbnails"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def sprites_dir(self) -> Path:
        d = self.cache_dir / "sprites"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def preload_dir(self) -> Path:
        d = self.cache_dir / "preload"
        d.mkdir(parents=True, exist_ok=True)
        return d

    # --- Segment tracking ---

    def register_segment(
        self,
        file_hash: str,
        quality: str,
        segment_index: int,
        path: str,
        size_bytes: int,
        is_preload: bool = False,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO segments
                   (file_hash, quality, segment_index, is_preload, path, size_bytes)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (file_hash, quality, segment_index, is_preload, path, size_bytes),
            )
            self._conn.commit()

    def touch_segment(self, file_hash: str, quality: str, segment_index: int) -> None:
        """Update last_accessed to prevent LRU eviction."""
        with self._lock:
            self._conn.execute(
                "UPDATE segments SET last_accessed = datetime('now') "
                "WHERE file_hash = ? AND quality = ? AND segment_index = ?",
                (file_hash, quality, segment_index),
            )
            self._conn.commit()

    def get_segment_path(self, file_hash: str, quality: str, segment_index: int) -> str | None:
        row = self._conn.execute(
            "SELECT path FROM segments WHERE file_hash = ? AND quality = ? AND segment_index = ?",
            (file_hash, quality, segment_index),
        ).fetchone()
        if row and Path(row["path"]).exists():
            self.touch_segment(file_hash, quality, segment_index)
            return row["path"]
        return None

    # --- Size tracking ---

    def current_size_bytes(self) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(size_bytes), 0) AS total FROM segments"
        ).fetchone()
        return row["total"]

    def stats(self) -> dict[str, Any]:
        total = self.current_size_bytes()
        segment_count = self._conn.execute("SELECT COUNT(*) AS cnt FROM segments").fetchone()["cnt"]
        return {
            "cache_dir": str(self.cache_dir),
            "enabled": self.enabled,
            "limit_bytes": self.limit_bytes,
            "used_bytes": total,
            "used_pct": round(total / self.limit_bytes * 100, 1) if self.limit_bytes else 0,
            "segment_count": segment_count,
        }

    # --- Eviction ---

    def evict_if_needed(self) -> int:
        """Evict LRU segments until cache is under limit.  Returns bytes freed."""
        freed = 0
        while self.current_size_bytes() > self.limit_bytes:
            # Never evict preload segments automatically
            row = self._conn.execute(
                "SELECT id, path, size_bytes FROM segments "
                "WHERE is_preload = 0 AND locked_by IS NULL "
                "ORDER BY last_accessed ASC LIMIT 1"
            ).fetchone()
            if not row:
                break
            path = Path(row["path"])
            self.lock_registry.request_release(str(path))
            if path.exists():
                path.unlink()
            with self._lock:
                self._conn.execute("DELETE FROM segments WHERE id = ?", (row["id"],))
                self._conn.commit()
            freed += row["size_bytes"] or 0
        if freed:
            log.info("Cache eviction freed %d bytes", freed)
        return freed

    # --- Clear ---

    def clear(self) -> int:
        """Remove all cached data.  Returns bytes freed."""
        size = self.current_size_bytes()
        for subdir in ("segments", "thumbnails", "sprites", "preload"):
            d = self.cache_dir / subdir
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)
                d.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._conn.execute("DELETE FROM segments")
            self._conn.execute("DELETE FROM thumbnails")
            self._conn.commit()
        log.info("Cache cleared: %d bytes freed", size)
        return size

    # --- Location change ---

    def move_to(self, new_dir: str) -> None:
        """Move all cache data to a new directory."""
        new_path = Path(new_dir)
        if new_path == self.cache_dir:
            return
        new_path.mkdir(parents=True, exist_ok=True)
        # Release all locks before moving
        self.lock_registry.request_release(str(self.cache_dir))
        # Copy contents
        for item in self.cache_dir.iterdir():
            dest = new_path / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)
        old_dir = self.cache_dir
        self.cache_dir = new_path
        self._db_path = new_path / "cache.db"
        self._conn.close()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        log.info("Cache moved from %s to %s", old_dir, new_path)

    def close(self) -> None:
        self._conn.close()
