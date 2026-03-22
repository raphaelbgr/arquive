"""Tests for Flask API endpoints — media, faces, IPTV, cache, fleet, auth, settings."""

import json


class TestAuthAPI:
    def test_login_wrong_password(self, client, auth_manager):
        auth_manager.set_password("correct")
        resp = client.post("/api/v1/auth/login", json={"password": "wrong"})
        assert resp.status_code == 401

    def test_login_correct_password(self, client, auth_manager):
        auth_manager.set_password("correct")
        resp = client.post("/api/v1/auth/login", json={"password": "correct"})
        assert resp.status_code == 200
        assert "arquive_token" in resp.headers.get("Set-Cookie", "")

    def test_me_unauthenticated(self, client):
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_me_authenticated(self, client, auth_manager):
        auth_manager.set_password("pw")
        login = client.post("/api/v1/auth/login", json={"password": "pw"})
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "user" in data

    def test_logout(self, client, auth_manager):
        auth_manager.set_password("pw")
        client.post("/api/v1/auth/login", json={"password": "pw"})
        resp = client.post("/api/v1/auth/logout")
        assert resp.status_code == 200

    def test_revoke_all(self, client):
        resp = client.post("/api/v1/auth/revoke-all")
        assert resp.status_code == 200


class TestMediaAPI:
    def test_media_list_empty(self, client):
        resp = client.get("/api/v1/media")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_media_stats(self, client):
        resp = client.get("/api/v1/media/stats")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "total_files" in data

    def test_media_with_files(self, client, tmp_db):
        tmp_db.upsert_file(path="/test/photo.jpg", name="photo.jpg", extension=".jpg", size=2048)
        resp = client.get("/api/v1/media")
        data = resp.get_json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "photo.jpg"

    def test_media_detail(self, client, tmp_db):
        fid = tmp_db.upsert_file(path="/test/vid.mp4", name="vid.mp4", size=10000)
        resp = client.get(f"/api/v1/media/{fid}")
        assert resp.status_code == 200
        assert resp.get_json()["name"] == "vid.mp4"

    def test_media_detail_not_found(self, client):
        resp = client.get("/api/v1/media/99999")
        assert resp.status_code == 404

    def test_media_search(self, client, tmp_db):
        tmp_db.upsert_file(path="/test/sunset.jpg", name="sunset.jpg", size=100)
        tmp_db.upsert_file(path="/test/cat.jpg", name="cat.jpg", size=100)
        resp = client.get("/api/v1/media/search?q=sunset")
        data = resp.get_json()
        assert len(data["items"]) == 1

    def test_media_timeline(self, client):
        resp = client.get("/api/v1/media/timeline")
        assert resp.status_code == 200

    def test_media_folders(self, client):
        resp = client.get("/api/v1/media/folders")
        assert resp.status_code == 200


class TestFacesAPI:
    def test_persons_list(self, client, tmp_db):
        tmp_db.ensure_person("Alice", 5)
        job = tmp_db.create_scan_job(1)
        tmp_db.add_match(job, "Alice", "/a.jpg", "image", 0.9)
        resp = client.get("/api/v1/faces/persons")
        data = resp.get_json()
        assert len(data["persons"]) == 1
        assert data["persons"][0]["person_name"] == "Alice"

    def test_person_detail(self, client, tmp_db):
        job = tmp_db.create_scan_job(1)
        tmp_db.add_match(job, "Bob", "/b.jpg", "image", 0.85)
        resp = client.get("/api/v1/faces/persons/Bob")
        data = resp.get_json()
        assert data["total"] == 1

    def test_scan_status(self, client):
        resp = client.get("/api/v1/faces/scan")
        assert resp.status_code == 200

    def test_face_settings(self, client):
        resp = client.get("/api/v1/faces/settings")
        data = resp.get_json()
        assert "threshold" in data
        assert "model" in data


class TestCacheAPI:
    def test_cache_stats(self, client):
        resp = client.get("/api/v1/cache/stats")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "used_bytes" in data
        assert "limit_bytes" in data

    def test_cache_clear(self, client):
        resp = client.post("/api/v1/cache/clear")
        assert resp.status_code == 200
        assert "freed_bytes" in resp.get_json()

    def test_cache_settings_update(self, client):
        resp = client.put("/api/v1/cache/settings", json={"limit_gb": 50, "enabled": False})
        assert resp.status_code == 200


class TestFleetAPI:
    def test_fleet_status(self, client):
        resp = client.get("/api/v1/fleet/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "nodes" in data

    def test_fleet_nodes(self, client):
        resp = client.get("/api/v1/fleet/nodes")
        assert resp.status_code == 200


class TestSettingsAPI:
    def test_get_all_settings(self, client):
        resp = client.get("/api/v1/settings")
        assert resp.status_code == 200

    def test_update_settings(self, client):
        resp = client.put("/api/v1/settings", json={"theme": "dark"})
        assert resp.status_code == 200

    def test_theme(self, client):
        client.put("/api/v1/settings/theme", json={"theme": "light"})
        resp = client.get("/api/v1/settings/theme")
        assert resp.get_json()["theme"] == "light"

    def test_preview_tiles_defaults(self, client):
        resp = client.get("/api/v1/settings/preview-tiles")
        data = resp.get_json()
        assert data["mediaLibrary"] == "always"
        assert data["crossfadeDurationMs"] == 200

    def test_preview_tiles_update(self, client):
        client.put("/api/v1/settings/preview-tiles", json={
            "mediaLibrary": "hover",
            "liveTV": "off",
            "frameIntervalMs": 2000,
            "crossfadeDurationMs": 300,
        })
        resp = client.get("/api/v1/settings/preview-tiles")
        data = resp.get_json()
        assert data["mediaLibrary"] == "hover"
        assert data["liveTV"] == "off"

    def test_libraries_crud(self, client):
        # Add
        resp = client.post("/api/v1/settings/libraries", json={
            "name": "Photos", "type": "local", "path": "/photos"
        })
        assert resp.status_code == 201
        lid = resp.get_json()["id"]

        # List
        resp = client.get("/api/v1/settings/libraries")
        assert len(resp.get_json()["libraries"]) == 1

        # Remove
        resp = client.delete(f"/api/v1/settings/libraries/{lid}")
        assert resp.status_code == 200


class TestIPTVAPI:
    def test_playlists_empty(self, client):
        resp = client.get("/api/v1/iptv/playlists")
        assert resp.status_code == 200
        assert resp.get_json()["playlists"] == []

    def test_channels_empty(self, client):
        resp = client.get("/api/v1/iptv/channels")
        assert resp.status_code == 200

    def test_custom_streams_crud(self, client):
        resp = client.post("/api/v1/iptv/streams", json={
            "name": "Test Stream", "url": "http://example.com/stream.m3u8"
        })
        assert resp.status_code == 201
        sid = resp.get_json()["id"]

        resp = client.get("/api/v1/iptv/streams")
        assert len(resp.get_json()["streams"]) == 1

        resp = client.delete(f"/api/v1/iptv/streams/{sid}")
        assert resp.status_code == 200

    def test_epg_empty(self, client):
        resp = client.get("/api/v1/iptv/epg")
        assert resp.status_code == 200

    def test_epg_now(self, client):
        resp = client.get("/api/v1/iptv/epg/now")
        assert resp.status_code == 200

    def test_recordings_empty(self, client):
        resp = client.get("/api/v1/iptv/recordings")
        assert resp.status_code == 200


class TestAIAPI:
    def test_ai_status(self, client):
        resp = client.get("/api/v1/ai/status")
        data = resp.get_json()
        assert "enabled" in data
        assert "model" in data

    def test_ai_config(self, client):
        resp = client.get("/api/v1/ai/config")
        assert resp.status_code == 200


class TestSPARouting:
    def test_index_serves_react(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_spa_routes_return_html(self, client):
        for path in ["/browse", "/timeline", "/live", "/people", "/settings"]:
            resp = client.get(path)
            assert resp.status_code == 200, f"{path} returned {resp.status_code}"
