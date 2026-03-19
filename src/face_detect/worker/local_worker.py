"""Multi-GPU local worker — runs parallel GPU threads with shared task queue."""

import logging
import queue
import threading
import time
from pathlib import Path

import faiss
import numpy as np
from insightface.app import FaceAnalysis

from ..config import Config
from ..database import Database
from ..indexer import FaceIndexer
from .processor import MediaProcessor
from ..gpu import init_gpu

log = logging.getLogger(__name__)

_STOP = object()


def _detect_gpu_count() -> int:
    """Detect how many real CUDA GPUs are available via nvidia-smi."""
    import subprocess
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
            count = len(lines)
            log.info("Detected %d CUDA GPU(s) via nvidia-smi", count)
            return max(count, 1)
    except Exception as e:
        log.warning("nvidia-smi failed: %s", e)
    return 1


class GPUWorkerThread:
    """A single GPU processing thread with its own InsightFace instance."""

    def __init__(self, gpu_id: int, config: Config, faiss_index, labels: list,
                 task_queue: queue.Queue, result_queue: queue.Queue,
                 thumbnails_dir: str):
        self.gpu_id = gpu_id
        self.config = config
        self.faiss_index = faiss_index
        self.labels = labels
        self.task_queue = task_queue
        self.result_queue = result_queue
        self.thumbnails_dir = thumbnails_dir
        self.thread = None
        self._running = False
        self.files_processed = 0
        self.matches_found = 0
        self.files_failed = 0

    def _create_processor(self) -> MediaProcessor:
        """Create a MediaProcessor bound to this GPU."""
        processor = MediaProcessor(
            self.config, self.faiss_index, self.labels, self.thumbnails_dir
        )
        # Override init_model to use specific GPU
        init_gpu()
        providers = [
            ("CUDAExecutionProvider", {"device_id": str(self.gpu_id)}),
            "CPUExecutionProvider",
        ]
        log.info("GPU-%d: Initializing InsightFace (providers: %s)", self.gpu_id, providers)
        processor.app = FaceAnalysis(
            name=self.config.recognition.model,
            providers=providers,
            allowed_modules=["detection", "recognition"],
        )
        det_w, det_h = self.config.recognition.det_size
        processor.app.prepare(ctx_id=self.gpu_id, det_size=(det_w, det_h))
        log.info("GPU-%d: Model ready", self.gpu_id)
        return processor

    def _run(self):
        """Processing loop for this GPU thread."""
        processor = self._create_processor()

        while self._running:
            try:
                item = self.task_queue.get(timeout=3)
            except queue.Empty:
                continue

            if item is _STOP:
                self.task_queue.put(_STOP)  # Re-broadcast for other GPU threads
                break

            task_id = item["id"]
            file_path = item["file_path"]

            try:
                result = processor.process_file(file_path)
                match_count = len(result.get("matches", []))
                self.result_queue.put(("ok", task_id, result))
                self.files_processed += 1
                self.matches_found += match_count
            except Exception as e:
                log.error("GPU-%d task %d failed (%s): %s",
                          self.gpu_id, task_id, Path(file_path).name, e)
                self.result_queue.put(("fail", task_id, {"file_path": file_path, "error": str(e)}))
                self.files_failed += 1

    def start(self):
        self._running = True
        self.thread = threading.Thread(
            target=self._run, daemon=True, name=f"gpu-{self.gpu_id}"
        )
        self.thread.start()

    def stop(self):
        self._running = False


class LocalWorker:
    """Multi-GPU local worker with shared task queue and batched DB writes.

    Architecture:
        Prefetch threads -> [task_queue] -> GPU threads (one per GPU) -> [result_queue] -> DB writer
    """

    def __init__(self, config: Config, scheduler, db: Database,
                 index_dir: str, scan_job_id: int,
                 worker_name: str = "desktop", num_prefetch: int = 4,
                 gpu_ids: list = None):
        self.config = config
        self.scheduler = scheduler
        self.db = db
        self.index_dir = index_dir
        self.scan_job_id = scan_job_id
        self.worker_name = worker_name
        self.num_prefetch = num_prefetch
        self._running = False
        self._start_time = 0

        # Auto-detect GPUs if not specified
        if gpu_ids is None:
            num_gpus = _detect_gpu_count()
            self.gpu_ids = list(range(num_gpus))
        else:
            self.gpu_ids = gpu_ids

        # Shared queues
        self._task_queue = queue.Queue(maxsize=num_prefetch * 2 * len(self.gpu_ids))
        self._result_queue = queue.Queue(maxsize=200)

        self.gpu_workers = []

    def _prefetch_loop(self):
        """Pull tasks from scheduler into the shared task queue."""
        while self._running:
            task = self.scheduler.get_next_task(self.worker_name)
            if task is None:
                self._task_queue.put(_STOP)
                return
            self._task_queue.put(task)

    def _db_writer_loop(self, num_gpu_threads: int):
        """Batch-write results to SQLite."""
        batch = []
        batch_size = 50
        last_flush = time.time()
        stop_count = 0

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
                stop_count += 1
                if stop_count >= num_gpu_threads:
                    if batch:
                        self._flush_batch(batch)
                    return
                continue

            status, task_id, result = item

            if status == "ok":
                self.scheduler.complete_task(task_id, result)
            else:
                self.scheduler.fail_task(task_id, result.get("error", ""))

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
                    file_hash=result.get("file_hash"), status="done"
                )
            else:
                self.db.mark_file_processed(
                    file_path, self.scan_job_id, status="failed"
                )

        if db_matches:
            self.db.add_matches_batch(db_matches)

        progress = self.scheduler.get_progress()
        matched_count = self.db.conn.execute(
            "SELECT COUNT(DISTINCT file_path) FROM matches WHERE scan_job_id=?",
            (self.scan_job_id,)
        ).fetchone()[0]
        self.db.update_scan_progress(
            self.scan_job_id, progress["done"], matched_count, progress["failed"]
        )

    def _progress_loop(self):
        """Log progress periodically."""
        while self._running:
            time.sleep(15)
            progress = self.scheduler.get_progress()
            elapsed = time.time() - self._start_time
            total_done = sum(gw.files_processed for gw in self.gpu_workers)
            total_matches = sum(gw.matches_found for gw in self.gpu_workers)
            total_failed = sum(gw.files_failed for gw in self.gpu_workers)
            rate = total_done / elapsed if elapsed > 0 else 0

            gpu_rates = []
            for gw in self.gpu_workers:
                gr = gw.files_processed / elapsed if elapsed > 0 else 0
                gpu_rates.append(f"GPU-{gw.gpu_id}:{gw.files_processed}({gr:.1f}/s)")

            log.info("Progress: %d/%d (%.1f%%) | %.1f files/sec [%s] | %d matches | %d failed",
                     progress["done"], progress["total"], progress["progress_pct"],
                     rate, " ".join(gpu_rates), total_matches, total_failed)

    def run(self):
        """Run the multi-GPU local worker."""
        log.info("LocalWorker '%s' starting with %d GPU(s): %s",
                 self.worker_name, len(self.gpu_ids), self.gpu_ids)

        # Load shared FAISS index
        index, labels, stats = FaceIndexer.load(self.index_dir)

        self._running = True
        self._start_time = time.time()

        # Start GPU worker threads
        for gpu_id in self.gpu_ids:
            gw = GPUWorkerThread(
                gpu_id, self.config, index, labels,
                self._task_queue, self._result_queue,
                self.config.output.thumbnails_dir,
            )
            gw.start()
            self.gpu_workers.append(gw)
            time.sleep(2)  # Stagger GPU init to avoid VRAM spikes

        # Start DB writer
        db_thread = threading.Thread(
            target=self._db_writer_loop, args=(len(self.gpu_ids),),
            daemon=True, name="db-writer"
        )
        db_thread.start()

        # Start prefetch threads
        for i in range(self.num_prefetch):
            t = threading.Thread(target=self._prefetch_loop, daemon=True, name=f"prefetch-{i}")
            t.start()

        # Start progress reporter
        progress_thread = threading.Thread(target=self._progress_loop, daemon=True, name="progress")
        progress_thread.start()

        # Wait for all GPU threads to finish
        try:
            for gw in self.gpu_workers:
                gw.thread.join()
        except KeyboardInterrupt:
            log.info("Interrupted — stopping GPU workers")
            self.stop()

        self._running = False

        # Wait for DB writer
        self._result_queue.put(_STOP)  # Extra stop for safety
        db_thread.join(timeout=30)

        elapsed = time.time() - self._start_time
        total_done = sum(gw.files_processed for gw in self.gpu_workers)
        total_matches = sum(gw.matches_found for gw in self.gpu_workers)
        rate = total_done / elapsed if elapsed > 0 else 0
        log.info("LocalWorker done: %d files in %.0fs (%.1f files/sec), %d matches",
                 total_done, elapsed, rate, total_matches)

    def stop(self):
        self._running = False
        self._task_queue.put(_STOP)
        for gw in self.gpu_workers:
            gw.stop()
