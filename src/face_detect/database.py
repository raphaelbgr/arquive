"""SQLite database for storing scan results and Arquive media index.

Architecture
------------
Thread-safe SQLite layer with WAL mode and a global threading.Lock.
Schema is versioned: migrations run automatically on startup via
``run_migrations()``.  Existing face-detection tables (persons, matches,
processed_files, scan_jobs) are never modified — only new tables are added.

Migration strategy:
  - Version 0: original face-detection schema (created via CREATE IF NOT EXISTS)
  - Version 1+: Arquive extensions (files, libraries, IPTV, cache, auth, …)

Dependencies: sqlite3 (stdlib), threading, pathlib, json, logging
"""

from __future__ import annotations

import json
import sqlite3
import logging
import threading
from pathlib import Path
from datetime import datetime
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Version 0 — original face-detection tables (unchanged)
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS persons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    embedding_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scan_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT DEFAULT (datetime('now')),
    finished_at TEXT,
    total_files INTEGER DEFAULT 0,
    processed_files INTEGER DEFAULT 0,
    matched_files INTEGER DEFAULT 0,
    failed_files INTEGER DEFAULT 0,
    status TEXT DEFAULT 'running'
);

CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_job_id INTEGER,
    person_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_type TEXT NOT NULL,
    confidence REAL NOT NULL,
    timestamp_start REAL,
    timestamp_end REAL,
    thumbnail_path TEXT,
    file_hash TEXT,
    description TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (scan_job_id) REFERENCES scan_jobs(id)
);

CREATE TABLE IF NOT EXISTS processed_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT UNIQUE NOT NULL,
    file_hash TEXT,
    file_size INTEGER,
    scan_job_id INTEGER,
    status TEXT DEFAULT 'done',
    processed_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (scan_job_id) REFERENCES scan_jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_matches_person ON matches(person_name);
CREATE INDEX IF NOT EXISTS idx_matches_file ON matches(file_path);
CREATE INDEX IF NOT EXISTS idx_processed_path ON processed_files(file_path);
"""

# ---------------------------------------------------------------------------
# Migrations — each entry is (version, description, sql)
# Version numbers must be sequential starting at 1.
# Each migration runs inside a single transaction.
# ---------------------------------------------------------------------------

MIGRATIONS: list[tuple[int, str, str]] = [
    (
        1,
        "Arquive core tables: files, libraries, credentials, users, settings",
        """
        -- Media library index (separate from face-scan processed_files)
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY,
            path TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            extension TEXT,
            size INTEGER,
            mime_type TEXT,
            width INTEGER,
            height INTEGER,
            duration REAL,
            created_at TEXT,
            modified_at TEXT,
            indexed_at TEXT,
            thumbnail_path TEXT,
            sprite_path TEXT,
            ai_description TEXT,
            metadata_json TEXT,
            library_id INTEGER REFERENCES libraries(id)
        );

        CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);
        CREATE INDEX IF NOT EXISTS idx_files_library ON files(library_id);
        CREATE INDEX IF NOT EXISTS idx_files_extension ON files(extension);

        -- Media libraries / sources
        CREATE TABLE IF NOT EXISTS libraries (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            path TEXT NOT NULL,
            credential_id INTEGER REFERENCES credentials(id),
            scan_interval_hours INTEGER DEFAULT 24,
            last_scanned TEXT,
            file_count INTEGER DEFAULT 0,
            total_size INTEGER DEFAULT 0,
            enabled BOOLEAN DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );

        -- Encrypted credentials for remote sources
        CREATE TABLE IF NOT EXISTS credentials (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            encrypted_data TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        -- User accounts
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'user',
            created_at TEXT DEFAULT (datetime('now')),
            last_login TEXT
        );

        -- Application settings (key-value store, JSON values)
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT DEFAULT (datetime('now'))
        );
        """,
    ),
    (
        2,
        "Transcode queue, cache history, video preview sprites",
        """
        -- Transcode / pre-encode queue
        CREATE TABLE IF NOT EXISTS preencode_queue (
            id INTEGER PRIMARY KEY,
            file_id INTEGER REFERENCES files(id),
            status TEXT DEFAULT 'pending',
            priority INTEGER DEFAULT 0,
            node TEXT,
            started_at TEXT,
            completed_at TEXT,
            output_path TEXT,
            error_message TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_preencode_status ON preencode_queue(status);

        -- Cache location history
        CREATE TABLE IF NOT EXISTS cache_history (
            id INTEGER PRIMARY KEY,
            path TEXT NOT NULL,
            size INTEGER,
            created_at TEXT DEFAULT (datetime('now')),
            removed_at TEXT
        );

        -- Video preview sprite sheets
        CREATE TABLE IF NOT EXISTS sprites (
            id INTEGER PRIMARY KEY,
            file_id INTEGER REFERENCES files(id),
            sprite_path TEXT NOT NULL,
            frame_width INTEGER,
            frame_height INTEGER,
            columns INTEGER,
            rows INTEGER,
            interval_seconds REAL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_sprites_file ON sprites(file_id);
        """,
    ),
    (
        3,
        "IPTV: playlists, channels, custom streams, EPG programs/sources, recordings",
        """
        -- IPTV Playlists
        CREATE TABLE IF NOT EXISTS iptv_playlists (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            url TEXT,
            file_path TEXT,
            epg_url TEXT,
            auto_refresh_hours INTEGER DEFAULT 24,
            last_refreshed TEXT,
            channel_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            error_message TEXT,
            credential_id INTEGER REFERENCES credentials(id),
            created_at TEXT DEFAULT (datetime('now'))
        );

        -- IPTV Channels
        CREATE TABLE IF NOT EXISTS iptv_channels (
            id INTEGER PRIMARY KEY,
            playlist_id INTEGER REFERENCES iptv_playlists(id),
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            logo_url TEXT,
            group_title TEXT,
            tvg_id TEXT,
            tvg_name TEXT,
            tvg_language TEXT,
            is_favorite BOOLEAN DEFAULT 0,
            sort_order INTEGER,
            last_watched TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_channels_playlist ON iptv_channels(playlist_id);
        CREATE INDEX IF NOT EXISTS idx_channels_group ON iptv_channels(group_title);
        CREATE INDEX IF NOT EXISTS idx_channels_tvg_id ON iptv_channels(tvg_id);

        -- Custom URL Streams
        CREATE TABLE IF NOT EXISTS custom_streams (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            category TEXT,
            is_favorite BOOLEAN DEFAULT 0,
            added_at TEXT DEFAULT (datetime('now'))
        );

        -- EPG Programs
        CREATE TABLE IF NOT EXISTS epg_programs (
            id INTEGER PRIMARY KEY,
            channel_id TEXT NOT NULL,
            title TEXT NOT NULL,
            subtitle TEXT,
            description TEXT,
            category TEXT,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            duration_minutes INTEGER,
            season INTEGER,
            episode INTEGER,
            year INTEGER,
            rating TEXT,
            star_rating REAL,
            poster_url TEXT,
            credits_json TEXT,
            language TEXT,
            is_new BOOLEAN DEFAULT 0,
            is_live BOOLEAN DEFAULT 0,
            epg_source TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_epg_channel ON epg_programs(channel_id);
        CREATE INDEX IF NOT EXISTS idx_epg_start ON epg_programs(start_time);
        CREATE INDEX IF NOT EXISTS idx_epg_channel_time ON epg_programs(channel_id, start_time);

        -- EPG Sources
        CREATE TABLE IF NOT EXISTS epg_sources (
            id INTEGER PRIMARY KEY,
            url TEXT UNIQUE NOT NULL,
            name TEXT,
            last_fetched TEXT,
            channel_count INTEGER,
            program_count INTEGER,
            status TEXT DEFAULT 'active',
            auto_refresh_hours INTEGER DEFAULT 12,
            created_at TEXT DEFAULT (datetime('now'))
        );

        -- Recordings (DVR)
        CREATE TABLE IF NOT EXISTS recordings (
            id INTEGER PRIMARY KEY,
            channel_id INTEGER REFERENCES iptv_channels(id),
            program_title TEXT,
            stream_url TEXT NOT NULL,
            output_path TEXT NOT NULL,
            status TEXT DEFAULT 'scheduled',
            scheduled_start TEXT,
            scheduled_end TEXT,
            actual_start TEXT,
            actual_end TEXT,
            file_size INTEGER,
            format TEXT DEFAULT 'original',
            series_pattern TEXT,
            error_message TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_recordings_status ON recordings(status);
        """,
    ),
]


def _get_schema_version(conn: sqlite3.Connection) -> int:
    """Return current schema version, or -1 if schema_version table missing."""
    try:
        row = conn.execute(
            "SELECT MAX(version) FROM schema_version"
        ).fetchone()
        return row[0] if row and row[0] is not None else 0
    except sqlite3.OperationalError:
        return -1


def run_migrations(conn: sqlite3.Connection, lock: threading.Lock) -> None:
    """Apply pending schema migrations.

    Creates the schema_version tracking table if needed, then applies each
    migration whose version exceeds the current DB version.  Each migration
    runs inside the global lock to prevent concurrent schema changes.
    """
    with lock:
        # Ensure tracking table exists
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.commit()

        current = _get_schema_version(conn)
        for version, description, sql in MIGRATIONS:
            if version <= current:
                continue
            log.info("Applying migration v%d: %s", version, description)
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (version,),
            )
            conn.commit()
            log.info("Migration v%d applied successfully", version)


class Database:
    """Thread-safe SQLite database for face detection results and Arquive media index."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self._init_schema()

    def _init_schema(self) -> None:
        """Create original tables then apply any pending migrations."""
        with self._lock:
            self.conn.executescript(SCHEMA)
            self.conn.commit()
        run_migrations(self.conn, self._lock)

    def create_scan_job(self, total_files: int) -> int:
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO scan_jobs (total_files) VALUES (?)",
                (total_files,)
            )
            self.conn.commit()
            return cur.lastrowid

    def update_scan_progress(self, job_id: int, processed: int, matched: int, failed: int):
        with self._lock:
            self.conn.execute(
                "UPDATE scan_jobs SET processed_files=?, matched_files=?, failed_files=? WHERE id=?",
                (processed, matched, failed, job_id)
            )
            self.conn.commit()

    def finish_scan_job(self, job_id: int):
        with self._lock:
            self.conn.execute(
                "UPDATE scan_jobs SET finished_at=datetime('now'), status='completed' WHERE id=?",
                (job_id,)
            )
            self.conn.commit()

    def ensure_person(self, name: str, embedding_count: int = 0):
        with self._lock:
            self.conn.execute(
                "INSERT OR IGNORE INTO persons (name, embedding_count) VALUES (?, ?)",
                (name, embedding_count)
            )
            self.conn.commit()

    def add_match(self, scan_job_id: int, person_name: str, file_path: str,
                  file_type: str, confidence: float, timestamp_start: float = None,
                  timestamp_end: float = None, thumbnail_path: str = None,
                  file_hash: str = None):
        with self._lock:
            self.conn.execute(
                """INSERT INTO matches
                   (scan_job_id, person_name, file_path, file_type, confidence,
                    timestamp_start, timestamp_end, thumbnail_path, file_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (scan_job_id, person_name, file_path, file_type, confidence,
                 timestamp_start, timestamp_end, thumbnail_path, file_hash)
            )
            self.conn.commit()

    def add_matches_batch(self, matches: list):
        """Insert multiple matches at once."""
        with self._lock:
            self.conn.executemany(
                """INSERT INTO matches
                   (scan_job_id, person_name, file_path, file_type, confidence,
                    timestamp_start, timestamp_end, thumbnail_path, file_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [(m["scan_job_id"], m["person_name"], m["file_path"], m["file_type"],
                  m["confidence"], m.get("timestamp_start"), m.get("timestamp_end"),
                  m.get("thumbnail_path"), m.get("file_hash"))
                 for m in matches]
            )
            self.conn.commit()

    def mark_file_processed(self, file_path: str, scan_job_id: int,
                            file_hash: str = None, file_size: int = None,
                            status: str = "done"):
        with self._lock:
            self.conn.execute(
                """INSERT OR REPLACE INTO processed_files
                   (file_path, file_hash, file_size, scan_job_id, status)
                   VALUES (?, ?, ?, ?, ?)""",
                (file_path, file_hash, file_size, scan_job_id, status)
            )
            self.conn.commit()

    def is_file_processed(self, file_path: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM processed_files WHERE file_path=? AND status='done'",
            (file_path,)
        ).fetchone()
        return row is not None

    def update_description(self, file_path: str, person_name: str, description: str):
        """Update the description for a match."""
        with self._lock:
            self.conn.execute(
                "UPDATE matches SET description=? WHERE file_path=? AND person_name=?",
                (description, file_path, person_name)
            )
            self.conn.commit()

    def get_all_matches(self) -> list:
        rows = self.conn.execute(
            """SELECT person_name, file_path, file_type, confidence,
                      timestamp_start, timestamp_end, thumbnail_path, description
               FROM matches ORDER BY person_name, file_path, timestamp_start"""
        ).fetchall()
        return [dict(r) for r in rows]

    def get_matches_by_person(self) -> dict:
        """Get matches grouped by person name."""
        all_matches = self.get_all_matches()
        by_person = {}
        for m in all_matches:
            name = m["person_name"]
            if name not in by_person:
                by_person[name] = []
            by_person[name].append(m)
        return by_person

    def get_scan_stats(self, job_id: int = None) -> dict:
        """Get aggregate stats across ALL scan jobs."""
        row = self.conn.execute("""
            SELECT
                COALESCE(SUM(processed_files), 0) as processed_files,
                COALESCE(SUM(failed_files), 0) as failed_files,
                (SELECT COUNT(DISTINCT file_path) FROM matches) as matched_files,
                (SELECT COUNT(*) FROM matches) as total_matches
            FROM scan_jobs
        """).fetchone()
        return dict(row) if row else {}

    def get_persons(self) -> list:
        rows = self.conn.execute("SELECT * FROM persons ORDER BY name").fetchall()
        return [dict(r) for r in rows]

    def export_json(self) -> dict:
        """Export full results as JSON-serializable dict."""
        return {
            "persons": self.get_persons(),
            "matches": self.get_matches_by_person(),
            "stats": self.get_scan_stats(),
            "exported_at": datetime.now().isoformat(),
        }

    # ------------------------------------------------------------------
    # Settings helpers
    # ------------------------------------------------------------------

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        """Return a setting value, or *default* if the key doesn't exist."""
        row = self.conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) "
                "VALUES (?, ?, datetime('now'))",
                (key, value),
            )
            self.conn.commit()

    def get_all_settings(self) -> dict[str, str]:
        rows = self.conn.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}

    # ------------------------------------------------------------------
    # Library / media-source helpers
    # ------------------------------------------------------------------

    def add_library(
        self,
        name: str,
        source_type: str,
        path: str,
        credential_id: int | None = None,
        scan_interval_hours: int = 24,
    ) -> int:
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO libraries (name, type, path, credential_id, scan_interval_hours) "
                "VALUES (?, ?, ?, ?, ?)",
                (name, source_type, path, credential_id, scan_interval_hours),
            )
            self.conn.commit()
            return cur.lastrowid

    def get_libraries(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM libraries ORDER BY name"
        ).fetchall()
        return [dict(r) for r in rows]

    def remove_library(self, library_id: int) -> None:
        with self._lock:
            self.conn.execute("DELETE FROM libraries WHERE id = ?", (library_id,))
            self.conn.commit()

    # ------------------------------------------------------------------
    # Files (media index) helpers
    # ------------------------------------------------------------------

    def upsert_file(self, **kwargs: Any) -> int:
        """Insert or update a file record.  Returns the row id."""
        path = kwargs["path"]
        with self._lock:
            existing = self.conn.execute(
                "SELECT id FROM files WHERE path = ?", (path,)
            ).fetchone()
            if existing:
                sets = ", ".join(f"{k} = ?" for k in kwargs if k != "path")
                vals = [v for k, v in kwargs.items() if k != "path"]
                vals.append(path)
                self.conn.execute(
                    f"UPDATE files SET {sets} WHERE path = ?", vals
                )
                self.conn.commit()
                return existing["id"]
            cols = ", ".join(kwargs.keys())
            placeholders = ", ".join("?" for _ in kwargs)
            cur = self.conn.execute(
                f"INSERT INTO files ({cols}) VALUES ({placeholders})",
                list(kwargs.values()),
            )
            self.conn.commit()
            return cur.lastrowid

    def get_files(
        self,
        library_id: int | None = None,
        extension: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM files WHERE 1=1"
        params: list[Any] = []
        if library_id is not None:
            query += " AND library_id = ?"
            params.append(library_id)
        if extension is not None:
            query += " AND extension = ?"
            params.append(extension)
        query += " ORDER BY modified_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_file_by_id(self, file_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM files WHERE id = ?", (file_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_file_count(self, library_id: int | None = None) -> int:
        if library_id is not None:
            row = self.conn.execute(
                "SELECT COUNT(*) as cnt FROM files WHERE library_id = ?",
                (library_id,),
            ).fetchone()
        else:
            row = self.conn.execute("SELECT COUNT(*) as cnt FROM files").fetchone()
        return row["cnt"] if row else 0

    # ------------------------------------------------------------------
    # User helpers
    # ------------------------------------------------------------------

    def add_user(self, username: str, password_hash: str, role: str = "user") -> int:
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, password_hash, role),
            )
            self.conn.commit()
            return cur.lastrowid

    def get_user(self, username: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        return dict(row) if row else None

    def get_users(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT id, username, role, created_at, last_login FROM users ORDER BY username"
        ).fetchall()
        return [dict(r) for r in rows]

    def remove_user(self, username: str) -> bool:
        with self._lock:
            cur = self.conn.execute("DELETE FROM users WHERE username = ?", (username,))
            self.conn.commit()
            return cur.rowcount > 0

    def update_user_login(self, username: str) -> None:
        with self._lock:
            self.conn.execute(
                "UPDATE users SET last_login = datetime('now') WHERE username = ?",
                (username,),
            )
            self.conn.commit()

    def deduplicate_files(self) -> int:
        """Remove duplicate file entries (same path with different slash styles)."""
        with self._lock:
            dupes = self.conn.execute("""
                DELETE FROM files WHERE id NOT IN (
                    SELECT MIN(id) FROM files GROUP BY REPLACE(path, '\\', '/')
                )
            """)
            self.conn.commit()
            return dupes.rowcount

    def close(self):
        self.conn.close()
