"""Shared test fixtures for Arquive test suite."""

import os
import sys
import tempfile

import pytest

# Ensure src/ is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary Database with all migrations applied."""
    from face_detect.database import Database
    db_path = str(tmp_path / "test.db")
    db = Database(db_path)
    yield db
    db.close()


@pytest.fixture
def config():
    """Load default config (from config.yaml if present, else defaults)."""
    from face_detect.config import load_config
    return load_config()


@pytest.fixture
def auth_manager(tmp_db, config):
    """AuthManager backed by a temp database."""
    from face_detect.auth import AuthManager
    return AuthManager(tmp_db, config)


@pytest.fixture
def cache(tmp_path):
    """CacheManager using a temp directory."""
    from face_detect.cache_manager import CacheManager
    cm = CacheManager(cache_dir=str(tmp_path / "cache"), limit_bytes=100 * 1024 * 1024)
    yield cm
    cm.close()


@pytest.fixture
def app(config, tmp_db, auth_manager, cache):
    """Flask test app with all routes."""
    from face_detect.webapp import create_app
    flask_app = create_app(config, tmp_db, auth_manager, cache)
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()
