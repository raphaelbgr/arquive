"""XMLTV EPG (Electronic Program Guide) fetching and parsing.

Parses XMLTV XML data into the ``epg_programs`` table.  Supports
multiple EPG sources with independent refresh intervals.  Channel
matching uses ``tvg_id``, ``tvg_name``, or fuzzy name matching.

Dependencies: xml.etree.ElementTree (stdlib), requests
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any

log = logging.getLogger(__name__)


class EPGService:
    """Fetches and parses XMLTV EPG data."""

    def __init__(self, db: Any) -> None:
        self.db = db

    def refresh_all(self) -> None:
        """Refresh all active EPG sources."""
        rows = self.db.conn.execute(
            "SELECT * FROM epg_sources WHERE status = 'active'"
        ).fetchall()
        for source in rows:
            try:
                self.refresh_source(source["id"], source["url"])
            except Exception:
                log.exception("Failed to refresh EPG source %s", source["url"])

    def refresh_source(self, source_id: int, url: str) -> int:
        """Fetch and parse a single EPG source.  Returns program count."""
        import requests

        resp = requests.get(url, timeout=60)
        resp.raise_for_status()

        programs = self._parse_xmltv(resp.content, url)

        # Clear old programs from this source and insert new ones
        with self.db._lock:
            self.db.conn.execute(
                "DELETE FROM epg_programs WHERE epg_source = ?", (url,)
            )
            for p in programs:
                self.db.conn.execute(
                    "INSERT INTO epg_programs "
                    "(channel_id, title, subtitle, description, category, "
                    "start_time, end_time, duration_minutes, season, episode, "
                    "year, rating, star_rating, poster_url, credits_json, "
                    "language, is_new, is_live, epg_source) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        p["channel_id"],
                        p["title"],
                        p.get("subtitle"),
                        p.get("description"),
                        p.get("category"),
                        p["start_time"],
                        p["end_time"],
                        p.get("duration_minutes"),
                        p.get("season"),
                        p.get("episode"),
                        p.get("year"),
                        p.get("rating"),
                        p.get("star_rating"),
                        p.get("poster_url"),
                        p.get("credits_json"),
                        p.get("language"),
                        p.get("is_new", False),
                        p.get("is_live", False),
                        url,
                    ),
                )

            # Update source metadata
            channel_ids = {p["channel_id"] for p in programs}
            self.db.conn.execute(
                "UPDATE epg_sources SET last_fetched = datetime('now'), "
                "channel_count = ?, program_count = ? WHERE id = ?",
                (len(channel_ids), len(programs), source_id),
            )
            self.db.conn.commit()

        log.info("EPG source %s: %d programs for %d channels", url, len(programs), len(channel_ids))
        return len(programs)

    @staticmethod
    def _parse_xmltv(xml_data: bytes, source_url: str) -> list[dict[str, Any]]:
        """Parse XMLTV XML into a list of program dicts."""
        programs: list[dict[str, Any]] = []

        root = ET.fromstring(xml_data)
        for prog_el in root.findall("programme"):
            channel_id = prog_el.get("channel", "")
            start_str = prog_el.get("start", "")
            stop_str = prog_el.get("stop", "")

            start_time = _parse_xmltv_datetime(start_str)
            end_time = _parse_xmltv_datetime(stop_str)

            title_el = prog_el.find("title")
            title = title_el.text if title_el is not None and title_el.text else "Unknown"

            subtitle_el = prog_el.find("sub-title")
            desc_el = prog_el.find("desc")
            category_el = prog_el.find("category")
            icon_el = prog_el.find("icon")

            duration_minutes = None
            if start_time and end_time:
                try:
                    dt_start = datetime.fromisoformat(start_time)
                    dt_end = datetime.fromisoformat(end_time)
                    duration_minutes = int((dt_end - dt_start).total_seconds() / 60)
                except Exception:
                    pass

            # Episode numbering (xmltv_ns or onscreen)
            season, episode = None, None
            for ep_el in prog_el.findall("episode-num"):
                system = ep_el.get("system", "")
                if system == "xmltv_ns" and ep_el.text:
                    parts = ep_el.text.split(".")
                    if len(parts) >= 2:
                        try:
                            season = int(parts[0]) + 1
                            episode = int(parts[1].split("/")[0]) + 1
                        except (ValueError, IndexError):
                            pass

            programs.append({
                "channel_id": channel_id,
                "title": title,
                "subtitle": subtitle_el.text if subtitle_el is not None else None,
                "description": desc_el.text if desc_el is not None else None,
                "category": category_el.text if category_el is not None else None,
                "start_time": start_time,
                "end_time": end_time,
                "duration_minutes": duration_minutes,
                "season": season,
                "episode": episode,
                "poster_url": icon_el.get("src") if icon_el is not None else None,
            })

        return programs


def _parse_xmltv_datetime(s: str) -> str | None:
    """Parse XMLTV datetime format (YYYYMMDDHHmmss +HHMM) to ISO 8601."""
    if not s:
        return None
    try:
        # Strip timezone offset for simplicity, store as-is
        s = s.strip()
        dt_part = s[:14]
        dt = datetime.strptime(dt_part, "%Y%m%d%H%M%S")
        # Preserve timezone offset if present
        tz = s[14:].strip() if len(s) > 14 else ""
        if tz:
            return dt.strftime("%Y-%m-%dT%H:%M:%S") + tz
        return dt.isoformat()
    except Exception:
        return s
