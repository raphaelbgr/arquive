"""M3U playlist parsing and management for IPTV.

Parses M3U/M3U8 playlists (from URL or local file) and stores channels
in the database.  Supports automatic refresh on configurable intervals.

Dependencies: requests, re (stdlib)
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

log = logging.getLogger(__name__)

# Regex for EXTINF line: #EXTINF:-1 tvg-id="..." tvg-name="..." ...
_EXTINF_RE = re.compile(
    r'#EXTINF:\s*-?\d+\s*'
    r'(?P<attrs>[^,]*),\s*'
    r'(?P<name>.*)',
)
_ATTR_RE = re.compile(r'(\w[\w-]*)="([^"]*)"')


class PlaylistManager:
    """Manages IPTV playlists and their channels."""

    def __init__(self, db: Any) -> None:
        self.db = db

    def add_playlist(
        self,
        url: str,
        name: str | None = None,
        epg_url: str | None = None,
        auto_refresh_hours: int = 24,
    ) -> int:
        """Add a new playlist and return its ID."""
        if not name:
            name = urlparse(url).netloc or "Untitled Playlist"
        with self.db._lock:
            cur = self.db.conn.execute(
                "INSERT INTO iptv_playlists (name, url, epg_url, auto_refresh_hours) "
                "VALUES (?, ?, ?, ?)",
                (name, url, epg_url, auto_refresh_hours),
            )
            self.db.conn.commit()
            return cur.lastrowid

    def refresh_playlist(self, playlist_id: int) -> int:
        """Re-fetch and parse a playlist.  Returns channel count."""
        row = self.db.conn.execute(
            "SELECT * FROM iptv_playlists WHERE id = ?", (playlist_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Playlist {playlist_id} not found")

        url = row["url"]
        try:
            content = self._fetch(url)
            channels = self._parse_m3u(content)
        except Exception as e:
            log.error("Failed to refresh playlist %d: %s", playlist_id, e)
            with self.db._lock:
                self.db.conn.execute(
                    "UPDATE iptv_playlists SET status = 'error', error_message = ? WHERE id = ?",
                    (str(e), playlist_id),
                )
                self.db.conn.commit()
            return 0

        # Detect EPG URL from playlist header
        epg_url = row["epg_url"]
        for line in content.split("\n")[:5]:
            match = re.search(r'url-tvg="([^"]+)"', line)
            if match and not epg_url:
                epg_url = match.group(1)
                break

        # Replace channels for this playlist
        with self.db._lock:
            self.db.conn.execute(
                "DELETE FROM iptv_channels WHERE playlist_id = ?", (playlist_id,)
            )
            for i, ch in enumerate(channels):
                self.db.conn.execute(
                    "INSERT INTO iptv_channels "
                    "(playlist_id, name, url, logo_url, group_title, tvg_id, tvg_name, tvg_language, sort_order) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        playlist_id,
                        ch["name"],
                        ch["url"],
                        ch.get("tvg-logo"),
                        ch.get("group-title"),
                        ch.get("tvg-id"),
                        ch.get("tvg-name"),
                        ch.get("tvg-language"),
                        i,
                    ),
                )
            self.db.conn.execute(
                "UPDATE iptv_playlists SET channel_count = ?, status = 'active', "
                "error_message = NULL, last_refreshed = datetime('now'), epg_url = ? "
                "WHERE id = ?",
                (len(channels), epg_url, playlist_id),
            )
            self.db.conn.commit()

        log.info("Playlist %d refreshed: %d channels", playlist_id, len(channels))
        return len(channels)

    def _fetch(self, url: str) -> str:
        """Fetch playlist content from URL."""
        import requests
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return resp.text

    @staticmethod
    def _parse_m3u(content: str) -> list[dict[str, str]]:
        """Parse M3U content into a list of channel dicts."""
        channels: list[dict[str, str]] = []
        lines = content.strip().split("\n")
        current_attrs: dict[str, str] = {}
        current_name = ""

        for line in lines:
            line = line.strip()
            if not line or line.startswith("#EXTM3U"):
                continue

            m = _EXTINF_RE.match(line)
            if m:
                current_name = m.group("name").strip()
                attrs_str = m.group("attrs")
                current_attrs = dict(_ATTR_RE.findall(attrs_str))
                continue

            if line.startswith("#"):
                continue

            # This is a URL line
            if current_name or current_attrs:
                channels.append({
                    "name": current_name or "Unknown",
                    "url": line,
                    **current_attrs,
                })
                current_attrs = {}
                current_name = ""

        return channels
