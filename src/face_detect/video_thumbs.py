"""Generate full-frame video thumbnails for matched videos."""

import logging
import sqlite3
from pathlib import Path

import cv2

log = logging.getLogger(__name__)


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
