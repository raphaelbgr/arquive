"""Tests for metadata extraction module."""

import tempfile
from pathlib import Path


class TestExtractMetadata:
    def test_nonexistent_file(self):
        from face_detect.metadata import extract_metadata
        result = extract_metadata("/nonexistent/file.jpg")
        assert result == {}

    def test_basic_text_file(self, tmp_path):
        from face_detect.metadata import extract_metadata
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        result = extract_metadata(str(f))
        assert result["name"] == "test.txt"
        assert result["extension"] == ".txt"
        assert result["size"] == 11
        assert "text" in result["mime_type"]

    def test_unknown_extension(self, tmp_path):
        from face_detect.metadata import extract_metadata
        f = tmp_path / "data.xyz123"
        f.write_bytes(b"\x00" * 100)
        result = extract_metadata(str(f))
        assert result["size"] == 100


class TestIPTVPlaylistParsing:
    def test_parse_m3u(self):
        from face_detect.iptv.playlist_manager import PlaylistManager
        content = """#EXTM3U
#EXTINF:-1 tvg-id="ch1" tvg-name="Channel 1" group-title="News" tvg-logo="http://logo.png",Channel One
http://example.com/stream1.m3u8
#EXTINF:-1 tvg-id="ch2" group-title="Sports",Channel Two
http://example.com/stream2.m3u8
"""
        channels = PlaylistManager._parse_m3u(content)
        assert len(channels) == 2
        assert channels[0]["name"] == "Channel One"
        assert channels[0]["tvg-id"] == "ch1"
        assert channels[0]["group-title"] == "News"
        assert channels[1]["url"] == "http://example.com/stream2.m3u8"

    def test_parse_empty_m3u(self):
        from face_detect.iptv.playlist_manager import PlaylistManager
        channels = PlaylistManager._parse_m3u("#EXTM3U\n")
        assert channels == []


class TestCredentialVault:
    def test_encrypt_decrypt_roundtrip(self):
        from face_detect.credential_vault import CredentialVault
        vault = CredentialVault()
        data = {"username": "admin", "password": "secret123", "host": "192.168.1.1"}
        encrypted = vault.encrypt(data)
        assert encrypted != str(data)
        decrypted = vault.decrypt(encrypted)
        assert decrypted == data

    def test_different_data_different_ciphertext(self):
        from face_detect.credential_vault import CredentialVault
        vault = CredentialVault()
        e1 = vault.encrypt({"a": "1"})
        e2 = vault.encrypt({"a": "2"})
        assert e1 != e2
