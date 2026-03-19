"""SQLite database for storing scan results."""

import json
import sqlite3
import logging
from pathlib import Path
from datetime import datetime

log = logging.getLogger(__name__)

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


class Database:
    """SQLite database for face detection results."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def create_scan_job(self, total_files: int) -> int:
        cur = self.conn.execute(
            "INSERT INTO scan_jobs (total_files) VALUES (?)",
            (total_files,)
        )
        self.conn.commit()
        return cur.lastrowid

    def update_scan_progress(self, job_id: int, processed: int, matched: int, failed: int):
        self.conn.execute(
            "UPDATE scan_jobs SET processed_files=?, matched_files=?, failed_files=? WHERE id=?",
            (processed, matched, failed, job_id)
        )
        self.conn.commit()

    def finish_scan_job(self, job_id: int):
        self.conn.execute(
            "UPDATE scan_jobs SET finished_at=datetime('now'), status='completed' WHERE id=?",
            (job_id,)
        )
        self.conn.commit()

    def ensure_person(self, name: str, embedding_count: int = 0):
        self.conn.execute(
            "INSERT OR IGNORE INTO persons (name, embedding_count) VALUES (?, ?)",
            (name, embedding_count)
        )
        self.conn.commit()

    def add_match(self, scan_job_id: int, person_name: str, file_path: str,
                  file_type: str, confidence: float, timestamp_start: float = None,
                  timestamp_end: float = None, thumbnail_path: str = None,
                  file_hash: str = None):
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

    def get_all_matches(self) -> list:
        rows = self.conn.execute(
            """SELECT person_name, file_path, file_type, confidence,
                      timestamp_start, timestamp_end, thumbnail_path
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

    def close(self):
        self.conn.close()
