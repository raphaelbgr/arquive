"""Live web dashboard for face detection results + Arquive API server.

Serves on port 64531.  Two factory functions:

  - ``create_webapp(config)`` — original face-detection dashboard (backward compat)
  - ``create_app(config, db, auth, cache)`` — full Arquive server with REST API,
    React frontend serving, auth, IPTV, cache, fleet, AI, and settings endpoints.

Dependencies: flask, pathlib, json, logging
"""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import re
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, send_file, send_from_directory, request, render_template_string, Response, make_response

from .config import load_config
from .database import Database

log = logging.getLogger(__name__)

# Cache for extract_date_from_path results (file_path -> iso date string)
_date_cache: dict[str, str] = {}

_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp', '.webp', '.heic'}
_VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', '.m4v', '.mpg', '.mpeg'}


def _extract_date_from_exif(file_path: str) -> str:
    """Try to read date from image EXIF data. Returns ISO date or empty string."""
    try:
        from PIL import Image
        img = Image.open(file_path)
        exif = img.getexif()
        if not exif:
            return ""
        # Tag 36867 = DateTimeOriginal, Tag 36868 = DateTimeDigitized, Tag 306 = DateTime
        for tag_id in (36867, 36868, 306):
            val = exif.get(tag_id)
            if val and isinstance(val, str):
                # EXIF date format: "YYYY:MM:DD HH:MM:SS"
                dt = datetime.strptime(val.strip()[:10], "%Y:%m:%d")
                return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    return ""


def _extract_date_from_file_creation(file_path: str) -> str:
    """Get the file creation/birth date. Returns ISO date or empty string."""
    try:
        stat = os.stat(file_path)
        # On Windows, st_ctime is creation time; on Unix it's metadata change time.
        # Use st_birthtime if available (macOS), otherwise st_ctime.
        ctime = getattr(stat, 'st_birthtime', None) or stat.st_ctime
        dt = datetime.fromtimestamp(ctime)
        # Only trust dates from 2000 onward
        if dt.year >= 2000:
            return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    return ""


def _extract_date_from_filename(file_path: str) -> str:
    """Try to extract a date from the file path or name (original logic)."""
    name = Path(file_path).stem
    m = re.search(r'(20[012]\d)(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])', name)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r'(20[012]\d)[-_](0[1-9]|1[0-2])[-_](0[1-9]|[12]\d|3[01])', name)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    parts = Path(file_path).parts
    for part in parts:
        if re.match(r'^(19|20)\d{2}$', part):
            return f"{part}-01-01"
    return ""


def extract_date_from_path(file_path: str) -> str:
    """Extract a date from file metadata or path, with caching.

    Priority:
    1. EXIF DateTimeOriginal / DateTimeDigitized (images)
    2. EXIF DateTime / CreateDate (images)
    3. File creation date
    4. Filename pattern (fallback)
    """
    if file_path in _date_cache:
        return _date_cache[file_path]

    result = ""
    ext = Path(file_path).suffix.lower()

    # 1 & 2: Try EXIF for images (handles DateTimeOriginal, DateTimeDigitized, DateTime)
    if ext in _IMAGE_EXTENSIONS:
        result = _extract_date_from_exif(file_path)

    # 3: File creation date (for both images and videos if no EXIF date found)
    if not result and os.path.isfile(file_path):
        result = _extract_date_from_file_creation(file_path)

    # 4: Filename pattern fallback
    if not result:
        result = _extract_date_from_filename(file_path)

    _date_cache[file_path] = result
    return result


def create_webapp(config=None):
    if config is None:
        config = load_config()

    db = Database(config.output.db_path)
    hide_persons = set(config.hide_persons or [])
    thumbs_dir = Path(config.output.thumbnails_dir).resolve()

    app = Flask(__name__)
    app.logger.setLevel(logging.WARNING)

    @app.route("/")
    def index():
        return render_template_string(APP_HTML)

    @app.route("/api/stats")
    def api_stats():
        stats = db.get_scan_stats()
        persons = db.conn.execute(
            "SELECT person_name, COUNT(*) as count FROM matches GROUP BY person_name"
        ).fetchall()
        person_list = [
            {"name": r[0], "count": r[1]}
            for r in persons if r[0] not in hide_persons
        ]
        described = db.conn.execute(
            "SELECT COUNT(*) FROM matches WHERE description IS NOT NULL"
        ).fetchone()[0]
        return jsonify({
            "stats": stats,
            "persons": person_list,
            "descriptions_done": described,
        })

    @app.route("/api/matches")
    def api_matches():
        person = request.args.get("person", "")
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 50))
        offset = (page - 1) * per_page

        query = """SELECT person_name, file_path, file_type, confidence,
                          timestamp_start, timestamp_end, thumbnail_path, description
                   FROM matches WHERE 1=1"""
        params = []

        if person:
            query += " AND person_name = ?"
            params.append(person)
        for hp in hide_persons:
            query += " AND person_name != ?"
            params.append(hp)

        query += " ORDER BY confidence DESC LIMIT ? OFFSET ?"
        params.extend([per_page, offset])

        rows = db.conn.execute(query, params).fetchall()

        count_query = "SELECT COUNT(*) FROM matches WHERE 1=1"
        count_params = []
        if person:
            count_query += " AND person_name = ?"
            count_params.append(person)
        for hp in hide_persons:
            count_query += " AND person_name != ?"
            count_params.append(hp)
        total = db.conn.execute(count_query, count_params).fetchone()[0]

        matches = []
        for r in rows:
            fp = r[1]
            thumb = Path(r[6]).name if r[6] else None
            # Check for video frame thumbnail
            vthumb = None
            if r[2] == "video" and r[4] is not None:
                vt_name = f"{Path(fp).stem}_{r[4]:.1f}s.jpg"
                if (video_thumbs_dir / vt_name).exists():
                    vthumb = vt_name
            matches.append({
                "person_name": r[0], "file_path": fp, "file_name": Path(fp).name,
                "file_type": r[2], "confidence": r[3],
                "timestamp_start": r[4], "timestamp_end": r[5],
                "thumbnail": thumb, "video_thumb": vthumb,
                "description": r[7], "date": extract_date_from_path(fp),
            })

        return jsonify({
            "matches": matches, "total": total, "page": page,
            "per_page": per_page, "pages": (total + per_page - 1) // per_page,
        })

    @app.route("/api/matches/by-date")
    def api_matches_by_date():
        person = request.args.get("person", "")
        query = """SELECT person_name, file_path, file_type, confidence,
                          timestamp_start, timestamp_end, thumbnail_path, description
                   FROM matches WHERE 1=1"""
        params = []
        if person:
            query += " AND person_name = ?"
            params.append(person)
        for hp in hide_persons:
            query += " AND person_name != ?"
            params.append(hp)
        query += " ORDER BY file_path"
        rows = db.conn.execute(query, params).fetchall()

        by_date = {}
        for r in rows:
            fp = r[1]
            date_str = extract_date_from_path(fp) or "Unknown Date"
            if date_str not in by_date:
                by_date[date_str] = []
            thumb = Path(r[6]).name if r[6] else None
            vthumb = None
            if r[2] == "video" and r[4] is not None:
                vt_name = f"{Path(fp).stem}_{r[4]:.1f}s.jpg"
                if (video_thumbs_dir / vt_name).exists():
                    vthumb = vt_name
            by_date[date_str].append({
                "person_name": r[0], "file_path": fp, "file_name": Path(fp).name,
                "file_type": r[2], "confidence": r[3],
                "timestamp_start": r[4], "timestamp_end": r[5],
                "thumbnail": thumb, "video_thumb": vthumb,
                "description": r[7],
            })

        sorted_dates = sorted(by_date.keys(), reverse=True)
        result = [{"date": d, "matches": by_date[d], "count": len(by_date[d])}
                  for d in sorted_dates]
        return jsonify({"groups": result, "total_dates": len(result)})

    video_thumbs_dir = (Path(config.output.thumbnails_dir) / ".." / "video_thumbs").resolve()

    @app.route("/thumb/<path:filename>")
    def serve_thumb(filename):
        thumb_file = thumbs_dir / filename
        if thumb_file.exists():
            return send_from_directory(str(thumbs_dir), filename)
        # Return a 1x1 transparent pixel as fallback
        import base64
        pixel = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVQI12NgAAIABQABNjN9GQAAAAlwSFlzAAAWJQAAFiUBSVIk8AAAAA0lEQVQI12P4z8BQDwAEgAF/QualcQAAAABJRU5ErkJggg==")
        return Response(pixel, mimetype="image/png")

    @app.route("/vthumb/<path:filename>")
    def serve_video_thumb(filename):
        vthumb_file = video_thumbs_dir / filename
        if vthumb_file.exists():
            return send_from_directory(str(video_thumbs_dir), filename)
        # Return a 1x1 transparent pixel as fallback
        import base64
        pixel = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVQI12NgAAIABQABNjN9GQAAAAlwSFlzAAAWJQAAFiUBSVIk8AAAAA0lEQVQI12P4z8BQDwAEgAF/QualcQAAAABJRU5ErkJggg==")
        return Response(pixel, mimetype="image/png")

    @app.route("/api/activity")
    def api_activity():
        # Check if coordinator scan is running
        scan_running = False
        scan_progress = None
        try:
            req = urllib.request.Request("http://localhost:8600/progress")
            with urllib.request.urlopen(req, timeout=1) as resp:
                data = json.loads(resp.read().decode())
                scan_running = True
                if isinstance(data, dict) and "done" in data and "total" in data:
                    scan_progress = {"done": data["done"], "total": data["total"]}
        except Exception:
            scan_running = False
            scan_progress = None

        # Description generation progress
        total_matches = db.conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
        described = db.conn.execute(
            "SELECT COUNT(*) FROM matches WHERE description IS NOT NULL"
        ).fetchone()[0]

        return jsonify({
            "scan_running": scan_running,
            "scan_progress": scan_progress,
            "describe_progress": {"done": described, "total": total_matches},
        })

    @app.route("/file")
    def serve_file():
        path = request.args.get("path", "")
        if not path or not os.path.exists(path):
            return "Not found", 404

        # Reject empty/corrupt files
        if os.path.getsize(path) == 0:
            return "Empty file", 204

        # Transcode HEVC/H.265 videos to H.264 on-the-fly for browser playback only.
        # DLNA clients (Apple TV, Smart TVs) handle HEVC natively — skip transcoding
        # when ?transcode=0 is passed or when request comes from a non-browser client.
        lower_path = path.lower()
        is_video = lower_path.endswith((".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".wmv", ".flv", ".3gp", ".mts"))
        # Only transcode when explicitly requested (?transcode=1)
        # Browsers should try native playback first — many support HEVC now
        if is_video and request.args.get("transcode") == "1":
            try:
                import subprocess as sp
                probe = sp.run(
                    ["ffprobe", "-v", "error", "-select_streams", "v:0",
                     "-show_entries", "stream=codec_name", "-of", "csv=p=0", path],
                    capture_output=True, text=True, timeout=5,
                )
                codec = probe.stdout.strip().lower()
                if codec in ("hevc", "h265", "vp6", "vp6f", "mpeg4", "msmpeg4v3", "wmv3"):
                    # Stream-transcode to H.264 via FFmpeg pipe
                    # Try NVENC (GPU) first, fall back to CPU libx264
                    def _pick_encoder():
                        try:
                            test = sp.run(["ffmpeg", "-hide_banner", "-encoders"],
                                         capture_output=True, text=True, timeout=5)
                            if "h264_nvenc" in test.stdout:
                                return ["ffmpeg", "-hwaccel", "cuda", "-i", path,
                                        "-c:v", "h264_nvenc", "-preset", "p1",
                                        "-b:v", "8M", "-c:a", "aac", "-b:a", "128k",
                                        "-movflags", "frag_keyframe+empty_moov+faststart",
                                        "-f", "mp4", "pipe:1"]
                        except Exception:
                            pass
                        return ["ffmpeg", "-i", path, "-c:v", "libx264", "-preset", "ultrafast",
                                "-crf", "23", "-c:a", "aac", "-b:a", "128k",
                                "-movflags", "frag_keyframe+empty_moov+faststart",
                                "-f", "mp4", "pipe:1"]

                    def generate():
                        proc = sp.Popen(_pick_encoder(), stdout=sp.PIPE, stderr=sp.DEVNULL)
                        try:
                            while True:
                                chunk = proc.stdout.read(65536)
                                if not chunk:
                                    break
                                yield chunk
                        finally:
                            proc.terminate()
                    return Response(generate(), mimetype="video/mp4")
            except Exception as e:
                log.debug("Video codec check failed for %s: %s", path, e)

        # Optional thumbnail mode: ?w=320 resizes images for grid view
        thumb_width = request.args.get("w", type=int)

        # Images that need conversion or resizing
        lower = path.lower()
        is_heic = lower.endswith((".heic", ".heif"))
        is_image = lower.endswith((".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif", ".gif")) or is_heic

        if is_image and (is_heic or thumb_width):
            try:
                if is_heic:
                    from pillow_heif import register_heif_opener
                    register_heif_opener()
                from PIL import Image, ImageOps
                import io
                img = Image.open(path)
                # Auto-rotate based on EXIF orientation (fixes -270 degree rotated images)
                img = ImageOps.exif_transpose(img)
                if thumb_width and img.width > thumb_width:
                    ratio = thumb_width / img.width
                    new_h = int(img.height * ratio)
                    img = img.resize((thumb_width, new_h), Image.LANCZOS)
                buf = io.BytesIO()
                img.convert("RGB").save(buf, format="JPEG", quality=80)
                buf.seek(0)
                resp = Response(buf.getvalue(), mimetype="image/jpeg")
                resp.headers["Cache-Control"] = "public, max-age=86400"
                return resp
            except Exception as e:
                log.debug("Image processing failed for %s: %s", path, e)
                if is_heic:
                    # Return a 1x1 transparent PNG as fallback for corrupt/empty HEIC files
                    import base64
                    pixel = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVQI12NgAAIABQABNjN9GQAAAAlwSFlzAAAWJQAAFiUBSVIk8AAAAA0lEQVQI12P4z8BQDwAEgAF/QualcQAAAABJRU5ErkJggg==")
                    return Response(pixel, mimetype="image/png", status=200)

        return send_file(path, conditional=True)

    return app


# ===================================================================
# Arquive App Factory — full server with all API routes
# ===================================================================

PREVIEW_TILES_DEFAULTS = {
    "mediaLibrary": "always",
    "liveTV": "always",
    "frameIntervalMs": 1500,
    "crossfadeDurationMs": 200,
    "spriteFrameCount": 10,
}


def create_app(config: Any, db: Database, auth: Any, cache: Any) -> Flask:
    """Create the full Arquive Flask application.

    Builds on top of ``create_webapp`` routes and adds all ``/api/v1/*``
    endpoints for media, faces, IPTV, cache, fleet, AI, auth, and settings.
    """
    # Start with the existing face-detection app
    base_app = create_webapp(config)

    app = Flask(__name__, static_folder=None)
    app.logger.setLevel(logging.WARNING)

    # Register existing routes from create_webapp, except "/" (we override it with React)
    for rule in base_app.url_map.iter_rules():
        if rule.endpoint == "static" or rule.rule == "/":
            continue
        view_func = base_app.view_functions.get(rule.endpoint)
        if view_func:
            app.add_url_rule(rule.rule, rule.endpoint, view_func, methods=list(rule.methods - {"OPTIONS", "HEAD"}))

    # Serve React frontend in production (web/dist/)
    web_dist = Path(__file__).parent.parent.parent / "web" / "dist"

    @app.route("/")
    def serve_index():
        if web_dist.exists() and (web_dist / "index.html").exists():
            resp = make_response(send_from_directory(str(web_dist), "index.html"))
            resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            return resp
        return render_template_string(APP_HTML)

    @app.route("/assets/<path:filename>")
    def serve_assets(filename: str):
        return send_from_directory(str(web_dist / "assets"), filename)

    # SPA catch-all: serve index.html for any non-API, non-static route
    # so that React Router handles client-side navigation
    @app.errorhandler(404)
    def spa_fallback(e: Any):
        if web_dist.exists() and (web_dist / "index.html").exists():
            return send_from_directory(str(web_dist), "index.html")
        return jsonify({"error": "Not found"}), 404

    # ----- Auth API (/api/v1/auth) -----

    @app.route("/api/v1/auth/login", methods=["POST"])
    def api_login():
        data = request.get_json() or {}
        if config.auth.sec_level == "forever":
            token = auth.issue_token("anonymous", "admin")
            resp = make_response(jsonify({"ok": True, "role": "admin"}))
            resp.set_cookie("arquive_token", token, httponly=True, samesite="Lax", max_age=365 * 86400)
            return resp

        if config.auth.sec_level == "simple-password":
            if not auth.check_password(data.get("password", "")):
                return jsonify({"error": "Invalid password"}), 401
            token = auth.issue_token("user", "admin")
        else:
            user = auth.authenticate_user(data.get("username", ""), data.get("password", ""))
            if not user:
                return jsonify({"error": "Invalid credentials"}), 401
            token = auth.issue_token(user["username"], user["role"])

        resp = make_response(jsonify({"ok": True}))
        resp.set_cookie("arquive_token", token, httponly=True, samesite="Lax", max_age=365 * 86400)
        return resp

    @app.route("/api/v1/auth/logout", methods=["POST"])
    def api_logout():
        resp = make_response(jsonify({"ok": True}))
        resp.delete_cookie("arquive_token")
        return resp

    @app.route("/api/v1/auth/me")
    def api_auth_me():
        if config.auth.sec_level == "forever":
            return jsonify({"user": "anonymous", "role": "admin", "sec_level": "forever"})
        token = request.cookies.get("arquive_token") or _bearer(request)
        if not token:
            return jsonify({"error": "Not authenticated"}), 401
        payload = auth.validate_token(token)
        if not payload:
            return jsonify({"error": "Invalid token"}), 401
        return jsonify({"user": payload.get("sub"), "role": payload.get("role"), "sec_level": config.auth.sec_level})

    @app.route("/api/v1/auth/revoke-all", methods=["POST"])
    def api_revoke_all():
        auth.revoke_all_sessions()
        return jsonify({"ok": True})

    # ----- Media API (/api/v1/media) -----

    _MEDIA_ONLY_EXTS = (
        ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".tif", ".svg",
        ".heic", ".heif", ".avif", ".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v",
        ".wmv", ".flv", ".mpg", ".mpeg", ".3gp", ".mp3", ".flac", ".wav", ".aac",
        ".ogg", ".wma", ".m4a", ".opus",
    )
    _DOC_EXTS = (
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".txt", ".rtf", ".odt", ".ods", ".odp",
    )

    @app.route("/api/v1/media")
    def api_media_list():
        page = int(request.args.get("page", 1))
        limit = int(request.args.get("limit", 50))
        library_id = request.args.get("library_id", type=int)
        extension = request.args.get("extension")
        folder = request.args.get("folder")
        month = request.args.get("month")  # YYYY-MM for timeline
        media_type = request.args.get("type")  # 'media_only', 'documents', 'office', 'text'

        # Support explicit offset param (overrides page calculation)
        offset = request.args.get("offset", type=int)
        if offset is None:
            offset = (page - 1) * limit

        if folder:
            folder_fwd = folder.replace("\\", "/")
            folder_bk = folder.replace("/", "\\")
            query = "SELECT * FROM files WHERE (path LIKE ? OR path LIKE ?) ORDER BY modified_at DESC LIMIT ? OFFSET ?"
            rows = db.conn.execute(query, (f"{folder_fwd}%", f"{folder_bk}%", limit, offset)).fetchall()
            total = db.conn.execute("SELECT COUNT(*) FROM files WHERE (path LIKE ? OR path LIKE ?)", (f"{folder_fwd}%", f"{folder_bk}%")).fetchone()[0]
        elif month:
            # Timeline: only media (images/video/audio), exclude documents
            ext_placeholders = ",".join("?" for _ in _MEDIA_ONLY_EXTS)
            rows = db.conn.execute(
                f"SELECT * FROM files WHERE modified_at LIKE ? AND extension IN ({ext_placeholders}) "
                f"ORDER BY modified_at DESC LIMIT ? OFFSET ?",
                (f"{month}%", *_MEDIA_ONLY_EXTS, limit, offset),
            ).fetchall()
            total = db.conn.execute(
                f"SELECT COUNT(*) FROM files WHERE modified_at LIKE ? AND extension IN ({ext_placeholders})",
                (f"{month}%", *_MEDIA_ONLY_EXTS),
            ).fetchone()[0]
        else:
            # Build WHERE clause
            where_parts = ["1=1"]
            params: list = []

            if library_id is not None:
                where_parts.append("library_id = ?")
                params.append(library_id)
            if extension:
                where_parts.append("extension = ?")
                params.append(extension)

            # Type filtering
            if media_type == "documents":
                ext_ph = ",".join("?" for _ in _DOC_EXTS)
                where_parts.append(f"extension IN ({ext_ph})")
                params.extend(_DOC_EXTS)
            elif media_type == "media_only":
                ext_ph = ",".join("?" for _ in _MEDIA_ONLY_EXTS)
                where_parts.append(f"extension IN ({ext_ph})")
                params.extend(_MEDIA_ONLY_EXTS)

            # MIME type prefix filter (e.g. "image,video")
            mime_filter = request.args.get("mime_filter")
            if mime_filter:
                prefixes = [p.strip() for p in mime_filter.split(",") if p.strip()]
                if prefixes:
                    mime_clauses = []
                    for prefix in prefixes:
                        mime_clauses.append("mime_type LIKE ?")
                        params.append(f"{prefix}/%")
                    where_parts.append(f"({' OR '.join(mime_clauses)})")

            where = " AND ".join(where_parts)
            rows = db.conn.execute(
                f"SELECT * FROM files WHERE {where} ORDER BY modified_at DESC LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ).fetchall()
            total = db.conn.execute(
                f"SELECT COUNT(*) FROM files WHERE {where}", params,
            ).fetchone()[0]

        return jsonify({
            "items": [dict(r) for r in rows],
            "total": total,
            "page": page,
            "limit": limit,
            "pages": max(1, (total + limit - 1) // limit),
        })

    @app.route("/api/v1/media/<int:media_id>")
    def api_media_detail(media_id: int):
        f = db.get_file_by_id(media_id)
        if not f:
            return jsonify({"error": "Not found"}), 404
        return jsonify(f)

    @app.route("/api/v1/media/<int:media_id>", methods=["DELETE"])
    def api_media_delete(media_id: int):
        """Delete a file record from the index (does NOT delete the actual file)."""
        f = db.get_file_by_id(media_id)
        if not f:
            return jsonify({"error": "Not found"}), 404
        with db._lock:
            db.conn.execute("DELETE FROM files WHERE id = ?", (media_id,))
            db.conn.commit()
        return jsonify({"ok": True, "id": media_id})

    @app.route("/api/v1/media/<int:media_id>/thumbnail")
    def api_media_thumbnail(media_id: int):
        """Serve thumbnail — for videos, generates a poster frame on-demand via FFmpeg."""
        f = db.get_file_by_id(media_id)
        if not f:
            return jsonify({"error": "Not found"}), 404

        # If we already have a cached thumbnail, serve it
        if f.get("thumbnail_path") and os.path.exists(f["thumbnail_path"]):
            return send_file(f["thumbnail_path"])

        file_path = f["path"]
        mime = (f.get("mime_type") or "").lower()

        # For videos: extract a poster frame via FFmpeg
        if mime.startswith("video/") and os.path.exists(file_path):
            poster_dir = cache.thumbnails_dir
            poster_path = poster_dir / f"poster_{media_id}.jpg"

            if poster_path.exists():
                resp = make_response(send_file(str(poster_path)))
                resp.headers["Cache-Control"] = "public, max-age=86400"
                return resp

            try:
                import subprocess
                # Extract frame at 10% of duration for a representative frame
                result = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "default=noprint_wrappers=1:nokey=1", file_path],
                    capture_output=True, text=True, timeout=10,
                )
                duration = float(result.stdout.strip()) if result.returncode == 0 else 5.0

                # Try multiple positions, keep the brightest frame
                vf = "scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2:black"
                best_path = None
                best_brightness = -1
                from PIL import Image as _PILImage
                for pct in (0.25, 0.5, 0.1, 0.75):
                    seek = min(duration * pct, 120)
                    tmp = str(poster_path) + f".tmp{int(pct*100)}.jpg"
                    subprocess.run(
                        ["ffmpeg", "-y", "-hwaccel", "cuda", "-ss", str(seek), "-i", file_path,
                         "-vframes", "1", "-vf", vf, "-q:v", "5", tmp],
                        capture_output=True, timeout=15,
                    )
                    if os.path.exists(tmp) and os.path.getsize(tmp) > 0:
                        try:
                            timg = _PILImage.open(tmp)
                            raw = timg.convert("L").tobytes()
                            brightness = sum(raw) / len(raw)
                            if brightness > best_brightness:
                                best_brightness = brightness
                                if best_path and best_path != tmp:
                                    os.remove(best_path)
                                best_path = tmp
                            else:
                                os.remove(tmp)
                        except Exception:
                            if os.path.exists(tmp):
                                os.remove(tmp)
                    if best_brightness > 80:
                        break  # Good enough
                if best_path:
                    os.rename(best_path, str(poster_path))
                    # Clean leftover temps
                    for pct in (0.25, 0.5, 0.1, 0.75):
                        tmp = str(poster_path) + f".tmp{int(pct*100)}.jpg"
                        if os.path.exists(tmp):
                            os.remove(tmp)

                if poster_path.exists():
                    # Update DB so we don't regenerate next time
                    with db._lock:
                        db.conn.execute(
                            "UPDATE files SET thumbnail_path = ? WHERE id = ?",
                            (str(poster_path), media_id),
                        )
                        db.conn.commit()
                    resp = make_response(send_file(str(poster_path)))
                    resp.headers["Cache-Control"] = "public, max-age=86400"
                    return resp
            except Exception as e:
                log.debug("Video poster generation failed for %d: %s", media_id, e)

        # For images without thumbnails, redirect to file endpoint with resize
        if mime.startswith("image/") and os.path.exists(file_path):
            from flask import redirect
            return redirect(f"/file?path={file_path}&w=320")

        return jsonify({"error": "No thumbnail available"}), 404

    @app.route("/api/v1/media/<int:media_id>/download")
    def api_media_download(media_id: int):
        f = db.get_file_by_id(media_id)
        if not f:
            return jsonify({"error": "Not found"}), 404
        return send_file(f["path"], as_attachment=True)

    @app.route("/api/v1/media/<int:media_id>/stream")
    def api_media_stream(media_id: int):
        f = db.get_file_by_id(media_id)
        if not f:
            return jsonify({"error": "Not found"}), 404
        # Return HLS manifest placeholder — transcoder will generate actual segments
        return jsonify({"manifest": f"/api/v1/stream/{media_id}/manifest.m3u8"})

    @app.route("/api/v1/media/search")
    def api_media_search():
        q = request.args.get("q", "")
        limit = int(request.args.get("limit", 50))
        rows = db.conn.execute(
            "SELECT * FROM files WHERE name LIKE ? OR ai_description LIKE ? LIMIT ?",
            (f"%{q}%", f"%{q}%", limit),
        ).fetchall()
        return jsonify({"items": [dict(r) for r in rows], "query": q})

    @app.route("/api/v1/media/batch", methods=["POST"])
    def api_media_batch():
        """Fetch files for multiple months in a single request."""
        data = request.get_json() or {}
        months = data.get("months", [])
        limit = int(data.get("limit", 30))

        ext_placeholders = ",".join("?" for _ in _MEDIA_ONLY_EXTS)
        results = {}
        for month in months[:20]:  # Cap at 20 months per batch
            rows = db.conn.execute(
                f"SELECT * FROM files WHERE modified_at LIKE ? AND extension IN ({ext_placeholders}) "
                f"ORDER BY modified_at DESC LIMIT ?",
                (f"{month}%", *_MEDIA_ONLY_EXTS, limit),
            ).fetchall()
            total = db.conn.execute(
                f"SELECT COUNT(*) FROM files WHERE modified_at LIKE ? AND extension IN ({ext_placeholders})",
                (f"{month}%", *_MEDIA_ONLY_EXTS),
            ).fetchone()[0]
            results[month] = {"items": [dict(r) for r in rows], "total": total}

        return jsonify(results)

    @app.route("/api/v1/media/stats")
    def api_media_stats():
        total = db.get_file_count()
        row = db.conn.execute(
            "SELECT COUNT(DISTINCT extension) as ext_count, "
            "COALESCE(SUM(size), 0) as total_size FROM files"
        ).fetchone()
        return jsonify({
            "total_files": total,
            "total_size": row["total_size"],
            "extension_count": row["ext_count"],
        })

    @app.route("/api/v1/media/timeline")
    def api_media_timeline():
        # Timeline only shows media (images, video, audio) — not documents
        ext_placeholders = ",".join("?" for _ in _MEDIA_ONLY_EXTS)
        rows = db.conn.execute(
            f"SELECT strftime('%Y-%m', modified_at) as month, COUNT(*) as count "
            f"FROM files WHERE modified_at IS NOT NULL AND extension IN ({ext_placeholders}) "
            f"GROUP BY month ORDER BY month DESC",
            _MEDIA_ONLY_EXTS,
        ).fetchall()
        return jsonify({"groups": [dict(r) for r in rows]})

    @app.route("/api/v1/media/folders")
    def api_media_folders():
        """Return top-level folder tree from indexed files."""
        parent = request.args.get("parent", "")
        depth = int(request.args.get("depth", 1))

        if not parent:
            # Return library root paths
            libs = db.get_libraries()
            folders = []
            for lib in libs:
                count = db.conn.execute(
                    "SELECT COUNT(*) as cnt FROM files WHERE library_id = ?", (lib["id"],)
                ).fetchone()["cnt"]
                folders.append({"path": lib["path"], "name": lib["name"], "count": count})
            return jsonify({"folders": folders})

        # List immediate subdirectories under parent
        # Use Python to extract unique subdirs — more reliable than SQL string ops across OS path separators
        parent_normalized = parent.replace("\\", "/").rstrip("/") + "/"
        parent_len = len(parent_normalized)
        rows = db.conn.execute(
            "SELECT path FROM files WHERE path LIKE ? LIMIT 50000",
            (f"{parent}%",),
        ).fetchall()

        subdirs: dict[str, int] = {}
        file_count = 0
        for r in rows:
            rel = r["path"].replace("\\", "/")[parent_len:]
            sep = rel.find("/")
            if sep == -1:
                file_count += 1
            else:
                subdir = rel[:sep]
                subdirs[subdir] = subdirs.get(subdir, 0) + 1

        folders = [{"path": f"{parent_normalized}{name}", "name": name, "count": count}
                   for name, count in sorted(subdirs.items())]
        return jsonify({"folders": folders, "file_count": file_count})

    @app.route("/api/v1/media/<int:media_id>/describe", methods=["POST"])
    def api_media_describe(media_id: int):
        f = db.get_file_by_id(media_id)
        if not f:
            return jsonify({"error": "Not found"}), 404
        # Queue AI description — this would trigger the describe module
        return jsonify({"status": "queued", "file_id": media_id})

    # ----- Sprite / Preview API -----

    @app.route("/api/v1/media/<int:media_id>/sprite")
    def api_media_sprite(media_id: int):
        f = db.get_file_by_id(media_id)
        if not f or not f.get("sprite_path"):
            return jsonify({"error": "No sprite"}), 404
        return send_file(f["sprite_path"])

    @app.route("/api/v1/media/<int:media_id>/sprite/meta")
    def api_media_sprite_meta(media_id: int):
        """Return sprite metadata, generating on-demand if needed."""
        row = db.conn.execute(
            "SELECT * FROM sprites WHERE file_id = ?", (media_id,)
        ).fetchone()
        if row:
            r = dict(row)
            # Convert DB row to client format with URLs
            sprite_name = Path(r.get("sprite_path", "")).name
            return jsonify({
                "spriteUrl": f"/sprites/{sprite_name}",
                "posterUrl": f"/api/v1/media/{media_id}/thumbnail",
                "frameWidth": r.get("frame_width", 160),
                "frameHeight": r.get("frame_height", 90),
                "columns": r.get("columns", 5),
                "rows": r.get("rows", 2),
                "totalFrames": (r.get("columns", 5) or 5) * (r.get("rows", 2) or 2),
                "intervalSeconds": r.get("interval_seconds", 2),
            })

        # If cached_only flag set, don't generate — return 404
        if request.args.get("cached_only"):
            return jsonify({"error": "No sprite cached"}), 404

        # On-demand sprite generation for videos
        f = db.get_file_by_id(media_id)
        if not f or not (f.get("mime_type") or "").startswith("video/"):
            return jsonify({"error": "Not a video"}), 404
        if not os.path.exists(f["path"]):
            return jsonify({"error": "File not found"}), 404

        try:
            from .video_thumbs import generate_sprite_sheet, SpriteConfig
            sprite_config = SpriteConfig(frame_width=160, frame_height=90, columns=5, max_frames=10)
            meta = generate_sprite_sheet(f["path"], str(cache.cache_dir), sprite_config)

            # Store in DB for next time
            with db._lock:
                db.conn.execute(
                    "INSERT OR REPLACE INTO sprites (file_id, sprite_path, frame_width, frame_height, columns, rows, interval_seconds) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (media_id, str(cache.sprites_dir / f"{Path(f['path']).stem}_sprite.jpg"),
                     meta["frameWidth"], meta["frameHeight"], meta["columns"], meta["rows"], meta["intervalSeconds"]),
                )
                db.conn.commit()
            return jsonify(meta)
        except Exception as e:
            log.debug("Sprite generation failed for %d: %s", media_id, e)
            return jsonify({"error": str(e)}), 500

    # ----- Face Detection API (/api/v1/faces) -----

    @app.route("/api/v1/faces/persons")
    def api_faces_persons():
        rows = db.conn.execute(
            "SELECT person_name, COUNT(*) as match_count "
            "FROM matches GROUP BY person_name ORDER BY match_count DESC"
        ).fetchall()
        return jsonify({"persons": [dict(r) for r in rows]})

    @app.route("/api/v1/faces/persons/<name>")
    def api_faces_person_detail(name: str):
        rows = db.conn.execute(
            "SELECT * FROM matches WHERE person_name = ? ORDER BY confidence DESC",
            (name,),
        ).fetchall()
        return jsonify({"person": name, "matches": [dict(r) for r in rows], "total": len(rows)})

    @app.route("/api/v1/faces/matches")
    def api_faces_matches():
        page = int(request.args.get("page", 1))
        limit = int(request.args.get("limit", 50))
        offset = (page - 1) * limit
        rows = db.conn.execute(
            "SELECT * FROM matches ORDER BY confidence DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        total = db.conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
        return jsonify({"items": [dict(r) for r in rows], "total": total, "page": page})

    @app.route("/api/v1/faces/scan", methods=["GET"])
    def api_faces_scan_status():
        row = db.conn.execute(
            "SELECT * FROM scan_jobs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return jsonify(dict(row) if row else {"status": "no_scans"})

    @app.route("/api/v1/faces/settings", methods=["GET"])
    def api_faces_settings():
        return jsonify({
            "model": config.recognition.model,
            "threshold": config.recognition.threshold,
            "det_size": list(config.recognition.det_size),
        })

    @app.route("/api/v1/faces/persons/<name>", methods=["DELETE"])
    def api_faces_delete_person(name: str):
        """Delete a person and all their matches."""
        with db._lock:
            db.conn.execute("DELETE FROM matches WHERE person_name = ?", (name,))
            db.conn.execute("DELETE FROM persons WHERE name = ?", (name,))
            db.conn.commit()
        return jsonify({"ok": True, "deleted": name})

    @app.route("/api/v1/faces/persons", methods=["POST"])
    def api_faces_add_person():
        """Add a new person."""
        data = request.get_json() or {}
        name = data.get("name", "").strip()
        if not name:
            return jsonify({"error": "Name required"}), 400
        db.ensure_person(name)
        return jsonify({"ok": True, "name": name}), 201

    # ----- IPTV API (/api/v1/iptv) -----

    @app.route("/api/v1/iptv/playlists")
    def api_iptv_playlists():
        rows = db.conn.execute("SELECT * FROM iptv_playlists ORDER BY name").fetchall()
        return jsonify({"playlists": [dict(r) for r in rows]})

    @app.route("/api/v1/iptv/playlists", methods=["POST"])
    def api_iptv_add_playlist():
        data = request.get_json() or {}
        from .iptv.playlist_manager import PlaylistManager
        pm = PlaylistManager(db)
        pid = pm.add_playlist(data["url"], name=data.get("name"))
        pm.refresh_playlist(pid)
        return jsonify({"id": pid}), 201

    @app.route("/api/v1/iptv/playlists/<int:pid>", methods=["DELETE"])
    def api_iptv_delete_playlist(pid: int):
        with db._lock:
            db.conn.execute("DELETE FROM iptv_channels WHERE playlist_id = ?", (pid,))
            db.conn.execute("DELETE FROM iptv_playlists WHERE id = ?", (pid,))
            db.conn.commit()
        return jsonify({"ok": True})

    @app.route("/api/v1/iptv/playlists/<int:pid>/refresh", methods=["POST"])
    def api_iptv_refresh_playlist(pid: int):
        from .iptv.playlist_manager import PlaylistManager
        pm = PlaylistManager(db)
        count = pm.refresh_playlist(pid)
        return jsonify({"channel_count": count})

    @app.route("/api/v1/iptv/channels")
    def api_iptv_channels():
        from .iptv.channel_manager import ChannelManager
        cm = ChannelManager(db)
        channels = cm.get_channels(
            playlist_id=request.args.get("playlist_id", type=int),
            group=request.args.get("group"),
            search=request.args.get("q"),
            favorites_only=request.args.get("favorites") == "true",
            limit=int(request.args.get("limit", 100)),
            offset=int(request.args.get("offset", 0)),
        )
        return jsonify({"channels": channels})

    @app.route("/api/v1/iptv/channels/favorites")
    def api_iptv_favorites():
        from .iptv.channel_manager import ChannelManager
        cm = ChannelManager(db)
        return jsonify({"channels": cm.get_channels(favorites_only=True)})

    @app.route("/api/v1/iptv/channels/<int:cid>")
    def api_iptv_channel_detail(cid: int):
        row = db.conn.execute("SELECT * FROM iptv_channels WHERE id = ?", (cid,)).fetchone()
        if not row:
            return jsonify({"error": "Not found"}), 404
        return jsonify(dict(row))

    @app.route("/api/v1/iptv/channels/<int:cid>/stream")
    def api_iptv_channel_stream(cid: int):
        row = db.conn.execute("SELECT url FROM iptv_channels WHERE id = ?", (cid,)).fetchone()
        if not row:
            return jsonify({"error": "Not found"}), 404
        # Proxy the stream through
        from .iptv.stream_proxy import StreamProxy
        sp = StreamProxy(str(cache.cache_dir))
        return Response(sp.proxy_hls(row["url"]), mimetype="video/MP2T")

    @app.route("/api/v1/iptv/channels/<int:cid>/favorite", methods=["PUT"])
    def api_iptv_toggle_favorite(cid: int):
        from .iptv.channel_manager import ChannelManager
        cm = ChannelManager(db)
        new_state = cm.toggle_favorite(cid)
        return jsonify({"is_favorite": new_state})

    @app.route("/api/v1/iptv/channels/groups")
    def api_iptv_groups():
        from .iptv.channel_manager import ChannelManager
        cm = ChannelManager(db)
        return jsonify({"groups": cm.get_groups()})

    @app.route("/api/v1/iptv/channels/search")
    def api_iptv_search_channels():
        from .iptv.channel_manager import ChannelManager
        cm = ChannelManager(db)
        return jsonify({"channels": cm.get_channels(search=request.args.get("q", ""))})

    # Custom streams
    @app.route("/api/v1/iptv/streams")
    def api_iptv_streams():
        from .iptv.channel_manager import ChannelManager
        cm = ChannelManager(db)
        return jsonify({"streams": cm.get_custom_streams()})

    @app.route("/api/v1/iptv/streams", methods=["POST"])
    def api_iptv_add_stream():
        data = request.get_json() or {}
        from .iptv.channel_manager import ChannelManager
        cm = ChannelManager(db)
        sid = cm.add_custom_stream(data["name"], data["url"], data.get("category"))
        return jsonify({"id": sid}), 201

    @app.route("/api/v1/iptv/streams/<int:sid>", methods=["DELETE"])
    def api_iptv_delete_stream(sid: int):
        with db._lock:
            db.conn.execute("DELETE FROM custom_streams WHERE id = ?", (sid,))
            db.conn.commit()
        return jsonify({"ok": True})

    # EPG
    @app.route("/api/v1/iptv/epg")
    def api_iptv_epg():
        channel_id = request.args.get("channel_id")
        date = request.args.get("date")  # YYYY-MM-DD
        limit = int(request.args.get("limit", 200))

        query = "SELECT * FROM epg_programs WHERE 1=1"
        params: list[Any] = []
        if channel_id:
            query += " AND channel_id = ?"
            params.append(channel_id)
        if date:
            query += " AND start_time >= ? AND start_time < date(?, '+1 day')"
            params.extend([date, date])
        query += " ORDER BY start_time LIMIT ?"
        params.append(limit)

        rows = db.conn.execute(query, params).fetchall()
        return jsonify({"programs": [dict(r) for r in rows]})

    @app.route("/api/v1/iptv/epg/now")
    def api_iptv_epg_now():
        rows = db.conn.execute(
            "SELECT * FROM epg_programs "
            "WHERE start_time <= datetime('now') AND end_time > datetime('now') "
            "ORDER BY channel_id"
        ).fetchall()
        return jsonify({"programs": [dict(r) for r in rows]})

    @app.route("/api/v1/iptv/epg/sources")
    def api_iptv_epg_sources():
        rows = db.conn.execute("SELECT * FROM epg_sources ORDER BY name").fetchall()
        return jsonify({"sources": [dict(r) for r in rows]})

    @app.route("/api/v1/iptv/epg/sources", methods=["POST"])
    def api_iptv_add_epg_source():
        data = request.get_json() or {}
        with db._lock:
            cur = db.conn.execute(
                "INSERT OR IGNORE INTO epg_sources (url, name) VALUES (?, ?)",
                (data["url"], data.get("name", data["url"])),
            )
            db.conn.commit()
        return jsonify({"id": cur.lastrowid}), 201

    @app.route("/api/v1/iptv/epg/refresh", methods=["POST"])
    def api_iptv_epg_refresh():
        from .iptv.epg_service import EPGService
        epg = EPGService(db)
        epg.refresh_all()
        return jsonify({"ok": True})

    # Recordings
    @app.route("/api/v1/iptv/recordings")
    def api_iptv_recordings():
        rows = db.conn.execute("SELECT * FROM recordings ORDER BY created_at DESC").fetchall()
        return jsonify({"recordings": [dict(r) for r in rows]})

    @app.route("/api/v1/iptv/recordings", methods=["POST"])
    def api_iptv_start_recording():
        data = request.get_json() or {}
        from .iptv.recorder import Recorder
        rec = Recorder(db, config.iptv.recording_dir)
        rid = rec.schedule_recording(
            channel_id=data["channel_id"],
            stream_url=data["stream_url"],
            title=data.get("title", "Recording"),
            start=data.get("start", datetime.utcnow().isoformat()),
            end=data.get("end", ""),
        )
        if data.get("start_now"):
            rec.start_recording(rid)
        return jsonify({"id": rid}), 201

    @app.route("/api/v1/iptv/recordings/<int:rid>", methods=["DELETE"])
    def api_iptv_delete_recording(rid: int):
        with db._lock:
            db.conn.execute("DELETE FROM recordings WHERE id = ?", (rid,))
            db.conn.commit()
        return jsonify({"ok": True})

    @app.route("/api/v1/iptv/recordings/<int:rid>/stop", methods=["PUT"])
    def api_iptv_stop_recording(rid: int):
        from .iptv.recorder import Recorder
        rec = Recorder(db, config.iptv.recording_dir)
        rec.stop_recording(rid)
        return jsonify({"ok": True})

    # ----- Cache API (/api/v1/cache) -----

    @app.route("/api/v1/cache/stats")
    def api_cache_stats():
        return jsonify(cache.stats())

    @app.route("/api/v1/cache/settings", methods=["PUT"])
    def api_cache_settings():
        data = request.get_json() or {}
        if "limit_gb" in data:
            cache.limit_bytes = int(data["limit_gb"] * 1024**3)
        if "enabled" in data:
            cache.enabled = data["enabled"]
        return jsonify(cache.stats())

    @app.route("/api/v1/cache/clear", methods=["POST"])
    def api_cache_clear():
        freed = cache.clear()
        return jsonify({"freed_bytes": freed})

    @app.route("/api/v1/cache/move", methods=["POST"])
    def api_cache_move():
        data = request.get_json() or {}
        new_path = data.get("path")
        if not new_path:
            return jsonify({"error": "path required"}), 400
        cache.move_to(new_path)
        return jsonify(cache.stats())

    # ----- Fleet API (/api/v1/fleet) -----

    @app.route("/api/v1/fleet/status")
    def api_fleet_status():
        nodes = []
        for w in config.workers:
            nodes.append({
                "name": w.name,
                "host": w.host,
                "gpu": w.gpu,
                "ssh_alias": w.ssh_alias,
                "online": True,  # TODO: actual health check
            })
        return jsonify({"nodes": nodes})

    @app.route("/api/v1/fleet/nodes")
    def api_fleet_nodes():
        return jsonify({"nodes": [
            {"name": w.name, "host": w.host, "gpu": w.gpu}
            for w in config.workers
        ]})

    # ----- AI API (/api/v1/ai) -----

    @app.route("/api/v1/ai/status")
    def api_ai_status():
        return jsonify({
            "enabled": config.ai.enabled,
            "model": config.ai.model,
            "endpoint": config.ai.endpoint,
        })

    @app.route("/api/v1/ai/config", methods=["GET"])
    def api_ai_config():
        return jsonify({
            "model": config.ai.model,
            "endpoint": config.ai.endpoint,
            "enabled": config.ai.enabled,
            "batch_size": config.ai.batch_size,
        })

    # ----- Settings API (/api/v1/settings) -----

    @app.route("/api/v1/settings")
    def api_settings():
        return jsonify(db.get_all_settings())

    @app.route("/api/v1/settings", methods=["PUT"])
    def api_settings_update():
        data = request.get_json() or {}
        for key, value in data.items():
            db.set_setting(key, json.dumps(value) if not isinstance(value, str) else value)
        return jsonify(db.get_all_settings())

    @app.route("/api/v1/settings/theme", methods=["GET"])
    def api_settings_theme():
        theme = db.get_setting("theme", "system")
        return jsonify({"theme": theme})

    @app.route("/api/v1/settings/theme", methods=["PUT"])
    def api_settings_theme_set():
        data = request.get_json() or {}
        db.set_setting("theme", data.get("theme", "system"))
        return jsonify({"theme": db.get_setting("theme")})

    @app.route("/api/v1/settings/preview-tiles", methods=["GET"])
    def api_preview_tiles_get():
        raw = db.get_setting("preview_tiles")
        if raw:
            return jsonify(json.loads(raw))
        return jsonify(PREVIEW_TILES_DEFAULTS)

    @app.route("/api/v1/settings/preview-tiles", methods=["PUT"])
    def api_preview_tiles_set():
        data = request.get_json() or {}
        db.set_setting("preview_tiles", json.dumps(data))
        return jsonify(data)

    @app.route("/api/v1/settings/libraries")
    def api_settings_libraries():
        return jsonify({"libraries": db.get_libraries()})

    @app.route("/api/v1/settings/libraries", methods=["POST"])
    def api_settings_add_library():
        data = request.get_json() or {}
        lid = db.add_library(
            name=data["name"],
            source_type=data["type"],
            path=data["path"],
            scan_interval_hours=data.get("scan_interval_hours", 24),
        )
        return jsonify({"id": lid}), 201

    @app.route("/api/v1/settings/libraries/<int:lid>", methods=["DELETE"])
    def api_settings_remove_library(lid: int):
        db.remove_library(lid)
        return jsonify({"ok": True})

    # ----- Library scan trigger -----

    @app.route("/api/v1/settings/libraries/<int:lid>/scan", methods=["POST"])
    def api_settings_scan_library(lid: int):
        """Trigger a background scan of a specific library."""
        import threading
        lib = db.conn.execute("SELECT * FROM libraries WHERE id = ?", (lid,)).fetchone()
        if not lib:
            return jsonify({"error": "Library not found"}), 404
        if lib["type"] == "local":
            def _scan():
                from .sources.local import LocalSource
                source = LocalSource(lid, lib["path"], db, exclude_dirs=set(config.exclude_dirs or []))
                count = source.scan()
                log.info("Library %d scan complete: %d files", lid, count)
            threading.Thread(target=_scan, daemon=True).start()
            return jsonify({"status": "scanning", "library_id": lid})
        return jsonify({"error": f"Scan not supported for type '{lib['type']}' yet"}), 400

    # ----- Debug API (/api/v1/debug) -----

    @app.route("/api/v1/debug/file/<int:file_id>")
    def api_debug_file(file_id: int):
        """Diagnose a specific file: DB record, filesystem check, serve test."""
        f = db.get_file_by_id(file_id)
        if not f:
            return jsonify({"error": "Not found in DB"}), 404
        path = f["path"]
        exists = os.path.exists(path)
        real_size = os.path.getsize(path) if exists else 0
        import mimetypes as mt
        guessed_mime, _ = mt.guess_type(path)
        return jsonify({
            "db_record": f,
            "filesystem": {
                "exists": exists,
                "real_size": real_size,
                "size_matches": real_size == (f.get("size") or 0),
                "guessed_mime": guessed_mime,
            },
            "urls": {
                "serve": f"/file?path={path}",
                "download": f"/api/v1/media/{file_id}/download",
                "detail": f"/api/v1/media/{file_id}",
            },
        })

    @app.route("/api/v1/system/browse-folder")
    def api_browse_folder():
        """List drives and browse server-side directories."""
        path = request.args.get("path", "")

        if not path:
            # Return available drives (Windows) or root dirs (Unix)
            import platform
            drives = []
            if platform.system() == "Windows":
                import string
                for letter in string.ascii_uppercase:
                    drive = f"{letter}:\\"
                    if os.path.exists(drive):
                        try:
                            total = os.statvfs(drive).f_frsize * os.statvfs(drive).f_blocks if hasattr(os, "statvfs") else 0
                        except Exception:
                            total = 0
                        drives.append({"name": f"{letter}:", "path": drive, "type": "drive"})
            else:
                drives = [{"name": "/", "path": "/", "type": "root"}]
                for d in ["/home", "/mnt", "/media", "/Volumes"]:
                    if os.path.isdir(d):
                        drives.append({"name": d.split("/")[-1], "path": d, "type": "mount"})
            return jsonify({"items": drives, "current": ""})

        # List subdirectories of the given path
        if not os.path.isdir(path):
            return jsonify({"error": "Not a directory", "path": path}), 404

        items = []
        try:
            for entry in sorted(os.scandir(path), key=lambda e: e.name.lower()):
                if entry.is_dir(follow_symlinks=False):
                    # Skip hidden and system dirs
                    if entry.name.startswith(".") or entry.name.startswith("$"):
                        continue
                    items.append({"name": entry.name, "path": entry.path, "type": "folder"})
        except PermissionError:
            pass

        return jsonify({"items": items, "current": path})

    @app.route("/api/v1/debug/stats")
    def api_debug_stats():
        """Database statistics for debugging."""
        ext_counts = db.conn.execute(
            "SELECT extension, COUNT(*) as c FROM files GROUP BY extension ORDER BY c DESC LIMIT 30"
        ).fetchall()
        mime_counts = db.conn.execute(
            "SELECT mime_type, COUNT(*) as c FROM files GROUP BY mime_type ORDER BY c DESC LIMIT 30"
        ).fetchall()
        total = db.get_file_count()
        schema_ver = db.conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
        return jsonify({
            "total_files": total,
            "schema_version": schema_ver,
            "by_extension": {r["extension"]: r["c"] for r in ext_counts},
            "by_mime": {r["mime_type"]: r["c"] for r in mime_counts},
            "libraries": db.get_libraries(),
            "cache": cache.stats(),
        })

    @app.route("/api/v1/debug/test-file")
    def api_debug_test_file():
        """Test serving a file by path, returns headers and size info."""
        path = request.args.get("path", "")
        if not path:
            return jsonify({"error": "path param required"}), 400
        exists = os.path.exists(path)
        if not exists:
            return jsonify({"error": "File not found", "path": path}), 404
        size = os.path.getsize(path)
        import mimetypes as mt
        mime, _ = mt.guess_type(path)
        readable = os.access(path, os.R_OK)
        return jsonify({
            "path": path,
            "exists": True,
            "size": size,
            "mime": mime,
            "readable": readable,
            "serve_url": f"/file?path={path}",
        })

    # ----- Sprite / static file serving -----

    @app.route("/sprites/<path:filename>")
    def serve_sprites(filename: str):
        return send_from_directory(str(cache.sprites_dir), filename)

    return app


def _bearer(req: Any) -> str | None:
    auth = req.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


APP_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Face Detection Dashboard</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0f0f0f;color:#e0e0e0;display:flex;height:100vh;overflow:hidden}
.sidebar{width:220px;min-width:220px;background:#111;border-right:1px solid #222;display:flex;flex-direction:column;height:100vh}
.sidebar .logo{padding:1.2rem 1rem;font-size:1.1rem;font-weight:700;color:#fff;border-bottom:1px solid #222}
.sidebar nav{flex:1;padding:.5rem 0}
.sidebar nav a{display:flex;align-items:center;gap:.6rem;padding:.7rem 1rem;color:#888;text-decoration:none;font-size:.85rem;border-left:3px solid transparent;transition:all .15s}
.sidebar nav a:hover{color:#ccc;background:#1a1a1a}
.sidebar nav a.active{color:#4fc3f7;border-left-color:#4fc3f7;background:#1a1a2a}
.sidebar nav a .icon{font-size:1.1rem;width:20px;text-align:center}
.sidebar .sidebar-footer{padding:.8rem 1rem;border-top:1px solid #222;font-size:.7rem;color:#444}
.main{flex:1;display:flex;flex-direction:column;overflow:hidden}
.header{padding:1rem 1.5rem;border-bottom:1px solid #222;display:flex;justify-content:space-between;align-items:center}
.header h1{font-size:1.3rem;color:#fff}
.stats-bar{display:flex;gap:1.5rem;font-size:.8rem;color:#888}
.stats-bar span.val{color:#4fc3f7;font-weight:600}
.controls{padding:.7rem 1.5rem;display:flex;gap:.8rem;align-items:center;border-bottom:1px solid #1a1a1a}
.controls select,.controls button{background:#1a1a1a;color:#e0e0e0;border:1px solid #333;padding:.35rem .7rem;border-radius:6px;cursor:pointer;font-size:.8rem}
.controls button:hover{border-color:#4fc3f7}
.controls button.active{background:#4fc3f7;color:#000;border-color:#4fc3f7}
.scroll-area{flex:1;overflow-y:auto;overflow-x:hidden}
.date-group{padding:0 1.5rem}
.date-title{padding:.8rem 0 .4rem;color:#4fc3f7;font-size:1rem;font-weight:600;border-bottom:1px solid #222;margin-bottom:.6rem;position:sticky;top:0;background:#0f0f0f;z-index:10}
.date-title .count{color:#666;font-size:.75rem;font-weight:400;margin-left:.5rem}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:.6rem;padding-bottom:.8rem}
.card{background:#1a1a1a;border-radius:8px;overflow:hidden;border:1px solid #2a2a2a;cursor:pointer;transition:border-color .2s;position:relative}
.card:hover{border-color:#4fc3f7}
.card img,.card video{width:100%;height:150px;object-fit:cover;background:#111}
.card .no-thumb{width:100%;height:150px;background:#111;display:flex;align-items:center;justify-content:center;color:#444;font-size:.75rem}
.card .type-badge{position:absolute;top:6px;left:6px;padding:2px 6px;border-radius:3px;font-size:.6rem;font-weight:700;text-transform:uppercase}
.card .type-badge.video{background:#e65100;color:#fff}
.card .type-badge.image{background:#004d40;color:#80cbc4}
.card .play-overlay{position:absolute;top:50%;left:50%;transform:translate(-50%,-70%);width:44px;height:44px;background:rgba(0,0,0,.6);border-radius:50%;display:flex;align-items:center;justify-content:center;pointer-events:none}
.card .play-overlay:after{content:'';border-style:solid;border-width:10px 0 10px 18px;border-color:transparent transparent transparent #fff;margin-left:3px}
.card .time-badge{position:absolute;top:6px;right:6px;padding:2px 6px;border-radius:3px;font-size:.6rem;background:rgba(0,0,0,.7);color:#ccc}
.card .info{padding:.5rem;font-size:.75rem}
.card .info .name{color:#ccc;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.card .info .meta{color:#666;font-size:.65rem;margin-top:.15rem}
.card .info .desc{color:#888;font-size:.65rem;margin-top:.2rem;line-height:1.3;max-height:36px;overflow:hidden}
.badge{display:inline-block;padding:1px 5px;border-radius:3px;font-size:.6rem;font-weight:600}
.badge-person{background:#1a237e;color:#9fa8da}
.conf-high{color:#a5d6a7}.conf-mid{color:#ffcc80}.conf-low{color:#ef9a9a}
.lightbox{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.95);z-index:1000;justify-content:center;align-items:center;flex-direction:column}
.lightbox.active{display:flex}
.lightbox img,.lightbox video{max-width:90vw;max-height:72vh;object-fit:contain;border-radius:8px}
.lightbox .lb-info{color:#ccc;margin-top:.8rem;text-align:center;max-width:75vw}
.lightbox .lb-info .lb-name{font-size:.85rem}
.lightbox .lb-info .lb-path{color:#666;font-size:.7rem;margin-top:.2rem;word-break:break-all}
.lightbox .lb-info .lb-desc{color:#999;font-size:.75rem;margin-top:.4rem;max-height:70px;overflow-y:auto;line-height:1.4}
.lightbox .lb-close{position:absolute;top:1.2rem;right:1.5rem;color:#888;font-size:2rem;cursor:pointer}
.lightbox .lb-close:hover{color:#fff}
.lb-nav{position:absolute;top:50%;transform:translateY(-50%);color:#555;font-size:3rem;cursor:pointer;user-select:none;padding:0 1.2rem}
.lb-nav:hover{color:#fff}
.lb-prev{left:0}.lb-next{right:0}
.loading{text-align:center;padding:3rem;color:#666}
</style>
</head>
<body>
<div class="sidebar">
    <div class="logo">FaceDetect</div>
    <nav>
        <a href="#" class="active"><span class="icon">&#128100;</span> People</a>
        <a href="#" style="opacity:.4;pointer-events:none"><span class="icon">&#128202;</span> Analytics</a>
        <a href="#" style="opacity:.4;pointer-events:none"><span class="icon">&#9881;</span> Settings</a>
    </nav>
    <div class="sidebar-footer" id="activity-status" style="line-height:1.6">
        <div id="scan-status" style="color:#666">Scan: checking...</div>
        <div id="desc-status" style="color:#666">Descriptions: ...</div>
        <div style="margin-top:4px;color:#444">v0.1.0 &mdash; Local AI Face Recognition</div>
    </div>
</div>
<div class="main">
    <div class="header">
        <h1>People</h1>
        <div class="stats-bar" id="stats"></div>
    </div>
    <div class="controls">
        <select id="personFilter"></select>
        <button id="btnByDate" class="active">By Date</button>
        <button id="btnByConf">By Confidence</button>
        <span id="totalCount" style="color:#666;font-size:.8rem;margin-left:auto"></span>
    </div>
    <div class="scroll-area" id="content"></div>
</div>
<div class="lightbox" id="lightbox">
    <span class="lb-close">&times;</span>
    <span class="lb-nav lb-prev">&#8249;</span>
    <span class="lb-nav lb-next">&#8250;</span>
    <img id="lb-img" src="" style="display:none">
    <video id="lb-vid" controls loop style="display:none"></video>
    <div class="lb-info">
        <div class="lb-name" id="lb-name"></div>
        <div class="lb-path" id="lb-path"></div>
        <div class="lb-desc" id="lb-desc"></div>
    </div>
</div>
<script>
let view='date',currentPerson='',allCards=[],lbIdx=-1;
const $=id=>document.getElementById(id);

function fmtTime(s){if(s==null)return'';const m=Math.floor(s/60),sec=Math.floor(s%60);return m+':'+String(sec).padStart(2,'0')}

async function loadStats(){
    const d=await(await fetch('/api/stats')).json();
    const s=d.stats;const el=$('stats');
    while(el.firstChild)el.removeChild(el.firstChild);
    const items=['Scanned: '+(s.processed_files||0),'Matches: '+(s.matched_files||0),'Described: '+d.descriptions_done];
    d.persons.forEach(p=>items.push(p.name+': '+p.count));
    items.forEach((t,i)=>{
        if(i>0){const sp=document.createElement('span');sp.textContent=' | ';el.appendChild(sp)}
        const sp=document.createElement('span');sp.className='val';sp.textContent=t;el.appendChild(sp);
    });
    const sel=$('personFilter');const prev=sel.value;
    while(sel.firstChild)sel.removeChild(sel.firstChild);
    const opt0=document.createElement('option');opt0.value='';opt0.textContent='All Persons';sel.appendChild(opt0);
    d.persons.forEach(p=>{const o=document.createElement('option');o.value=p.name;o.textContent=p.name+' ('+p.count+')';if(p.name===prev)o.selected=true;sel.appendChild(o)});
}

function setView(v){view=v;$('btnByDate').className=v==='date'?'active':'';$('btnByConf').className=v==='confidence'?'active':'';loadContent()}
$('btnByDate').onclick=()=>setView('date');
$('btnByConf').onclick=()=>setView('confidence');
$('personFilter').onchange=e=>{currentPerson=e.target.value;loadContent()};

function formatDate(iso){
    if(!iso||iso==='Unknown Date')return'Unknown Date';
    try{return new Date(iso+'T00:00:00').toLocaleDateString(undefined,{weekday:'long',year:'numeric',month:'long',day:'numeric'})}
    catch(e){return iso}
}

function makeCard(m,idx){
    const card=document.createElement('div');card.className='card';card.dataset.idx=idx;
    const isVideo=m.file_type==='video';
    if(m.thumbnail){
        const img=document.createElement('img');img.loading='lazy';
        if(isVideo&&m.video_thumb){img.src='/vthumb/'+m.video_thumb}
        else{img.src='/thumb/'+m.thumbnail}
        card.appendChild(img);
    }else{const d=document.createElement('div');d.className='no-thumb';d.textContent=isVideo?'Video':'No thumbnail';card.appendChild(d)}
    if(isVideo){const po=document.createElement('div');po.className='play-overlay';card.appendChild(po)}
    const tb=document.createElement('span');tb.className='type-badge '+(isVideo?'video':'image');tb.textContent=isVideo?'VIDEO':'IMAGE';card.appendChild(tb);
    if(isVideo&&m.timestamp_start!=null){
        const tm=document.createElement('span');tm.className='time-badge';
        tm.textContent=fmtTime(m.timestamp_start)+(m.timestamp_end!=null?' - '+fmtTime(m.timestamp_end):'');
        card.appendChild(tm);
    }
    const info=document.createElement('div');info.className='info';
    const nm=document.createElement('div');nm.className='name';nm.textContent=m.file_name;info.appendChild(nm);
    const meta=document.createElement('div');meta.className='meta';
    const badge=document.createElement('span');badge.className='badge badge-person';badge.textContent=m.person_name;meta.appendChild(badge);
    const conf=document.createElement('span');
    conf.className=m.confidence>=.5?'conf-high':m.confidence>=.4?'conf-mid':'conf-low';
    conf.textContent=' '+(m.confidence*100).toFixed(1)+'%';meta.appendChild(conf);
    info.appendChild(meta);
    if(m.description){const desc=document.createElement('div');desc.className='desc';desc.textContent=m.description.substring(0,100)+'...';info.appendChild(desc)}
    card.appendChild(info);
    card.onclick=()=>openLB(idx);
    return card;
}

async function loadContent(){
    const el=$('content');el.textContent='Loading...';
    if(view==='date')await loadByDate(el);else await loadByConf(el);
}

async function loadByDate(el){
    const url='/api/matches/by-date'+(currentPerson?'?person='+encodeURIComponent(currentPerson):'');
    const d=await(await fetch(url)).json();
    allCards=[];el.textContent='';
    let totalM=0;
    d.groups.forEach(g=>{
        const grp=document.createElement('div');grp.className='date-group';
        const title=document.createElement('div');title.className='date-title';
        title.textContent=formatDate(g.date);
        const cnt=document.createElement('span');cnt.className='count';cnt.textContent=g.count+' item(s)';title.appendChild(cnt);
        grp.appendChild(title);
        const grid=document.createElement('div');grid.className='grid';
        g.matches.forEach(m=>{const idx=allCards.length;allCards.push(m);grid.appendChild(makeCard(m,idx));totalM++});
        grp.appendChild(grid);el.appendChild(grp);
    });
    $('totalCount').textContent=totalM+' matches across '+d.total_dates+' dates';
}

async function loadByConf(el){
    const url='/api/matches?per_page=200'+(currentPerson?'&person='+encodeURIComponent(currentPerson):'');
    const d=await(await fetch(url)).json();
    allCards=d.matches;el.textContent='';
    $('totalCount').textContent=d.total+' total matches';
    const grp=document.createElement('div');grp.className='date-group';
    const grid=document.createElement('div');grid.className='grid';
    d.matches.forEach((m,i)=>grid.appendChild(makeCard(m,i)));
    grp.appendChild(grid);el.appendChild(grp);
}

function openLB(idx){
    lbIdx=idx;const m=allCards[idx];
    const isVideo=m.file_type==='video';
    const imgEl=$('lb-img');const vidEl=$('lb-vid');
    if(isVideo){
        imgEl.style.display='none';vidEl.style.display='block';
        vidEl.src='/file?path='+encodeURIComponent(m.file_path);vidEl.loop=true;
        if(m.timestamp_start!=null)vidEl.currentTime=m.timestamp_start;
        vidEl.play().catch(()=>{});
    }else{
        vidEl.style.display='none';vidEl.pause();vidEl.src='';
        imgEl.style.display='block';imgEl.src='/file?path='+encodeURIComponent(m.file_path);
    }
    $('lb-name').textContent=m.file_name+' \u2014 '+m.person_name+(isVideo&&m.timestamp_start!=null?' ['+fmtTime(m.timestamp_start)+' - '+fmtTime(m.timestamp_end)+']':'');
    $('lb-path').textContent=m.file_path;
    $('lb-desc').textContent=m.description||'';
    $('lightbox').classList.add('active');document.body.style.overflow='hidden';
}
function closeLB(e){
    if(e&&(e.target.classList.contains('lb-nav')||e.target.id==='lb-img'||e.target.id==='lb-vid'))return;
    $('lightbox').classList.remove('active');document.body.style.overflow='';lbIdx=-1;
    $('lb-vid').pause();$('lb-vid').src='';
}
function navLB(e,dir){e&&e.stopPropagation();const n=lbIdx+dir;if(n>=0&&n<allCards.length)openLB(n)}

$('lightbox').onclick=closeLB;
$('lightbox').querySelector('.lb-close').onclick=closeLB;
$('lightbox').querySelector('.lb-prev').onclick=e=>navLB(e,-1);
$('lightbox').querySelector('.lb-next').onclick=e=>navLB(e,1);
document.addEventListener('keydown',e=>{
    if(lbIdx===-1)return;
    if(e.key==='Escape')closeLB();
    else if(e.key==='ArrowLeft')navLB(null,-1);
    else if(e.key==='ArrowRight')navLB(null,1);
});

async function loadActivity(){
    try{
        const d=await(await fetch('/api/activity')).json();
        const scanEl=$('scan-status');const descEl=$('desc-status');
        if(d.scan_running){
            scanEl.style.color='#a5d6a7';
            if(d.scan_progress){scanEl.textContent='\u25CF Scan: '+d.scan_progress.done+'/'+d.scan_progress.total}
            else{scanEl.textContent='\u25CF Scan: running'}
        }else{scanEl.style.color='#666';scanEl.textContent='\u25CB Scan: idle'}
        const dp=d.describe_progress;
        if(dp.done<dp.total){descEl.style.color='#ffcc80';descEl.textContent='Desc: '+dp.done+'/'+dp.total}
        else{descEl.style.color='#a5d6a7';descEl.textContent='Desc: '+dp.done+'/'+dp.total+' \u2714'}
    }catch(e){$('scan-status').textContent='\u25CB Scan: unknown';$('scan-status').style.color='#666'}
}
setInterval(loadActivity,5000);loadActivity();

setInterval(loadStats,30000);
loadStats();loadContent();
</script>
</body>
</html>"""


def main():
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                        datefmt="%H:%M:%S")
    parser = argparse.ArgumentParser(description="Face Detection Web Dashboard")
    parser.add_argument("-c", "--config", default="config.yaml")
    parser.add_argument("-p", "--port", type=int, default=64531)
    args = parser.parse_args()

    config = load_config(args.config)
    app = create_webapp(config)
    log.info("Starting dashboard on http://localhost:%d", args.port)
    app.run(host="0.0.0.0", port=args.port, debug=False)


if __name__ == "__main__":
    main()
