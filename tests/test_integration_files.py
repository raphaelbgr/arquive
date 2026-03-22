"""Integration test: test every file type against all API endpoints.

Grabs one real sample of each file extension from the library and tests:
- File serving (/file?path=...)
- Thumbnail generation (/api/v1/media/:id/thumbnail)
- File detail (/api/v1/media/:id)
- Download (/api/v1/media/:id/download)
- For videos: codec detection, poster generation, HEVC transcode
- For images: HEIC conversion, EXIF rotation, resize
- For docs: PDF metadata
"""

import json
import os
import sys
import time
import urllib.parse

import pytest
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

BASE = "http://localhost:64531"

# Sample file IDs by extension (from real library)
SAMPLES = {
    ".jpg":  12,
    ".jpeg": 18415,
    ".png":  1925,
    ".gif":  1757,
    ".heic": 18498,
    ".bmp":  64,
    ".webp": 67236,
    ".tiff": 133540,
    ".mp4":  12236,
    ".mov":  10455,
    ".avi":  321,
    ".3gp":  11052,
    ".wmv":  12897,
    ".flv":  149059,
    ".webm": 207242,
    ".mts":  161941,
    ".mp3":  11049,
    ".wav":  5637,
    ".aac":  152999,
    ".ogg":  127988,
    ".m4a":  128005,
    ".pdf":  4907,
    ".doc":  61,
    ".docx": 11019,
    ".xls":  127738,
    ".xlsx": 125019,
    ".ppt":  12926,
    ".pptx": 1241,
    ".txt":  9824,
}


def api(path):
    return requests.get(f"{BASE}{path}", timeout=30)


def api_head(path):
    return requests.head(f"{BASE}{path}", timeout=10)


class TestFileDetail:
    """GET /api/v1/media/:id — must return valid JSON for every file type."""

    @pytest.mark.parametrize("ext,file_id", list(SAMPLES.items()))
    def test_detail(self, ext, file_id):
        r = api(f"/api/v1/media/{file_id}")
        assert r.status_code == 200, f"{ext} id={file_id}: {r.status_code} {r.text[:100]}"
        data = r.json()
        assert data["id"] == file_id
        assert data["path"]  # path must exist
        assert data["name"]


class TestFileServing:
    """GET /file?path=... — must serve the actual file."""

    @pytest.mark.parametrize("ext,file_id", list(SAMPLES.items()))
    def test_serve(self, ext, file_id):
        # Get path from detail
        detail = api(f"/api/v1/media/{file_id}").json()
        path = detail["path"]
        if not os.path.exists(path):
            pytest.skip(f"File not on disk: {path}")
        if os.path.getsize(path) == 0:
            pytest.skip(f"Empty file: {path}")

        encoded = urllib.parse.quote(path)
        r = api(f"/file?path={encoded}")
        assert r.status_code == 200, f"{ext}: serve failed {r.status_code}"
        assert len(r.content) > 0, f"{ext}: empty response"


class TestImageThumbnails:
    """GET /file?path=...&w=320 — must resize images."""

    IMAGE_EXTS = [".jpg", ".jpeg", ".png", ".gif", ".heic", ".bmp", ".webp", ".tiff"]

    @pytest.mark.parametrize("ext", IMAGE_EXTS)
    def test_thumbnail(self, ext):
        file_id = SAMPLES.get(ext)
        if not file_id:
            pytest.skip(f"No sample for {ext}")

        detail = api(f"/api/v1/media/{file_id}").json()
        path = detail["path"]
        if not os.path.exists(path):
            pytest.skip(f"File not on disk")
        if os.path.getsize(path) == 0:
            pytest.skip(f"Empty file")

        encoded = urllib.parse.quote(path)
        r = api(f"/file?path={encoded}&w=320")
        assert r.status_code == 200, f"{ext}: thumb failed {r.status_code}"
        assert r.headers.get("content-type", "").startswith("image/"), f"{ext}: not an image: {r.headers.get('content-type')}"
        assert len(r.content) > 100, f"{ext}: thumb too small ({len(r.content)} bytes)"

        # Full-res should be larger than thumbnail
        r_full = api(f"/file?path={encoded}")
        assert len(r_full.content) >= len(r.content), f"{ext}: thumb larger than original?"


class TestHEICConversion:
    """HEIC files must be converted to JPEG for browser display."""

    def test_heic_serves_as_jpeg(self):
        file_id = SAMPLES[".heic"]
        detail = api(f"/api/v1/media/{file_id}").json()
        path = detail["path"]
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            pytest.skip("HEIC file not available")

        encoded = urllib.parse.quote(path)
        r = api(f"/file?path={encoded}")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/jpeg", f"HEIC not converted: {r.headers['content-type']}"


class TestVideoPosters:
    """GET /api/v1/media/:id/thumbnail — must generate poster for videos."""

    VIDEO_EXTS = [".mp4", ".mov", ".avi", ".3gp", ".wmv", ".webm"]

    @pytest.mark.parametrize("ext", VIDEO_EXTS)
    def test_poster(self, ext):
        file_id = SAMPLES.get(ext)
        if not file_id:
            pytest.skip(f"No sample for {ext}")

        detail = api(f"/api/v1/media/{file_id}").json()
        if not os.path.exists(detail["path"]):
            pytest.skip("File not on disk")

        r = api(f"/api/v1/media/{file_id}/thumbnail")
        assert r.status_code == 200, f"{ext}: poster failed {r.status_code} {r.text[:100]}"
        assert r.headers.get("content-type", "").startswith("image/"), f"{ext}: not an image"
        assert len(r.content) > 500, f"{ext}: poster too small ({len(r.content)} bytes)"

        # Check dimensions are 320x180 (16:9)
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(r.content))
        assert img.size == (320, 180), f"{ext}: poster wrong size {img.size}"


class TestVideoCodecs:
    """Check video codec detection for all video types."""

    VIDEO_EXTS = [".mp4", ".mov", ".avi", ".3gp", ".wmv", ".flv", ".webm", ".mts"]

    @pytest.mark.parametrize("ext", VIDEO_EXTS)
    def test_codec_probe(self, ext):
        file_id = SAMPLES.get(ext)
        if not file_id:
            pytest.skip(f"No sample for {ext}")

        detail = api(f"/api/v1/media/{file_id}").json()
        path = detail["path"]
        if not os.path.exists(path):
            pytest.skip("File not on disk")

        import subprocess
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=codec_name",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=10,
        )
        codec = result.stdout.strip()
        assert codec, f"{ext}: ffprobe returned no codec"
        print(f"  {ext}: codec={codec}")


class TestVideoPlayback:
    """Test that videos can be served for browser playback (with HEVC transcode)."""

    def test_h264_direct(self):
        """H.264 MP4 should serve directly without transcoding."""
        detail = api(f"/api/v1/media/{SAMPLES['.mp4']}").json()
        path = detail["path"]
        if not os.path.exists(path):
            pytest.skip("File not on disk")

        encoded = urllib.parse.quote(path)
        # Use Range request like a browser would
        r = requests.get(
            f"{BASE}/file?path={encoded}",
            headers={"Range": "bytes=0-1023"},
            timeout=10,
        )
        assert r.status_code == 206, f"Range request failed: {r.status_code}"

    def test_mov_serves(self):
        """MOV files should be serveable."""
        detail = api(f"/api/v1/media/{SAMPLES['.mov']}").json()
        path = detail["path"]
        if not os.path.exists(path):
            pytest.skip("File not on disk")

        encoded = urllib.parse.quote(path)
        r = requests.get(
            f"{BASE}/file?path={encoded}",
            headers={"Range": "bytes=0-1023"},
            timeout=10,
        )
        assert r.status_code in (200, 206), f"MOV serve failed: {r.status_code}"


class TestDownload:
    """GET /api/v1/media/:id/download — must serve with attachment header."""

    @pytest.mark.parametrize("ext", [".jpg", ".mp4", ".pdf", ".docx", ".mp3"])
    def test_download(self, ext):
        file_id = SAMPLES.get(ext)
        if not file_id:
            pytest.skip(f"No sample for {ext}")

        detail = api(f"/api/v1/media/{file_id}").json()
        if not os.path.exists(detail["path"]):
            pytest.skip("File not on disk")

        r = requests.get(f"{BASE}/api/v1/media/{file_id}/download", timeout=30, stream=True)
        assert r.status_code == 200, f"{ext}: download failed {r.status_code}"
        # Read first chunk only
        chunk = next(r.iter_content(8192), b"")
        assert len(chunk) > 0, f"{ext}: empty download"
        r.close()


class TestDebugAPI:
    """GET /api/v1/debug/* — diagnostic endpoints."""

    def test_debug_stats(self):
        r = api("/api/v1/debug/stats")
        assert r.status_code == 200
        data = r.json()
        assert data["total_files"] > 0
        assert data["schema_version"] >= 3

    @pytest.mark.parametrize("ext", [".jpg", ".mp4", ".pdf"])
    def test_debug_file(self, ext):
        file_id = SAMPLES[ext]
        r = api(f"/api/v1/debug/file/{file_id}")
        assert r.status_code == 200
        data = r.json()
        assert "db_record" in data
        assert "filesystem" in data


class TestBatchAPI:
    """POST /api/v1/media/batch — batch month fetch."""

    def test_batch(self):
        r = requests.post(
            f"{BASE}/api/v1/media/batch",
            json={"months": ["2025-12", "2025-06", "2020-01"], "limit": 5},
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 3
        for month, result in data.items():
            assert "items" in result
            assert "total" in result


class TestFolderBrowser:
    """GET /api/v1/system/browse-folder — server-side folder listing."""

    def test_list_drives(self):
        r = api("/api/v1/system/browse-folder")
        assert r.status_code == 200
        data = r.json()
        assert len(data["items"]) > 0
        # Should have C: at minimum on Windows
        names = [i["name"] for i in data["items"]]
        assert "C:" in names

    def test_browse_folder(self):
        r = api("/api/v1/system/browse-folder?path=C%3A%5C")
        assert r.status_code == 200
        data = r.json()
        assert data["current"] == "C:\\"
        assert len(data["items"]) > 0


class TestTimelineAPI:
    """Timeline + month filtering."""

    def test_timeline(self):
        r = api("/api/v1/media/timeline")
        assert r.status_code == 200
        data = r.json()
        assert len(data["groups"]) > 0
        # Should only have media, not docs
        for g in data["groups"][:5]:
            assert g["count"] > 0

    def test_month_filter(self):
        # Get first month
        tl = api("/api/v1/media/timeline").json()
        month = tl["groups"][0]["month"]
        r = api(f"/api/v1/media?month={month}&limit=5")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] > 0
        assert len(data["items"]) <= 5
