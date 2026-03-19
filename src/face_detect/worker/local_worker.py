"""Optimized local worker — bypasses HTTP, uses threading for I/O overlap."""

import logging
import queue
import threading
import time
from pathlib import Path

from ..config import Config
from ..database import Database
from ..indexer import FaceIndexer
from .processor import MediaProcessor

log = logging.getLogger(__name__)

# Sentinel to signal threads to stop
_STOP = object()


class LocalWorker:
    """High-throughput local worker that processes tasks directly from the scheduler.

    Optimizations over the HTTP-based WorkerClient:
    - No HTTP overhead (direct queue access)
    - Prefetch: I/O thread loads images ahead of GPU processing
    - Batch result writes to database
    - Configurable number of I/O prefetch threads
    """

    def __init__(self, config: Config, scheduler, db: Database,
                 index_dir: str, scan_job_id: int,
                 worker_name: str = "desktop", num_prefetch: int = 4):
        self.config = config
        self.scheduler = scheduler
        self.db = db
        self.index_dir = index_dir
        self.scan_job_id = scan_job_id
        self.worker_name = worker_name
        self.num_prefetch = num_prefetch
        self.processor = None
        self._running = False

        # Prefetch queue: I/O threads load images, GPU thread consumes
        self._prefetch_queue = queue.Queue(maxsize=num_prefetch * 2)
        # Result batch queue: GPU thread produces, DB writer consumes
        self._result_queue = queue.Queue(maxsize=100)

        # Stats
        self.files_processed = 0
        self.matches_found = 0
        self.files_failed = 0
        self._start_time = 0

    def _init_processor(self):
        index, labels, stats = FaceIndexer.load(self.index_dir)
        self.processor = MediaProcessor(
            self.config, index, labels, self.config.output.thumbnails_dir
        )
        self.processor.init_model()

    def _prefetch_loop(self):
        """I/O thread: pull tasks from scheduler and load images into memory."""
        while self._running:
            task = self.scheduler.get_next_task(self.worker_name)
            if task is None:
                # No more tasks — signal GPU thread
                self._prefetch_queue.put(_STOP)
                return

            self._prefetch_queue.put(task)

    def _process_loop(self):
        """GPU thread: process prefetched tasks."""
        stop_count = 0
        while self._running:
            try:
                item = self._prefetch_queue.get(timeout=5)
            except queue.Empty:
                continue

            if item is _STOP:
                stop_count += 1
                if stop_count >= self.num_prefetch:
                    break
                continue

            task = item
            task_id = task["id"]
            file_path = task["file_path"]

            try:
                result = self.processor.process_file(file_path)
                match_count = len(result.get("matches", []))

                self.scheduler.complete_task(task_id, result)
                self._result_queue.put(("ok", result))

                self.files_processed += 1
                self.matches_found += match_count

                if self.files_processed % 100 == 0:
                    elapsed = time.time() - self._start_time
                    rate = self.files_processed / elapsed if elapsed > 0 else 0
                    progress = self.scheduler.get_progress()
                    log.info("Progress: %d/%d (%.1f%%) | %.1f files/sec | %d matches | %d failed",
                             progress["done"], progress["total"], progress["progress_pct"],
                             rate, self.matches_found, self.files_failed)

            except Exception as e:
                log.error("Task %d failed (%s): %s", task_id, Path(file_path).name, e)
                self.scheduler.fail_task(task_id, str(e))
                self._result_queue.put(("fail", {"file_path": file_path, "error": str(e)}))
                self.files_failed += 1

        # Signal DB writer to stop
        self._result_queue.put(_STOP)

    def _db_writer_loop(self):
        """DB thread: batch-write results to SQLite (avoids lock contention)."""
        batch = []
        batch_size = 50
        last_flush = time.time()

        while True:
            try:
                item = self._result_queue.get(timeout=2)
            except queue.Empty:
                if batch:
                    self._flush_batch(batch)
                    batch = []
                    last_flush = time.time()
                continue

            if item is _STOP:
                if batch:
                    self._flush_batch(batch)
                return

            status, result = item
            batch.append((status, result))

            if len(batch) >= batch_size or (time.time() - last_flush) > 5:
                self._flush_batch(batch)
                batch = []
                last_flush = time.time()

    def _flush_batch(self, batch: list):
        """Write a batch of results to the database."""
        db_matches = []
        for status, result in batch:
            file_path = result.get("file_path", "")

            if status == "ok":
                for m in result.get("matches", []):
                    db_matches.append({
                        "scan_job_id": self.scan_job_id,
                        "person_name": m["person_name"],
                        "file_path": result["file_path"],
                        "file_type": result["file_type"],
                        "confidence": m["confidence"],
                        "timestamp_start": m.get("timestamp_start"),
                        "timestamp_end": m.get("timestamp_end"),
                        "thumbnail_path": m.get("thumbnail_path"),
                        "file_hash": result.get("file_hash"),
                    })
                self.db.mark_file_processed(
                    file_path, self.scan_job_id,
                    file_hash=result.get("file_hash"),
                    status="done"
                )
            else:
                self.db.mark_file_processed(
                    file_path, self.scan_job_id,
                    status="failed"
                )

        if db_matches:
            self.db.add_matches_batch(db_matches)

        # Update progress
        progress = self.scheduler.get_progress()
        matched_count = self.db.conn.execute(
            "SELECT COUNT(DISTINCT file_path) FROM matches WHERE scan_job_id=?",
            (self.scan_job_id,)
        ).fetchone()[0]
        self.db.update_scan_progress(
            self.scan_job_id, progress["done"], matched_count, progress["failed"]
        )

    def run(self):
        """Run the optimized local worker."""
        log.info("LocalWorker '%s' starting (prefetch=%d)", self.worker_name, self.num_prefetch)
        self._init_processor()
        self._running = True
        self._start_time = time.time()

        # Start DB writer thread
        db_thread = threading.Thread(target=self._db_writer_loop, daemon=True, name="db-writer")
        db_thread.start()

        # Start prefetch threads
        prefetch_threads = []
        for i in range(self.num_prefetch):
            t = threading.Thread(target=self._prefetch_loop, daemon=True, name=f"prefetch-{i}")
            t.start()
            prefetch_threads.append(t)

        # Run GPU processing on main thread
        try:
            self._process_loop()
        except KeyboardInterrupt:
            log.info("LocalWorker interrupted")
            self._running = False

        # Wait for DB writer to finish
        db_thread.join(timeout=30)

        elapsed = time.time() - self._start_time
        rate = self.files_processed / elapsed if elapsed > 0 else 0
        log.info("LocalWorker done: %d files in %.0fs (%.1f files/sec), %d matches, %d failed",
                 self.files_processed, elapsed, rate, self.matches_found, self.files_failed)

    def stop(self):
        self._running = False
