"""HTTP API for the coordinator — serves tasks to workers and collects results."""

import io
import json
import logging
import threading
import time
from pathlib import Path

from flask import Flask, request, jsonify, send_file

from .scheduler import TaskScheduler
from ..database import Database

log = logging.getLogger(__name__)


def create_api(scheduler: TaskScheduler, db: Database, index_dir: str,
               scan_job_id: int) -> Flask:
    """Create the Flask API app for the coordinator."""

    app = Flask(__name__)
    app.logger.setLevel(logging.WARNING)  # Reduce Flask noise

    # Track worker health
    worker_heartbeats = {}
    hb_lock = threading.Lock()

    @app.route("/index", methods=["GET"])
    def get_index():
        """Download FAISS index + labels as a tar-like bundle."""
        index_path = Path(index_dir).resolve()
        which = request.args.get("file", "index.faiss")
        file_path = index_path / which
        if not file_path.exists():
            return jsonify({"error": f"File not found: {which}"}), 404
        return send_file(str(file_path.resolve()), as_attachment=True)

    @app.route("/task", methods=["GET"])
    def get_task():
        """Pull next available task. Query params: worker=<name>"""
        worker_name = request.args.get("worker", "")
        task = scheduler.get_next_task(worker_name)
        if task is None:
            return jsonify({"task": None, "message": "No tasks available"}), 200
        return jsonify({"task": task}), 200

    @app.route("/result", methods=["POST"])
    def post_result():
        """Submit processing result for a task."""
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON body"}), 400

        task_id = data.get("task_id")
        result = data.get("result", {})
        error = data.get("error")

        if error:
            scheduler.fail_task(task_id, error)
            db.mark_file_processed(
                result.get("file_path", ""), scan_job_id,
                status="failed"
            )
        else:
            scheduler.complete_task(task_id, result)

            # Store matches in database
            matches = result.get("matches", [])
            if matches:
                db_matches = []
                for m in matches:
                    db_matches.append({
                        "scan_job_id": scan_job_id,
                        "person_name": m["person_name"],
                        "file_path": result["file_path"],
                        "file_type": result["file_type"],
                        "confidence": m["confidence"],
                        "timestamp_start": m.get("timestamp_start"),
                        "timestamp_end": m.get("timestamp_end"),
                        "thumbnail_path": m.get("thumbnail_path"),
                        "file_hash": result.get("file_hash"),
                    })
                db.add_matches_batch(db_matches)

            db.mark_file_processed(
                result["file_path"], scan_job_id,
                file_hash=result.get("file_hash"),
                status="done"
            )

        # Update scan progress
        progress = scheduler.get_progress()
        matched_count = db.conn.execute(
            "SELECT COUNT(DISTINCT file_path) FROM matches WHERE scan_job_id=?",
            (scan_job_id,)
        ).fetchone()[0]
        db.update_scan_progress(
            scan_job_id, progress["done"], matched_count, progress["failed"]
        )

        return jsonify({"ok": True}), 200

    @app.route("/progress", methods=["GET"])
    def get_progress():
        """Get current scan progress."""
        progress = scheduler.get_progress()
        return jsonify(progress), 200

    @app.route("/health", methods=["POST"])
    def worker_health():
        """Worker heartbeat endpoint."""
        data = request.get_json() or {}
        worker_name = data.get("worker", "unknown")
        with hb_lock:
            worker_heartbeats[worker_name] = {
                "last_seen": time.time(),
                "status": data.get("status", "idle"),
            }
        return jsonify({"ok": True}), 200

    @app.route("/workers", methods=["GET"])
    def list_workers():
        """List connected workers and their status."""
        with hb_lock:
            return jsonify(worker_heartbeats), 200

    return app
