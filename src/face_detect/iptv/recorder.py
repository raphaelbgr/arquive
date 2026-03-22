"""DVR recording for live IPTV streams.

Records live streams to disk using FFmpeg stream copy (no re-encoding).
Supports scheduled recordings from EPG and instant recording.

Dependencies: subprocess (ffmpeg), threading
"""

from __future__ import annotations

import logging
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class Recorder:
    """Manages live stream recording sessions."""

    def __init__(self, db: Any, recording_dir: str) -> None:
        self.db = db
        self.recording_dir = Path(recording_dir) if recording_dir else Path.home() / "Recordings"
        self.recording_dir.mkdir(parents=True, exist_ok=True)
        self._active: dict[int, subprocess.Popen] = {}
        self._lock = threading.Lock()

    def start_recording(self, recording_id: int) -> None:
        """Start recording a stream in the background."""
        row = self.db.conn.execute(
            "SELECT * FROM recordings WHERE id = ?", (recording_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Recording {recording_id} not found")

        output_path = Path(row["output_path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            "ffmpeg", "-y",
            "-i", row["stream_url"],
            "-c", "copy",
            str(output_path),
        ]

        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        with self._lock:
            self._active[recording_id] = proc

        with self.db._lock:
            self.db.conn.execute(
                "UPDATE recordings SET status = 'recording', actual_start = datetime('now') WHERE id = ?",
                (recording_id,),
            )
            self.db.conn.commit()

        log.info("Recording %d started: %s", recording_id, row["stream_url"])

        # Monitor in background thread
        def _monitor():
            proc.wait()
            with self._lock:
                self._active.pop(recording_id, None)
            # Update status based on exit code
            status = "completed" if proc.returncode == 0 else "failed"
            error = None
            if proc.returncode != 0:
                error = proc.stderr.read().decode(errors="replace")[-500:]
            file_size = output_path.stat().st_size if output_path.exists() else 0
            with self.db._lock:
                self.db.conn.execute(
                    "UPDATE recordings SET status = ?, actual_end = datetime('now'), "
                    "file_size = ?, error_message = ? WHERE id = ?",
                    (status, file_size, error, recording_id),
                )
                self.db.conn.commit()
            log.info("Recording %d finished: %s", recording_id, status)

        threading.Thread(target=_monitor, daemon=True).start()

    def stop_recording(self, recording_id: int) -> None:
        """Stop an active recording gracefully."""
        with self._lock:
            proc = self._active.get(recording_id)
        if proc:
            proc.terminate()
            log.info("Recording %d stop requested", recording_id)

    def schedule_recording(
        self,
        channel_id: int,
        stream_url: str,
        title: str,
        start: str,
        end: str,
        fmt: str = "original",
    ) -> int:
        """Schedule a future recording.  Returns recording ID."""
        filename = f"{title.replace(' ', '_')}_{start[:10]}.ts"
        output_path = str(self.recording_dir / filename)
        with self.db._lock:
            cur = self.db.conn.execute(
                "INSERT INTO recordings "
                "(channel_id, program_title, stream_url, output_path, "
                "scheduled_start, scheduled_end, format) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (channel_id, title, stream_url, output_path, start, end, fmt),
            )
            self.db.conn.commit()
            return cur.lastrowid

    def get_active(self) -> list[int]:
        """Return IDs of currently recording sessions."""
        with self._lock:
            return list(self._active.keys())
