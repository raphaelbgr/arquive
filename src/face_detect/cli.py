"""CLI entry point for face-detect / Arquive.

Extends the original face-detect CLI with new Arquive commands (serve,
cache, fleet, iptv, user, set-password, sessions, describe) while
keeping all existing commands (index, scan, worker, report, status)
fully intact.

Dependencies: argparse (stdlib), plus lazy imports for each command
"""

from __future__ import annotations

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
                generate_html_report(db, config.output.html_path, config.output.thumbnails_dir,
                                 hide_persons=config.hide_persons)
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
    generate_html_report(db, config.output.html_path, config.output.thumbnails_dir,
                                 hide_persons=config.hide_persons)
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
        generate_html_report(db, out, config.output.thumbnails_dir,
                             hide_persons=config.hide_persons)
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


# ===================================================================
# New Arquive commands
# ===================================================================

def cmd_serve(args):
    """Start the full Arquive server (Flask + auth + cache + background scanner)."""
    config = load_config(args.config)
    if args.port:
        config.server.port = args.port
    if args.host:
        config.server.host = args.host
    if args.sec_level:
        config.auth.sec_level = args.sec_level
    if args.cache_dir:
        config.cache.directory = args.cache_dir
    if args.cache_limit:
        config.cache.limit_gb = args.cache_limit

    db = Database(config.output.db_path)

    deduped = db.deduplicate_files()
    if deduped:
        log.info("Removed %d duplicate file entries", deduped)

    from .auth import AuthManager
    auth = AuthManager(db, config)

    # In simple-password mode, generate a password if none exists
    if config.auth.sec_level == "simple-password":
        generated = auth.get_or_create_password()
        if generated:
            print(f"\n  Generated server password: {generated}")
            print(f"  (change with: face-detect set-password <new-password>)\n")

    from .cache_manager import CacheManager
    cache = CacheManager(
        cache_dir=config.cache.directory,
        limit_bytes=int(config.cache.limit_gb * 1024**3),
    )

    # Auto-create libraries from media_dirs if none exist
    if not db.get_libraries() and config.media_dirs:
        for media_dir in config.media_dirs:
            name = Path(media_dir).name or media_dir
            db.add_library(name, "local", media_dir)
            log.info("Auto-created library: %s -> %s", name, media_dir)

    # Background media scanner — indexes files from all libraries on startup
    def _background_scanner():
        time.sleep(2)  # Let Flask start first
        from .sources.local import LocalSource
        libraries = db.get_libraries()
        for lib in libraries:
            if not lib["enabled"]:
                continue
            if lib["type"] == "local":
                try:
                    source = LocalSource(
                        library_id=lib["id"],
                        path=lib["path"],
                        db=db,
                        exclude_dirs=set(config.exclude_dirs),
                    )
                    count = source.scan()
                    log.info("Library '%s' scanned: %d files", lib["name"], count)
                except Exception:
                    log.exception("Failed to scan library '%s'", lib["name"])

    scanner_thread = threading.Thread(target=_background_scanner, daemon=True)
    scanner_thread.start()

    from .webapp import create_app
    app = create_app(config, db, auth, cache)

    print(f"\n  Arquive server starting on http://{config.server.host}:{config.server.port}")
    print(f"  Auth mode: {config.auth.sec_level}")
    print(f"  Cache: {cache.cache_dir} (limit {config.cache.limit_gb} GB)")
    print(f"  Libraries: {len(db.get_libraries())} configured\n")

    app.run(
        host=config.server.host,
        port=config.server.port,
        debug=False,
        use_reloader=False,
    )


def cmd_set_password(args):
    """Set or change the server password."""
    config = load_config(args.config)
    db = Database(config.output.db_path)
    from .auth import AuthManager
    auth = AuthManager(db, config)
    auth.set_password(args.password)
    print("Password updated.")
    db.close()


def cmd_user(args):
    """Manage user accounts."""
    config = load_config(args.config)
    db = Database(config.output.db_path)
    from .auth import AuthManager
    auth = AuthManager(db, config)

    if args.user_action == "add":
        role = args.role or "user"
        import getpass
        password = getpass.getpass(f"Password for {args.username}: ")
        auth.create_user(args.username, password, role)
        print(f"User '{args.username}' created with role '{role}'.")
    elif args.user_action == "list":
        users = db.get_users()
        if not users:
            print("No users.")
        for u in users:
            print(f"  {u['username']}  role={u['role']}  created={u['created_at']}")
    elif args.user_action == "remove":
        if db.remove_user(args.username):
            print(f"User '{args.username}' removed.")
        else:
            print(f"User '{args.username}' not found.")
    db.close()


def cmd_sessions(args):
    """Revoke all active sessions."""
    config = load_config(args.config)
    db = Database(config.output.db_path)
    from .auth import AuthManager
    auth = AuthManager(db, config)
    auth.revoke_all_sessions()
    print("All sessions revoked.")
    db.close()


def cmd_cache(args):
    """Cache management commands."""
    config = load_config(args.config)

    from .cache_manager import CacheManager
    cache = CacheManager(
        cache_dir=config.cache.directory,
        limit_bytes=int(config.cache.limit_gb * 1024**3),
    )

    if args.cache_action == "clear":
        freed = cache.clear()
        print(f"Cache cleared: {freed / 1024**2:.1f} MB freed")
    elif args.cache_action == "stats":
        stats = cache.stats()
        print(f"  Location:  {stats['cache_dir']}")
        print(f"  Enabled:   {stats['enabled']}")
        print(f"  Used:      {stats['used_bytes'] / 1024**3:.2f} GB / {stats['limit_bytes'] / 1024**3:.1f} GB ({stats['used_pct']}%)")
        print(f"  Segments:  {stats['segment_count']}")
    cache.close()


def cmd_fleet(args):
    """GPU fleet management."""
    config = load_config(args.config)

    if args.fleet_action == "test":
        import subprocess
        for worker in config.workers:
            if not worker.ssh_alias:
                print(f"  {worker.name}: localhost (local)")
                continue
            try:
                result = subprocess.run(
                    ["ssh", worker.ssh_alias, "echo", "ok"],
                    capture_output=True, text=True, timeout=10,
                )
                status = "OK" if result.returncode == 0 else f"FAIL: {result.stderr.strip()}"
            except subprocess.TimeoutExpired:
                status = "TIMEOUT"
            except Exception as e:
                status = f"ERROR: {e}"
            print(f"  {worker.name} ({worker.ssh_alias}): {status}")


def cmd_iptv(args):
    """IPTV management commands."""
    config = load_config(args.config)
    db = Database(config.output.db_path)

    if args.iptv_action == "add":
        from .iptv.playlist_manager import PlaylistManager
        pm = PlaylistManager(db)
        playlist_id = pm.add_playlist(args.url, name=args.name)
        print(f"Playlist added (id={playlist_id}). Refreshing...")
        pm.refresh_playlist(playlist_id)
        print("Done.")
    elif args.iptv_action == "list":
        rows = db.conn.execute(
            "SELECT id, name, channel_count, status, last_refreshed FROM iptv_playlists ORDER BY name"
        ).fetchall()
        if not rows:
            print("No playlists configured.")
        for r in rows:
            print(f"  [{r['id']}] {r['name']}  channels={r['channel_count']}  status={r['status']}  refreshed={r['last_refreshed']}")
    elif args.iptv_action == "refresh":
        from .iptv.playlist_manager import PlaylistManager
        pm = PlaylistManager(db)
        rows = db.conn.execute("SELECT id FROM iptv_playlists").fetchall()
        for r in rows:
            pm.refresh_playlist(r["id"])
        print(f"Refreshed {len(rows)} playlists.")
    elif args.iptv_action == "epg-add":
        db.conn.execute(
            "INSERT OR IGNORE INTO epg_sources (url, name) VALUES (?, ?)",
            (args.url, args.name or args.url),
        )
        db.conn.commit()
        print(f"EPG source added: {args.url}")
    elif args.iptv_action == "epg-refresh":
        from .iptv.epg_service import EPGService
        epg = EPGService(db)
        epg.refresh_all()
        print("EPG data refreshed.")

    db.close()


def cmd_describe(args):
    """Run AI descriptions on files."""
    config = load_config(args.config)
    from .describe import generate_description
    target = args.path or "."
    print(f"Generating AI descriptions for: {target}")
    # Delegate to existing describe module
    generate_description(target, config)


# ===================================================================
# Argument parser
# ===================================================================

def main():
    parser = argparse.ArgumentParser(
        prog="face-detect",
        description="Arquive — personal media archive with face detection & live TV",
    )
    parser.add_argument("-c", "--config", default="config.yaml", help="Config file path")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    sub = parser.add_subparsers(dest="command", required=True)

    # --- Existing commands (unchanged) ---

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

    # --- New Arquive commands ---

    # serve
    p_serve = sub.add_parser("serve", help="Start full Arquive server")
    p_serve.add_argument("--port", type=int, help="Server port (default: 64531)")
    p_serve.add_argument("--host", help="Bind address (default: 0.0.0.0)")
    p_serve.add_argument("--sec-level", choices=["simple-password", "user-account", "forever"],
                         help="Authentication mode")
    p_serve.add_argument("--cache-dir", help="Cache directory path")
    p_serve.add_argument("--cache-limit", type=float, help="Cache limit in GB")

    # set-password
    p_setpw = sub.add_parser("set-password", help="Set server password")
    p_setpw.add_argument("password", help="New password")

    # user
    p_user = sub.add_parser("user", help="Manage user accounts")
    p_user_sub = p_user.add_subparsers(dest="user_action", required=True)
    p_user_add = p_user_sub.add_parser("add", help="Add user")
    p_user_add.add_argument("username", help="Username")
    p_user_add.add_argument("--role", choices=["admin", "user", "viewer"], default="user")
    p_user_list = p_user_sub.add_parser("list", help="List users")
    p_user_rm = p_user_sub.add_parser("remove", help="Remove user")
    p_user_rm.add_argument("username", help="Username to remove")

    # sessions
    p_sess = sub.add_parser("sessions", help="Session management")
    p_sess_sub = p_sess.add_subparsers(dest="sessions_action", required=True)
    p_sess_sub.add_parser("revoke-all", help="Revoke all active sessions")

    # cache
    p_cache = sub.add_parser("cache", help="Cache management")
    p_cache_sub = p_cache.add_subparsers(dest="cache_action", required=True)
    p_cache_sub.add_parser("clear", help="Clear transcode cache")
    p_cache_sub.add_parser("stats", help="Show cache usage")

    # fleet
    p_fleet = sub.add_parser("fleet", help="GPU fleet management")
    p_fleet_sub = p_fleet.add_subparsers(dest="fleet_action", required=True)
    p_fleet_sub.add_parser("test", help="Test SSH connectivity to GPU nodes")

    # iptv
    p_iptv = sub.add_parser("iptv", help="IPTV management")
    p_iptv_sub = p_iptv.add_subparsers(dest="iptv_action", required=True)
    p_iptv_add = p_iptv_sub.add_parser("add", help="Add M3U playlist URL")
    p_iptv_add.add_argument("url", help="M3U playlist URL")
    p_iptv_add.add_argument("--name", help="Playlist name")
    p_iptv_sub.add_parser("list", help="List playlists")
    p_iptv_sub.add_parser("refresh", help="Refresh all playlists")
    p_epg_add = p_iptv_sub.add_parser("epg-add", help="Add EPG source URL")
    p_epg_add.add_argument("url", help="XMLTV EPG URL")
    p_epg_add.add_argument("--name", help="EPG source name")
    p_iptv_sub.add_parser("epg-refresh", help="Refresh EPG data")

    # describe
    p_describe = sub.add_parser("describe", help="Run AI descriptions")
    p_describe.add_argument("path", nargs="?", help="File or directory to describe")

    args = parser.parse_args()
    setup_logging(args.verbose)

    commands = {
        "index": cmd_index,
        "scan": cmd_scan,
        "worker": cmd_worker,
        "report": cmd_report,
        "status": cmd_status,
        "serve": cmd_serve,
        "set-password": cmd_set_password,
        "user": cmd_user,
        "sessions": cmd_sessions,
        "cache": cmd_cache,
        "fleet": cmd_fleet,
        "iptv": cmd_iptv,
        "describe": cmd_describe,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
