"""CLI entry point for face-detect."""

import argparse
import json
import logging
import sys
import threading
import time
from pathlib import Path

from .config import load_config, THRESHOLD_PRESETS
from .database import Database
from .indexer import FaceIndexer
from .coordinator.scheduler import TaskScheduler
from .coordinator.api import create_api
from .worker.local_worker import LocalWorker
from .worker.client import WorkerClient
from .worker.processor import MediaProcessor
from .reports.generator import (
    generate_cli_report, generate_json_report, generate_html_report,
)
from .orchestrator import Orchestrator

log = logging.getLogger("face_detect")


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=level, format=fmt, datefmt="%H:%M:%S")
    # Reduce noisy loggers
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def cmd_index(args):
    """Build FAISS index from reference faces."""
    config = load_config(args.config)
    if args.faces_dir:
        config.faces_dir = args.faces_dir

    indexer = FaceIndexer(config)
    indexer.build_index()

    index_dir = str(Path(config.output.db_path).parent / "index")
    indexer.save(index_dir)
    print(f"\nIndex saved to: {index_dir}")
    print(f"  Persons: {len(indexer.person_stats)}")
    for name, stats in indexer.person_stats.items():
        print(f"    {name}: {stats['embedding_count']} embeddings from {stats['image_count']} images")


def cmd_scan(args):
    """Start coordinator and run scan."""
    config = load_config(args.config)

    if args.media:
        config.media_dirs = args.media
    if args.threshold:
        config.recognition.threshold = args.threshold
    elif args.preset:
        config.recognition.threshold = THRESHOLD_PRESETS.get(
            args.preset, config.recognition.threshold
        )

    # Ensure index exists
    index_dir = str(Path(config.output.db_path).parent / "index")
    if not (Path(index_dir) / "index.faiss").exists():
        print("Error: No FAISS index found. Run 'face-detect index' first.")
        sys.exit(1)

    # Initialize database
    db = Database(config.output.db_path)

    # Ensure persons are in DB
    _, labels, stats = FaceIndexer.load(index_dir)
    for person_name in set(labels):
        ec = stats.get(person_name, {}).get("embedding_count", 0)
        db.ensure_person(person_name, ec)

    # Build task queue (skip already-processed files if configured)
    processed_checker = None
    if config.skip_processed and not args.rescan:
        processed_checker = db.is_file_processed
    scheduler = TaskScheduler(config, processed_checker=processed_checker)

    if args.files:
        total = scheduler.add_files(args.files)
    else:
        total = scheduler.scan_media_dirs()

    if total == 0:
        print("No new media files to scan (all previously processed or none found).")
        sys.exit(0)

    print(f"\nScan started: {total} files to process")
    scan_job_id = db.create_scan_job(total)

    # Start coordinator API
    api = create_api(scheduler, db, index_dir, scan_job_id)
    coordinator_url = f"http://localhost:{config.coordinator.port}"

    api_thread = threading.Thread(
        target=lambda: api.run(
            host=config.coordinator.host,
            port=config.coordinator.port,
            debug=False,
            use_reloader=False,
        ),
        daemon=True,
    )
    api_thread.start()
    time.sleep(1)  # Let API start

    # Start remote workers if distributed mode
    orchestrator = None
    if args.distributed:
        orchestrator = Orchestrator(config, coordinator_url)
        orchestrator.start_remote_workers()

    # Start stale task requeuer (for remote workers)
    def _requeue_loop():
        while True:
            time.sleep(60)
            scheduler.requeue_stale_tasks()

    requeue_thread = threading.Thread(target=_requeue_loop, daemon=True)
    requeue_thread.start()

    # Auto-regenerate HTML report every 60 seconds
    def _report_loop():
        while True:
            time.sleep(60)
            try:
                generate_html_report(db, config.output.html_path, config.output.thumbnails_dir)
            except Exception as e:
                log.warning("Report generation failed: %s", e)

    report_thread = threading.Thread(target=_report_loop, daemon=True)
    report_thread.start()

    # Use optimized LocalWorker (bypasses HTTP, prefetches I/O)
    local_worker = LocalWorker(
        config, scheduler, db,
        index_dir=index_dir,
        scan_job_id=scan_job_id,
        worker_name="desktop",
        num_prefetch=4,
    )

    # Run local worker (blocking)
    try:
        local_worker.run()
    except KeyboardInterrupt:
        print("\n\nScan interrupted by user.")
        local_worker.stop()

    # Wait a bit for remote workers to finish
    if orchestrator:
        print("\nWaiting for remote workers to finish...")
        time.sleep(10)
        orchestrator.stop_all()

    # Finalize
    db.finish_scan_job(scan_job_id)
    progress = scheduler.get_progress()
    print(f"\n\nScan complete: {progress['done']} done, {progress['failed']} failed")

    # Auto-generate reports
    print("\nGenerating reports...")
    cli_report = generate_cli_report(db)
    print(cli_report)

    generate_json_report(db, config.output.json_path)
    generate_html_report(db, config.output.html_path, config.output.thumbnails_dir)
    print(f"\nJSON report: {config.output.json_path}")
    print(f"HTML report: {config.output.html_path}")

    db.close()


def cmd_worker(args):
    """Run as a remote worker."""
    config = load_config(args.config)
    if args.threshold:
        config.recognition.threshold = args.threshold

    # Find path_map for this worker from config
    path_map = {}
    for w in config.workers:
        if w.name == args.name:
            path_map = w.path_map
            break

    worker = WorkerClient(
        config,
        worker_name=args.name,
        coordinator_url=args.coordinator,
        path_map=path_map,
    )

    try:
        worker.run()
    except KeyboardInterrupt:
        worker.stop()


def cmd_report(args):
    """Generate reports from existing results database."""
    config = load_config(args.config)
    db_path = args.db or config.output.db_path

    if not Path(db_path).exists():
        print(f"Error: Database not found: {db_path}")
        sys.exit(1)

    db = Database(db_path)
    fmt = args.format or "all"

    if fmt in ("cli", "all"):
        print(generate_cli_report(db))

    if fmt in ("json", "all"):
        out = args.output or config.output.json_path
        generate_json_report(db, out)
        print(f"JSON report: {out}")

    if fmt in ("html", "all"):
        out = args.output or config.output.html_path
        generate_html_report(db, out, config.output.thumbnails_dir)
        print(f"HTML report: {out}")

    db.close()


def cmd_status(args):
    """Show scan progress from coordinator."""
    import requests
    url = args.coordinator or "http://localhost:8600"
    try:
        resp = requests.get(f"{url}/progress", timeout=5)
        data = resp.json()
        print(f"Scan progress:")
        print(f"  Total:    {data['total']}")
        print(f"  Done:     {data['done']}")
        print(f"  Failed:   {data['failed']}")
        print(f"  Assigned: {data['assigned']}")
        print(f"  Pending:  {data['pending']}")
        print(f"  Progress: {data['progress_pct']:.1f}%")
    except Exception as e:
        print(f"Error contacting coordinator: {e}")


def main():
    parser = argparse.ArgumentParser(
        prog="face-detect",
        description="Distributed face recognition across media archives",
    )
    parser.add_argument("-c", "--config", default="config.yaml", help="Config file path")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    sub = parser.add_subparsers(dest="command", required=True)

    # index
    p_index = sub.add_parser("index", help="Build FAISS index from reference faces")
    p_index.add_argument("--faces-dir", help="Override faces directory")

    # scan
    p_scan = sub.add_parser("scan", help="Start scan coordinator + local worker")
    p_scan.add_argument("--media", nargs="+", help="Override media directories")
    p_scan.add_argument("--files", nargs="+", help="Scan specific files instead of directories")
    p_scan.add_argument("--distributed", action="store_true",
                        help="Also start remote workers via SSH")
    p_scan.add_argument("--threshold", type=float, help="Recognition threshold (0.0-1.0)")
    p_scan.add_argument("--preset", choices=list(THRESHOLD_PRESETS.keys()),
                        help="Use a threshold preset")
    p_scan.add_argument("--rescan", action="store_true",
                        help="Ignore previous results, rescan all files")

    # worker
    p_worker = sub.add_parser("worker", help="Run as a remote worker")
    p_worker.add_argument("--name", required=True, help="Worker name")
    p_worker.add_argument("--coordinator", required=True, help="Coordinator URL")
    p_worker.add_argument("--threshold", type=float, help="Recognition threshold override")

    # report
    p_report = sub.add_parser("report", help="Generate reports from results")
    p_report.add_argument("--format", choices=["cli", "json", "html", "all"], default="all")
    p_report.add_argument("--output", help="Output file path")
    p_report.add_argument("--db", help="Database file path")

    # status
    p_status = sub.add_parser("status", help="Show scan progress")
    p_status.add_argument("--coordinator", help="Coordinator URL")

    args = parser.parse_args()
    setup_logging(args.verbose)

    commands = {
        "index": cmd_index,
        "scan": cmd_scan,
        "worker": cmd_worker,
        "report": cmd_report,
        "status": cmd_status,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
