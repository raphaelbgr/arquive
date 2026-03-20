"""Configuration loader for face-detect."""

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
class Config:
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

    return cfg
