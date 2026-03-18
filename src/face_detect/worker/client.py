"""Worker client — pulls tasks from coordinator and processes them."""

import json
import logging
import time
import threading
from pathlib import Path

import requests

from ..config import Config
from .processor import MediaProcessor
from ..indexer import FaceIndexer

log = logging.getLogger(__name__)


class WorkerClient:
    """Remote or local worker that pulls tasks from the coordinator API."""

    def __init__(self, config: Config, worker_name: str,
                 coordinator_url: str, index_dir: str = None):
        self.config = config
        self.worker_name = worker_name
        self.coordinator_url = coordinator_url.rstrip("/")
        self.index_dir = index_dir
        self.processor = None
        self._running = False

    def _download_index(self, dest_dir: str):
        """Download FAISS index from coordinator."""
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)

        for filename in ["index.faiss", "labels.json", "person_stats.json"]:
            url = f"{self.coordinator_url}/index?file={filename}"
            log.info("Downloading %s from coordinator...", filename)
            resp = requests.get(url, timeout=60)
            if resp.status_code == 200:
                (dest / filename).write_bytes(resp.content)
                log.info("  Downloaded %s (%d bytes)", filename, len(resp.content))
            else:
                if filename == "person_stats.json":
                    continue  # optional
                raise RuntimeError(f"Failed to download {filename}: {resp.status_code}")

    def _init_processor(self):
        """Initialize the media processor with FAISS index."""
        if self.processor is not None:
            return

        # Download or use local index
        if self.index_dir and Path(self.index_dir).exists():
            idx_dir = self.index_dir
        else:
            idx_dir = f"./worker_cache/{self.worker_name}"
            self._download_index(idx_dir)

        index, labels, stats = FaceIndexer.load(idx_dir)
        self.processor = MediaProcessor(
            self.config, index, labels, self.config.output.thumbnails_dir
        )
        self.processor.init_model()

    def _heartbeat_loop(self):
        """Send periodic heartbeats to coordinator."""
        while self._running:
            try:
                requests.post(
                    f"{self.coordinator_url}/health",
                    json={"worker": self.worker_name, "status": "active"},
                    timeout=5,
                )
            except Exception:
                pass
            time.sleep(30)

    def run(self):
        """Main worker loop — pull tasks, process, report results."""
        log.info("Worker '%s' starting, coordinator: %s", self.worker_name, self.coordinator_url)
        self._init_processor()

        self._running = True
        hb_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        hb_thread.start()

        idle_count = 0
        max_idle = 10  # Stop after 10 consecutive empty polls (50 seconds)

        while self._running:
            try:
                resp = requests.get(
                    f"{self.coordinator_url}/task",
                    params={"worker": self.worker_name},
                    timeout=30,
                )
                data = resp.json()
                task = data.get("task")

                if task is None:
                    idle_count += 1
                    if idle_count >= max_idle:
                        log.info("No more tasks available. Worker shutting down.")
                        break
                    time.sleep(5)
                    continue

                idle_count = 0
                task_id = task["id"]
                file_path = task["file_path"]
                log.info("Processing task %d: %s", task_id, file_path)

                try:
                    result = self.processor.process_file(file_path)
                    match_count = len(result.get("matches", []))
                    log.info("  Task %d done: %d matches found", task_id, match_count)

                    requests.post(
                        f"{self.coordinator_url}/result",
                        json={"task_id": task_id, "result": result},
                        timeout=30,
                    )
                except Exception as e:
                    log.error("  Task %d failed: %s", task_id, e)
                    try:
                        requests.post(
                            f"{self.coordinator_url}/result",
                            json={
                                "task_id": task_id,
                                "error": str(e),
                                "result": {"file_path": file_path},
                            },
                            timeout=10,
                        )
                    except Exception:
                        pass

            except requests.ConnectionError:
                log.warning("Cannot reach coordinator, retrying in 10s...")
                time.sleep(10)
            except Exception as e:
                log.error("Worker error: %s", e)
                time.sleep(5)

        self._running = False
        log.info("Worker '%s' stopped", self.worker_name)

    def stop(self):
        """Signal the worker to stop."""
        self._running = False
