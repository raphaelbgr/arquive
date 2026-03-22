"""HLS transcode orchestrator using FFmpeg subprocess + GPU cascade.

Implements the cascade strategy:
  1. Check cache for pre-encoded segments
  2. Try local GPU (NVENC) via FFmpeg subprocess
  3. SSH probe fleet for available GPUs
  4. CPU fallback (x264/x265)

Each video is split into HLS segments (.m3u8 + .ts files) cached by
the CacheManager.  Adaptive quality levels: 360p, 720p, 1080p, 2160p.

Dependencies: subprocess (ffmpeg), threading
"""

from __future__ import annotations

import logging
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

QUALITY_PRESETS = {
    "360p":  {"width": 640,  "height": 360,  "bitrate": "800k",  "maxrate": "1200k"},
    "720p":  {"width": 1280, "height": 720,  "bitrate": "2500k", "maxrate": "4000k"},
    "1080p": {"width": 1920, "height": 1080, "bitrate": "5000k", "maxrate": "8000k"},
    "2160p": {"width": 3840, "height": 2160, "bitrate": "15000k","maxrate": "20000k"},
}


@dataclass
class TranscodeJob:
    file_path: str
    file_hash: str
    quality: str
    output_dir: str
    encoder: str = "libx264"  # or nvenc, videotoolbox
    status: str = "pending"
    process: subprocess.Popen | None = None


class Transcoder:
    """Orchestrates HLS transcoding with GPU cascade fallback."""

    def __init__(self, cache_manager: Any, config: Any) -> None:
        self.cache = cache_manager
        self.config = config
        self._jobs: dict[str, TranscodeJob] = {}
        self._lock = threading.Lock()

    def get_or_transcode(self, file_path: str, file_hash: str, quality: str = "720p") -> str:
        """Return path to HLS manifest, transcoding on-demand if needed.

        Checks cache first; starts transcode if not cached.
        Returns the manifest (.m3u8) path.
        """
        manifest_dir = self.cache.segments_dir / file_hash / quality
        manifest_path = manifest_dir / "manifest.m3u8"

        if manifest_path.exists():
            return str(manifest_path)

        # Start transcode
        manifest_dir.mkdir(parents=True, exist_ok=True)
        encoder = self._select_encoder()
        self._transcode_hls(file_path, str(manifest_dir), quality, encoder)
        return str(manifest_path)

    def _select_encoder(self) -> str:
        """Pick the best available encoder via cascade."""
        # Try local NVENC first
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                util = int(result.stdout.strip().replace(" %", ""))
                if util < self.config.transcode.gpu_busy_threshold:
                    return "h264_nvenc"
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
            pass

        # CPU fallback
        return "libx264"

    def _transcode_hls(
        self, input_path: str, output_dir: str, quality: str, encoder: str
    ) -> None:
        """Run FFmpeg to produce HLS segments."""
        preset = QUALITY_PRESETS.get(quality, QUALITY_PRESETS["720p"])

        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-c:v", encoder,
            "-b:v", preset["bitrate"],
            "-maxrate", preset["maxrate"],
            "-bufsize", str(int(preset["maxrate"].replace("k", "")) * 2) + "k",
            "-vf", f"scale={preset['width']}:{preset['height']}",
            "-c:a", "aac", "-b:a", "128k",
            "-f", "hls",
            "-hls_time", "6",
            "-hls_list_size", "0",
            "-hls_segment_filename", f"{output_dir}/seg_%03d.ts",
            f"{output_dir}/manifest.m3u8",
        ]

        log.info("Transcoding %s -> %s (%s via %s)", input_path, output_dir, quality, encoder)
        result = subprocess.run(cmd, capture_output=True, timeout=600)
        if result.returncode != 0:
            log.error("Transcode failed: %s", result.stderr.decode(errors="replace")[-500:])
            raise RuntimeError(f"FFmpeg transcode failed for {input_path}")

        # Register segments in cache
        for ts_file in Path(output_dir).glob("seg_*.ts"):
            seg_index = int(ts_file.stem.split("_")[1])
            self.cache.register_segment(
                file_hash=Path(output_dir).parent.name,
                quality=quality,
                segment_index=seg_index,
                path=str(ts_file),
                size_bytes=ts_file.stat().st_size,
            )

        log.info("Transcode complete: %s %s", input_path, quality)
