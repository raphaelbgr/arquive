"""Channel organization, favorites, and search for IPTV.

Provides convenience queries over the iptv_channels and custom_streams
tables — grouping, favorites, search, and ordering.

Dependencies: sqlite3 (via Database)
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


class ChannelManager:
    """High-level channel queries and management."""

    def __init__(self, db: Any) -> None:
        self.db = db

    def get_channels(
        self,
        playlist_id: int | None = None,
        group: str | None = None,
        search: str | None = None,
        favorites_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM iptv_channels WHERE 1=1"
        params: list[Any] = []
        if playlist_id is not None:
            query += " AND playlist_id = ?"
            params.append(playlist_id)
        if group:
            query += " AND group_title = ?"
            params.append(group)
        if favorites_only:
            query += " AND is_favorite = 1"
        if search:
            query += " AND name LIKE ?"
            params.append(f"%{search}%")
        query += " ORDER BY sort_order LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self.db.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_groups(self) -> list[dict[str, Any]]:
        """Return distinct channel groups with counts."""
        rows = self.db.conn.execute(
            "SELECT group_title, COUNT(*) as count FROM iptv_channels "
            "WHERE group_title IS NOT NULL GROUP BY group_title ORDER BY group_title"
        ).fetchall()
        return [dict(r) for r in rows]

    def toggle_favorite(self, channel_id: int) -> bool:
        """Toggle favorite status.  Returns new state."""
        row = self.db.conn.execute(
            "SELECT is_favorite FROM iptv_channels WHERE id = ?", (channel_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Channel {channel_id} not found")
        new_state = not bool(row["is_favorite"])
        with self.db._lock:
            self.db.conn.execute(
                "UPDATE iptv_channels SET is_favorite = ? WHERE id = ?",
                (new_state, channel_id),
            )
            self.db.conn.commit()
        return new_state

    def get_custom_streams(self) -> list[dict[str, Any]]:
        rows = self.db.conn.execute(
            "SELECT * FROM custom_streams ORDER BY name"
        ).fetchall()
        return [dict(r) for r in rows]

    def add_custom_stream(self, name: str, url: str, category: str | None = None) -> int:
        with self.db._lock:
            cur = self.db.conn.execute(
                "INSERT INTO custom_streams (name, url, category) VALUES (?, ?, ?)",
                (name, url, category),
            )
            self.db.conn.commit()
            return cur.lastrowid
