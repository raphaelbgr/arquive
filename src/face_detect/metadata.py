"""Unified metadata extraction for images, videos, audio, and documents.

Extracts EXIF data, codec info, GPS coordinates, document properties, etc.
into a flat dict suitable for storing in ``files.metadata_json``.

Extraction stack:
  - Images: Pillow/PIL (EXIF, dimensions, color space)
  - Video/Audio: ffprobe via subprocess (codec, bitrate, duration, HDR)
  - Documents: PyPDF2 (pages, author, encryption), python-docx (planned)

Dependencies: Pillow, subprocess (ffprobe), PyPDF2 (optional)
"""

from __future__ import annotations

import json
import logging
import mimetypes
import subprocess
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def extract_metadata(file_path: str) -> dict[str, Any]:
    """Extract all available metadata from a file.

    Returns a dict with standardised keys.  Missing fields are omitted
    rather than set to None — callers should use ``.get()``.
    """
    path = Path(file_path)
    if not path.exists():
        return {}

    mime, _ = mimetypes.guess_type(str(path))
    meta: dict[str, Any] = {
        "name": path.name,
        "extension": path.suffix.lower(),
        "size": path.stat().st_size,
        "mime_type": mime or "application/octet-stream",
    }

    if mime:
        if mime.startswith("image/"):
            meta.update(_extract_image(path))
        elif mime.startswith("video/"):
            meta.update(_extract_ffprobe(path))
        elif mime.startswith("audio/"):
            meta.update(_extract_ffprobe(path))
        elif mime == "application/pdf":
            meta.update(_extract_pdf(path))

    return meta


# ---------------------------------------------------------------------------
# Image metadata via Pillow
# ---------------------------------------------------------------------------

def _extract_image(path: Path) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS

        with Image.open(path) as img:
            meta["width"] = img.width
            meta["height"] = img.height
            meta["color_space"] = img.mode
            if hasattr(img, "bits"):
                meta["bit_depth"] = img.bits

            exif_data = img.getexif()
            if exif_data:
                exif = {}
                for tag_id, value in exif_data.items():
                    tag = TAGS.get(tag_id, str(tag_id))
                    # Convert bytes to string for JSON serialisation
                    if isinstance(value, bytes):
                        try:
                            value = value.decode("utf-8", errors="replace")
                        except Exception:
                            continue
                    exif[tag] = value

                meta["camera_make"] = exif.get("Make")
                meta["camera_model"] = exif.get("Model")
                meta["exposure"] = str(exif.get("ExposureTime", ""))
                meta["iso"] = exif.get("ISOSpeedRatings")
                meta["flash"] = str(exif.get("Flash", ""))

                # GPS
                gps_info = exif_data.get(0x8825)
                if gps_info and isinstance(gps_info, dict):
                    meta["gps_lat"] = _gps_to_decimal(gps_info.get(2), gps_info.get(1))
                    meta["gps_lon"] = _gps_to_decimal(gps_info.get(4), gps_info.get(3))
    except Exception:
        log.debug("Image metadata extraction failed for %s", path, exc_info=True)
    return meta


def _gps_to_decimal(coords: Any, ref: str | None) -> float | None:
    if not coords or not ref:
        return None
    try:
        d, m, s = [float(x) for x in coords]
        decimal = d + m / 60 + s / 3600
        if ref in ("S", "W"):
            decimal = -decimal
        return round(decimal, 6)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Video / audio metadata via ffprobe
# ---------------------------------------------------------------------------

def _extract_ffprobe(path: Path) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format", "-show_streams",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return meta

        info = json.loads(result.stdout)
        fmt = info.get("format", {})

        meta["duration"] = float(fmt.get("duration", 0))
        meta["container"] = fmt.get("format_name")
        meta["bitrate"] = int(fmt.get("bit_rate", 0))

        for stream in info.get("streams", []):
            codec_type = stream.get("codec_type")
            if codec_type == "video" and "codec" not in meta:
                meta["width"] = stream.get("width")
                meta["height"] = stream.get("height")
                meta["codec"] = stream.get("codec_name")
                meta["codec_profile"] = stream.get("profile")
                fps = stream.get("r_frame_rate", "0/1")
                if "/" in str(fps):
                    num, den = fps.split("/")
                    meta["framerate"] = round(float(num) / float(den), 2) if float(den) else 0
                # HDR detection
                if stream.get("color_transfer") in ("smpte2084", "arib-std-b67"):
                    meta["hdr_format"] = stream.get("color_transfer")
            elif codec_type == "audio" and "audio_codec" not in meta:
                meta["audio_codec"] = stream.get("codec_name")
                meta["audio_channels"] = stream.get("channels")
                meta["audio_sample_rate"] = int(stream.get("sample_rate", 0))
                meta["audio_bitrate"] = int(stream.get("bit_rate", 0))

    except FileNotFoundError:
        log.debug("ffprobe not found — skipping media metadata for %s", path)
    except Exception:
        log.debug("ffprobe failed for %s", path, exc_info=True)
    return meta


# ---------------------------------------------------------------------------
# PDF metadata via PyPDF2
# ---------------------------------------------------------------------------

def _extract_pdf(path: Path) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    try:
        from PyPDF2 import PdfReader

        reader = PdfReader(str(path))
        meta["page_count"] = len(reader.pages)
        info = reader.metadata
        if info:
            meta["author"] = info.author
            meta["producer"] = info.producer
        meta["has_text_layer"] = bool(reader.pages[0].extract_text().strip()) if reader.pages else False
    except ImportError:
        log.debug("PyPDF2 not installed — skipping PDF metadata for %s", path)
    except Exception:
        log.debug("PDF metadata extraction failed for %s", path, exc_info=True)
    return meta
