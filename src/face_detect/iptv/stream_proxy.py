"""Live stream proxy for IPTV channels.

Proxies live HLS/MPEG-TS streams through Arquive, enabling adaptive
quality, timeshift buffering, and recording.  Also captures periodic
thumbnails for live channel preview tiles.

Dependencies: requests, subprocess (ffmpeg)
"""

from __future__ import annotations

import logging
import subprocess
import threading
from pathlib import Path
from typing import Any, Generator

log = logging.getLogger(__name__)


class StreamProxy:
    """Proxies a live stream and optionally captures thumbnails."""

    def __init__(self, cache_dir: str) -> None:
        self.cache_dir = Path(cache_dir)
        self._active_streams: dict[int, subprocess.Popen] = {}
        self._lock = threading.Lock()

    def proxy_hls(self, stream_url: str) -> Generator[bytes, None, None]:
        """Stream HLS content chunk-by-chunk.

        For HLS sources, fetches and yields each segment.
        For other sources, pipes through FFmpeg to produce HLS.
        """
        import requests

        if stream_url.endswith(".m3u8"):
            # Pass-through HLS: fetch and relay segments
            resp = requests.get(stream_url, stream=True, timeout=10)
            resp.raise_for_status()
            for chunk in resp.iter_content(chunk_size=8192):
                yield chunk
        else:
            # Transcode to HLS via FFmpeg pipe
            proc = subprocess.Popen(
                [
                    "ffmpeg", "-i", stream_url,
                    "-c:v", "copy", "-c:a", "copy",
                    "-f", "mpegts", "pipe:1",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            try:
                while True:
                    chunk = proc.stdout.read(8192)
                    if not chunk:
                        break
                    yield chunk
            finally:
                proc.terminate()

    def capture_live_thumbnail(self, stream_url: str, output_path: str) -> bool:
        """Capture a single frame from a live stream for preview tiles."""
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", stream_url,
                    "-vframes", "1", "-q:v", "5",
                    "-vf", "scale=160:90",
                    output_path,
                ],
                capture_output=True,
                timeout=10,
            )
            return Path(output_path).exists()
        except Exception:
            log.debug("Failed to capture thumbnail from %s", stream_url)
            return False
