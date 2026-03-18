"""Task Scheduler — walks media directories and manages task queue."""

import logging
import threading
import time
from pathlib import Path, PureWindowsPath, PurePosixPath

from ..config import Config, IMAGE_EXTENSIONS, VIDEO_EXTENSIONS

log = logging.getLogger(__name__)


class Task:
    """A single file processing task."""

    __slots__ = ("id", "file_path", "file_type", "locality", "status",
                 "assigned_to", "assigned_at", "result")

    def __init__(self, task_id: int, file_path: str, file_type: str, locality: str = ""):
        self.id = task_id
        self.file_path = file_path
        self.file_type = file_type
        self.locality = locality  # preferred worker name
        self.status = "pending"  # pending, assigned, done, failed
        self.assigned_to = ""
        self.assigned_at = 0.0
        self.result = None

    def to_dict(self):
        return {
            "id": self.id,
            "file_path": self.file_path,
            "file_type": self.file_type,
            "locality": self.locality,
            "status": self.status,
        }


class TaskScheduler:
    """Manages the task queue for distributed processing."""

    def __init__(self, config: Config):
        self.config = config
        self.tasks = {}  # id -> Task
        self.lock = threading.Lock()
        self._next_id = 1
        self._locality_map = self._build_locality_map()

    def _build_locality_map(self) -> dict:
        """Build mapping from path prefixes to worker names."""
        mapping = {}
        for worker in self.config.workers:
            for prefix in worker.locality_paths:
                mapping[prefix.lower().replace("\\", "/")] = worker.name
        return mapping

    def _resolve_locality(self, file_path: str) -> str:
        """Determine which worker is local to this file path."""
        normalized = file_path.lower().replace("\\", "/")
        for prefix, worker_name in self._locality_map.items():
            if normalized.startswith(prefix):
                return worker_name
        return ""  # no locality preference

    def scan_media_dirs(self) -> int:
        """Walk all media directories and create tasks.

        Returns number of tasks created.
        """
        count = 0
        for media_dir in self.config.media_dirs:
            media_path = Path(media_dir)
            if not media_path.exists():
                log.warning("Media directory does not exist: %s", media_dir)
                continue

            log.info("Scanning: %s", media_dir)
            for item in media_path.rglob("*"):
                if not item.is_file():
                    continue
                suffix = item.suffix.lower()
                if suffix in IMAGE_EXTENSIONS:
                    file_type = "image"
                elif suffix in VIDEO_EXTENSIONS:
                    file_type = "video"
                else:
                    continue

                file_str = str(item)
                locality = self._resolve_locality(file_str)

                with self.lock:
                    task = Task(self._next_id, file_str, file_type, locality)
                    self.tasks[self._next_id] = task
                    self._next_id += 1
                    count += 1

            log.info("  Found %d media files so far", count)

        log.info("Total tasks created: %d", count)
        return count

    def add_files(self, file_paths: list) -> int:
        """Add specific files as tasks (for testing or manual use)."""
        count = 0
        for fp in file_paths:
            path = Path(fp)
            if not path.exists():
                continue
            suffix = path.suffix.lower()
            if suffix in IMAGE_EXTENSIONS:
                file_type = "image"
            elif suffix in VIDEO_EXTENSIONS:
                file_type = "video"
            else:
                continue

            locality = self._resolve_locality(str(path))
            with self.lock:
                task = Task(self._next_id, str(path), file_type, locality)
                self.tasks[self._next_id] = task
                self._next_id += 1
                count += 1

        return count

    def get_next_task(self, worker_name: str = "") -> dict | None:
        """Get the next available task, preferring locality matches.

        Returns task dict or None if no tasks available.
        """
        with self.lock:
            # First pass: find locality match
            if worker_name:
                for task in self.tasks.values():
                    if task.status == "pending" and task.locality == worker_name:
                        task.status = "assigned"
                        task.assigned_to = worker_name
                        task.assigned_at = time.time()
                        return task.to_dict()

            # Second pass: any pending task without locality or unclaimed
            for task in self.tasks.values():
                if task.status == "pending":
                    task.status = "assigned"
                    task.assigned_to = worker_name or "unknown"
                    task.assigned_at = time.time()
                    return task.to_dict()

        return None  # No tasks available

    def complete_task(self, task_id: int, result: dict):
        """Mark a task as completed with its result."""
        with self.lock:
            if task_id in self.tasks:
                self.tasks[task_id].status = "done"
                self.tasks[task_id].result = result

    def fail_task(self, task_id: int, error: str = ""):
        """Mark a task as failed."""
        with self.lock:
            if task_id in self.tasks:
                self.tasks[task_id].status = "failed"
                self.tasks[task_id].result = {"error": error}

    def requeue_stale_tasks(self):
        """Re-queue tasks that have been assigned for too long (worker died)."""
        timeout = self.config.coordinator.task_timeout_seconds
        now = time.time()
        requeued = 0
        with self.lock:
            for task in self.tasks.values():
                if (task.status == "assigned" and
                        now - task.assigned_at > timeout):
                    task.status = "pending"
                    task.assigned_to = ""
                    task.assigned_at = 0
                    requeued += 1
        if requeued:
            log.info("Re-queued %d stale tasks", requeued)
        return requeued

    def get_progress(self) -> dict:
        """Get current progress statistics."""
        with self.lock:
            total = len(self.tasks)
            pending = sum(1 for t in self.tasks.values() if t.status == "pending")
            assigned = sum(1 for t in self.tasks.values() if t.status == "assigned")
            done = sum(1 for t in self.tasks.values() if t.status == "done")
            failed = sum(1 for t in self.tasks.values() if t.status == "failed")

        return {
            "total": total,
            "pending": pending,
            "assigned": assigned,
            "done": done,
            "failed": failed,
            "progress_pct": round(done / total * 100, 1) if total > 0 else 0,
        }
