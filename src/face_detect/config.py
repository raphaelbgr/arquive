"""Configuration loader for face-detect / Arquive.

Loads a YAML config file into typed dataclasses.  Existing sections
(recognition, video, coordinator, workers, output) are unchanged.
New Arquive sections (cache, auth, iptv, dlna, transcode, ai, server)
are added alongside them — missing sections get sensible defaults.

Dependencies: pyyaml
"""

from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass, field

import yaml


DEFAULT_CONFIG_PATH = "config.yaml"

THRESHOLD_PRESETS = {
    "high_precision": 0.50,
    "balanced": 0.45,
    "high_recall": 0.35,
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".wmv", ".flv"}
AUDIO_EXTENSIONS = {".mp3", ".flac", ".wav", ".aac", ".ogg", ".wma", ".m4a", ".opus"}
DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt"}


@dataclass
class RecognitionConfig:
    model: str = "buffalo_l"
    det_size: tuple = (640, 640)
    threshold: float = 0.45


@dataclass
class VideoConfig:
    sample_fps: int = 2
    batch_size: int = 16
    merge_gap_seconds: int = 3


@dataclass
class CoordinatorConfig:
    host: str = "0.0.0.0"
    port: int = 8600
    task_timeout_seconds: int = 300


@dataclass
class WorkerDef:
    name: str = ""
    host: str = "localhost"
    ssh_alias: str = ""
    gpu: str = "cuda"
    locality_paths: list = field(default_factory=list)
    path_map: dict = field(default_factory=dict)  # coordinator path prefix -> worker path prefix


@dataclass
class OutputConfig:
    db_path: str = "./results/faces.db"
    thumbnails_dir: str = "./results/thumbs"
    json_path: str = "./results/results.json"
    html_path: str = "./results/report.html"


@dataclass
class CacheConfig:
    """Transcode / thumbnail cache settings."""
    enabled: bool = True
    directory: str = ""  # empty = OS temp directory
    limit_gb: float = 20.0
    preload_seconds: int = 20  # first N seconds pre-encoded per video


@dataclass
class AuthConfig:
    """Authentication settings."""
    sec_level: str = "simple-password"  # simple-password | user-account | forever
    session_duration: str = "365d"
    jwt_secret: str = ""  # auto-generated on first run if empty


@dataclass
class ServerConfig:
    """Arquive HTTP server settings."""
    host: str = "0.0.0.0"
    port: int = 64531


@dataclass
class TranscodeConfig:
    """GPU fleet transcoding settings."""
    gpu_busy_threshold: int = 80
    poll_interval_seconds: int = 5
    encoders: dict = field(default_factory=dict)  # node_name -> {encoder, health_check, priority}


@dataclass
class AIConfig:
    """AI description generation settings."""
    model: str = "qwen2.5-vl"
    endpoint: str = "http://mac-mini:11434/api/generate"
    enabled: bool = True
    batch_size: int = 50
    describe_videos: bool = True
    keyframe_count: int = 5


@dataclass
class IPTVConfig:
    """IPTV / Live TV settings."""
    enabled: bool = True
    recording_dir: str = ""
    epg_refresh_hours: int = 12
    playlist_refresh_hours: int = 24


@dataclass
class DLNAConfig:
    """DLNA/UPnP server settings."""
    enabled: bool = False
    friendly_name: str = "Arquive Media Server"


@dataclass
class Config:
    # --- Existing sections (unchanged) ---
    faces_dir: str = "./recognition/faces"
    media_dirs: list = field(default_factory=list)
    skip_processed: bool = True
    exclude_dirs: list = field(default_factory=list)
    recognition: RecognitionConfig = field(default_factory=RecognitionConfig)
    video: VideoConfig = field(default_factory=VideoConfig)
    coordinator: CoordinatorConfig = field(default_factory=CoordinatorConfig)
    workers: list = field(default_factory=list)
    output: OutputConfig = field(default_factory=OutputConfig)
    hide_persons: list = field(default_factory=list)
    # --- New Arquive sections ---
    cache: CacheConfig = field(default_factory=CacheConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    transcode: TranscodeConfig = field(default_factory=TranscodeConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    iptv: IPTVConfig = field(default_factory=IPTVConfig)
    dlna: DLNAConfig = field(default_factory=DLNAConfig)


def load_config(config_path: str = None) -> Config:
    """Load configuration from YAML file."""
    path = config_path or DEFAULT_CONFIG_PATH
    if not os.path.exists(path):
        return Config()

    with open(path, "r") as f:
        raw = yaml.safe_load(f) or {}

    cfg = Config()
    cfg.faces_dir = raw.get("faces_dir", cfg.faces_dir)
    cfg.media_dirs = raw.get("media_dirs", cfg.media_dirs)
    cfg.skip_processed = raw.get("skip_processed", True)
    cfg.exclude_dirs = raw.get("exclude_dirs", [])
    cfg.hide_persons = raw.get("hide_persons", [])

    if "recognition" in raw:
        r = raw["recognition"]
        cfg.recognition = RecognitionConfig(
            model=r.get("model", "buffalo_l"),
            det_size=tuple(r.get("det_size", [640, 640])),
            threshold=r.get("threshold", 0.45),
        )

    if "video" in raw:
        v = raw["video"]
        cfg.video = VideoConfig(
            sample_fps=v.get("sample_fps", 2),
            batch_size=v.get("batch_size", 16),
            merge_gap_seconds=v.get("merge_gap_seconds", 3),
        )

    if "coordinator" in raw:
        c = raw["coordinator"]
        cfg.coordinator = CoordinatorConfig(
            host=c.get("host", "0.0.0.0"),
            port=c.get("port", 8600),
            task_timeout_seconds=c.get("task_timeout_seconds", 300),
        )

    if "workers" in raw:
        cfg.workers = []
        for w in raw["workers"]:
            cfg.workers.append(WorkerDef(
                name=w.get("name", ""),
                host=w.get("host", "localhost"),
                ssh_alias=w.get("ssh_alias", ""),
                gpu=w.get("gpu", "cuda"),
                locality_paths=w.get("locality_paths", []),
                path_map=w.get("path_map", {}),
            ))

    if "output" in raw:
        o = raw["output"]
        cfg.output = OutputConfig(
            db_path=o.get("db_path", cfg.output.db_path),
            thumbnails_dir=o.get("thumbnails_dir", cfg.output.thumbnails_dir),
            json_path=o.get("json_path", cfg.output.json_path),
            html_path=o.get("html_path", cfg.output.html_path),
        )

    # --- New Arquive sections ---

    if "cache" in raw:
        c = raw["cache"]
        cfg.cache = CacheConfig(
            enabled=c.get("enabled", True),
            directory=c.get("directory", ""),
            limit_gb=c.get("limit_gb", 20.0),
            preload_seconds=c.get("preload_seconds", 20),
        )

    if "auth" in raw:
        a = raw["auth"]
        cfg.auth = AuthConfig(
            sec_level=a.get("sec_level", "simple-password"),
            session_duration=a.get("session_duration", "365d"),
            jwt_secret=a.get("jwt_secret", ""),
        )

    if "server" in raw:
        s = raw["server"]
        cfg.server = ServerConfig(
            host=s.get("host", "0.0.0.0"),
            port=s.get("port", 64531),
        )

    if "transcode" in raw:
        t = raw["transcode"]
        cfg.transcode = TranscodeConfig(
            gpu_busy_threshold=t.get("gpu_busy_threshold", 80),
            poll_interval_seconds=t.get("poll_interval_seconds", 5),
            encoders=t.get("encoders", {}),
        )

    if "ai" in raw:
        ai = raw["ai"]
        cfg.ai = AIConfig(
            model=ai.get("model", "qwen2.5-vl"),
            endpoint=ai.get("endpoint", "http://mac-mini:11434/api/generate"),
            enabled=ai.get("enabled", True),
            batch_size=ai.get("batch_size", 50),
            describe_videos=ai.get("describe_videos", True),
            keyframe_count=ai.get("keyframe_count", 5),
        )

    if "iptv" in raw:
        i = raw["iptv"]
        cfg.iptv = IPTVConfig(
            enabled=i.get("enabled", True),
            recording_dir=i.get("recording_dir", ""),
            epg_refresh_hours=i.get("epg_refresh_hours", 12),
            playlist_refresh_hours=i.get("playlist_refresh_hours", 24),
        )

    if "dlna" in raw:
        d = raw["dlna"]
        cfg.dlna = DLNAConfig(
            enabled=d.get("enabled", False),
            friendly_name=d.get("friendly_name", "Arquive Media Server"),
        )

    return cfg
