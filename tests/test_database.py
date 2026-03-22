"""Tests for database schema, migrations, and CRUD operations."""

import json


class TestMigrations:
    def test_schema_version_reaches_latest(self, tmp_db):
        row = tmp_db.conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        assert row[0] == 3

    def test_all_tables_created(self, tmp_db):
        tables = tmp_db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = {r["name"] for r in tables}
        expected = {
            "persons", "matches", "processed_files", "scan_jobs",  # v0
            "files", "libraries", "credentials", "users", "settings",  # v1
            "preencode_queue", "cache_history", "sprites",  # v2
            "iptv_playlists", "iptv_channels", "custom_streams",  # v3
            "epg_programs", "epg_sources", "recordings",  # v3
            "schema_version",
        }
        assert expected.issubset(names)

    def test_idempotent_init(self, tmp_db):
        """Running _init_schema again should not fail or duplicate data."""
        tmp_db._init_schema()
        row = tmp_db.conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        assert row[0] == 3

    def test_existing_face_tables_untouched(self, tmp_db):
        """Original face-detection tables still have correct columns."""
        cols = tmp_db.conn.execute("PRAGMA table_info(matches)").fetchall()
        col_names = {c["name"] for c in cols}
        assert {"person_name", "file_path", "confidence", "thumbnail_path"}.issubset(col_names)


class TestSettings:
    def test_set_and_get(self, tmp_db):
        tmp_db.set_setting("theme", "dark")
        assert tmp_db.get_setting("theme") == "dark"

    def test_get_default(self, tmp_db):
        assert tmp_db.get_setting("nonexistent", "fallback") == "fallback"

    def test_overwrite(self, tmp_db):
        tmp_db.set_setting("key", "v1")
        tmp_db.set_setting("key", "v2")
        assert tmp_db.get_setting("key") == "v2"

    def test_get_all(self, tmp_db):
        tmp_db.set_setting("a", "1")
        tmp_db.set_setting("b", "2")
        all_settings = tmp_db.get_all_settings()
        assert all_settings["a"] == "1"
        assert all_settings["b"] == "2"


class TestLibraries:
    def test_add_and_list(self, tmp_db):
        lid = tmp_db.add_library("Photos", "local", "/data/photos")
        assert lid > 0
        libs = tmp_db.get_libraries()
        assert len(libs) == 1
        assert libs[0]["name"] == "Photos"
        assert libs[0]["type"] == "local"

    def test_remove(self, tmp_db):
        lid = tmp_db.add_library("Temp", "local", "/tmp")
        tmp_db.remove_library(lid)
        assert len(tmp_db.get_libraries()) == 0


class TestFiles:
    def test_upsert_insert(self, tmp_db):
        fid = tmp_db.upsert_file(path="/test/a.jpg", name="a.jpg", extension=".jpg", size=1024)
        assert fid > 0
        f = tmp_db.get_file_by_id(fid)
        assert f["name"] == "a.jpg"
        assert f["size"] == 1024

    def test_upsert_update(self, tmp_db):
        fid1 = tmp_db.upsert_file(path="/test/b.jpg", name="b.jpg", size=100)
        fid2 = tmp_db.upsert_file(path="/test/b.jpg", name="b.jpg", size=200)
        assert fid1 == fid2
        f = tmp_db.get_file_by_id(fid1)
        assert f["size"] == 200

    def test_get_files_pagination(self, tmp_db):
        for i in range(10):
            tmp_db.upsert_file(path=f"/test/{i}.jpg", name=f"{i}.jpg", extension=".jpg", size=i)
        page1 = tmp_db.get_files(limit=5, offset=0)
        page2 = tmp_db.get_files(limit=5, offset=5)
        assert len(page1) == 5
        assert len(page2) == 5

    def test_get_file_count(self, tmp_db):
        assert tmp_db.get_file_count() == 0
        tmp_db.upsert_file(path="/x.jpg", name="x.jpg", size=1)
        assert tmp_db.get_file_count() == 1


class TestUsers:
    def test_add_and_get(self, tmp_db):
        uid = tmp_db.add_user("alice", "hash123", "admin")
        assert uid > 0
        user = tmp_db.get_user("alice")
        assert user["role"] == "admin"

    def test_list_users(self, tmp_db):
        tmp_db.add_user("bob", "h1")
        tmp_db.add_user("carol", "h2")
        users = tmp_db.get_users()
        assert len(users) == 2

    def test_remove_user(self, tmp_db):
        tmp_db.add_user("dave", "h")
        assert tmp_db.remove_user("dave") is True
        assert tmp_db.remove_user("dave") is False

    def test_get_nonexistent(self, tmp_db):
        assert tmp_db.get_user("ghost") is None


class TestExistingFaceDetection:
    """Verify original face-detection DB operations still work."""

    def test_scan_job_lifecycle(self, tmp_db):
        job_id = tmp_db.create_scan_job(100)
        assert job_id > 0
        tmp_db.update_scan_progress(job_id, 50, 10, 2)
        tmp_db.finish_scan_job(job_id)
        row = tmp_db.conn.execute("SELECT * FROM scan_jobs WHERE id = ?", (job_id,)).fetchone()
        assert row["status"] == "completed"
        assert row["processed_files"] == 50

    def test_person_and_match(self, tmp_db):
        tmp_db.ensure_person("Alice", 5)
        job_id = tmp_db.create_scan_job(1)
        tmp_db.add_match(job_id, "Alice", "/photo.jpg", "image", 0.95)
        matches = tmp_db.get_all_matches()
        assert len(matches) == 1
        assert matches[0]["person_name"] == "Alice"

    def test_processed_file_tracking(self, tmp_db):
        job_id = tmp_db.create_scan_job(1)
        assert not tmp_db.is_file_processed("/a.jpg")
        tmp_db.mark_file_processed("/a.jpg", job_id, file_hash="abc", file_size=100)
        assert tmp_db.is_file_processed("/a.jpg")
