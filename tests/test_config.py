"""Tests for configuration loading — existing + new Arquive sections."""

import tempfile
from pathlib import Path

import yaml


class TestConfigDefaults:
    def test_default_config_loads(self):
        from face_detect.config import Config
        c = Config()
        assert c.server.port == 64531
        assert c.auth.sec_level == "simple-password"
        assert c.cache.limit_gb == 20.0
        assert c.ai.model == "qwen2.5-vl"
        assert c.iptv.enabled is True
        assert c.dlna.enabled is False

    def test_existing_sections_preserved(self, config):
        assert config.recognition.model == "buffalo_l"
        assert config.recognition.threshold == 0.45
        assert config.coordinator.port == 8600


class TestConfigLoading:
    def test_load_with_new_sections(self, tmp_path):
        from face_detect.config import load_config
        cfg_file = tmp_path / "test.yaml"
        cfg_file.write_text(yaml.dump({
            "server": {"port": 9999, "host": "127.0.0.1"},
            "auth": {"sec_level": "forever"},
            "cache": {"limit_gb": 50.0, "enabled": False},
            "ai": {"model": "llama3", "enabled": False},
            "iptv": {"recording_dir": "/rec", "epg_refresh_hours": 6},
            "dlna": {"enabled": True, "friendly_name": "Test Server"},
            "transcode": {"gpu_busy_threshold": 90},
        }))
        c = load_config(str(cfg_file))
        assert c.server.port == 9999
        assert c.auth.sec_level == "forever"
        assert c.cache.limit_gb == 50.0
        assert c.cache.enabled is False
        assert c.ai.model == "llama3"
        assert c.iptv.recording_dir == "/rec"
        assert c.dlna.friendly_name == "Test Server"
        assert c.transcode.gpu_busy_threshold == 90

    def test_missing_file_returns_defaults(self, tmp_path):
        from face_detect.config import load_config
        c = load_config(str(tmp_path / "nonexistent.yaml"))
        assert c.server.port == 64531

    def test_partial_config_fills_defaults(self, tmp_path):
        from face_detect.config import load_config
        cfg_file = tmp_path / "partial.yaml"
        cfg_file.write_text(yaml.dump({"server": {"port": 8080}}))
        c = load_config(str(cfg_file))
        assert c.server.port == 8080
        assert c.server.host == "0.0.0.0"  # default
        assert c.auth.sec_level == "simple-password"  # default


class TestMediaExtensions:
    def test_all_extension_sets(self):
        from face_detect.config import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, AUDIO_EXTENSIONS, DOCUMENT_EXTENSIONS
        assert ".jpg" in IMAGE_EXTENSIONS
        assert ".mp4" in VIDEO_EXTENSIONS
        assert ".mp3" in AUDIO_EXTENSIONS
        assert ".pdf" in DOCUMENT_EXTENSIONS
