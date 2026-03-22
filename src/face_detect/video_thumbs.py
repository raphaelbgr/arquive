"""Generate full-frame video thumbnails and sprite sheets for video preview tiles.

Existing function ``generate_video_thumbnails`` is unchanged.  New functions
added for Arquive sprite sheet generation via FFmpeg subprocess.

Dependencies: cv2 (OpenCV), subprocess (FFmpeg)
"""

from __future__ import annotations

import json
import logging
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path

import cv2

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sprite sheet generation (Step 10 — Arquive extension)
# ---------------------------------------------------------------------------

@dataclass
class SpriteConfig:
    frame_width: int = 160
    frame_height: int = 90
    columns: int = 5
    max_frames: int = 20


def _get_video_duration(video_path: str) -> float:
    """Get video duration in seconds via ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
        ],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    return float(result.stdout.strip())


def generate_sprite_sheet(
    video_path: str,
    output_dir: str,
    config: SpriteConfig | None = None,
) -> dict:
    """Generate a sprite sheet and poster for a video file.

    Extracts evenly-spaced frames via FFmpeg and composites them into a
    grid image.  Returns sprite metadata dict.
    """
    if config is None:
        config = SpriteConfig()

    out = Path(output_dir) / "sprites"
    out.mkdir(parents=True, exist_ok=True)

    video_hash = Path(video_path).stem  # TODO: use proper content hash
    sprite_path = out / f"{video_hash}_sprite.jpg"
    poster_path = out / f"{video_hash}_poster.jpg"
    meta_path = out / f"{video_hash}_sprite.json"

    # Skip if already generated
    if sprite_path.exists() and poster_path.exists():
        if meta_path.exists():
            return json.loads(meta_path.read_text())

    duration = _get_video_duration(video_path)
    if duration <= 0:
        raise ValueError(f"Invalid duration for {video_path}")

    interval = max(1, int(duration / config.max_frames))
    total_frames = min(config.max_frames, max(1, int(duration / interval)))
    rows = -(-total_frames // config.columns)  # ceil division

    # Generate sprite sheet
    subprocess.run(
        [
            "ffmpeg", "-y", "-hwaccel", "cuda", "-i", video_path,
            "-vf", (
                f"fps=1/{interval},"
                f"scale={config.frame_width}:{config.frame_height},"
                f"tile={config.columns}x{rows}"
            ),
            "-frames:v", "1", "-q:v", "5",
            str(sprite_path),
        ],
        capture_output=True, timeout=120,
    )

    # Generate poster (first frame)
    subprocess.run(
        [
            "ffmpeg", "-y", "-hwaccel", "cuda", "-i", video_path,
            "-vframes", "1", "-q:v", "2",
            "-vf", f"scale={config.frame_width}:{config.frame_height}",
            str(poster_path),
        ],
        capture_output=True, timeout=30,
    )

    metadata = {
        "spriteUrl": f"/sprites/{video_hash}_sprite.jpg",
        "posterUrl": f"/sprites/{video_hash}_poster.jpg",
        "frameWidth": config.frame_width,
        "frameHeight": config.frame_height,
        "columns": config.columns,
        "rows": rows,
        "totalFrames": total_frames,
        "intervalSeconds": interval,
        "duration": duration,
    }

    meta_path.write_text(json.dumps(metadata, indent=2))
    log.info("Sprite sheet generated: %s (%d frames)", sprite_path, total_frames)
    return metadata


def compose_live_sprite(
    thumbnail_paths: list[str],
    output_path: str,
    frame_width: int = 160,
    frame_height: int = 90,
    columns: int = 5,
) -> None:
    """Composite individual frame captures into a single sprite sheet.

    Called on a 60-second timer to refresh live channel preview tiles.
    Uses Pillow for image compositing.
    """
    from PIL import Image

    rows = -(-len(thumbnail_paths) // columns)
    sheet = Image.new("RGB", (frame_width * columns, frame_height * rows), (0, 0, 0))

    for i, thumb_path in enumerate(thumbnail_paths):
        col = i % columns
        row = i // columns
        frame = Image.open(thumb_path).resize((frame_width, frame_height))
        sheet.paste(frame, (col * frame_width, row * frame_height))

    sheet.save(output_path, "JPEG", quality=80)
    log.info("Live sprite sheet generated: %s (%d frames)", output_path, len(thumbnail_paths))


# ---------------------------------------------------------------------------
# Original video thumbnail generation (unchanged)
# ---------------------------------------------------------------------------


def generate_video_thumbnails(db_path: str, output_dir: str, size: tuple = (320, 180)):
    """Generate full-frame thumbnails for all video matches.

    Extracts the frame at the match timestamp and saves as a JPEG.
    Saves the path in matches.thumbnail_video column.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    out = Path(output_dir) / "video_thumbs"
    out.mkdir(parents=True, exist_ok=True)

    rows = conn.execute("""
        SELECT DISTINCT file_path, timestamp_start, person_name
        FROM matches WHERE file_type = 'video'
        ORDER BY file_path, timestamp_start
    """).fetchall()

    total = len(rows)
    generated = 0
    skipped = 0
    failed = 0

    for i, row in enumerate(rows):
        file_path = row["file_path"]
        ts = row["timestamp_start"] or 0
        person = row["person_name"]

        stem = Path(file_path).stem
        thumb_name = f"{stem}_{ts:.1f}s.jpg"
        thumb_path = out / thumb_name

        if thumb_path.exists():
            skipped += 1
            continue

        try:
            cap = cv2.VideoCapture(file_path)
            if not cap.isOpened():
                failed += 1
                continue

            fps = cap.get(cv2.CAP_PROP_FPS) or 30
            frame_num = int(ts * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
            ret, frame = cap.read()
            cap.release()

            if not ret or frame is None:
                failed += 1
                continue

            # Resize to thumbnail size
            h, w = frame.shape[:2]
            target_w, target_h = size
            scale = max(target_w / w, target_h / h)
            new_w, new_h = int(w * scale), int(h * scale)
            resized = cv2.resize(frame, (new_w, new_h))

            # Center crop
            x_off = (new_w - target_w) // 2
            y_off = (new_h - target_h) // 2
            cropped = resized[y_off:y_off + target_h, x_off:x_off + target_w]

            cv2.imwrite(str(thumb_path), cropped, [cv2.IMWRITE_JPEG_QUALITY, 80])

            # Update DB with video thumbnail path
            conn.execute(
                "UPDATE matches SET thumbnail_path = ? WHERE file_path = ? AND person_name = ? AND timestamp_start = ?",
                (str(thumb_path), file_path, person, ts)
            )

            generated += 1
            if generated % 50 == 0:
                conn.commit()
                log.info("Generated %d/%d video thumbs (skipped %d, failed %d)",
                         generated, total, skipped, failed)

        except Exception as e:
            log.warning("Failed to generate thumb for %s @ %.1fs: %s", file_path, ts, e)
            failed += 1

    conn.commit()
    conn.close()
    log.info("Done: %d generated, %d skipped, %d failed out of %d video matches",
             generated, skipped, failed, total)


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                        datefmt="%H:%M:%S")
    parser = argparse.ArgumentParser(description="Generate video thumbnails")
    parser.add_argument("--db", default="./results/faces.db")
    parser.add_argument("--output", default="./results")
    args = parser.parse_args()
    generate_video_thumbnails(args.db, args.output)
