"""Report generator — CLI, JSON, and HTML output from results database."""

import json
import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, BaseLoader

from ..database import Database

log = logging.getLogger(__name__)


def format_timestamp(seconds: float) -> str:
    """Convert seconds to HH:MM:SS or MM:SS format."""
    if seconds is None:
        return ""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def generate_cli_report(db: Database) -> str:
    """Generate a text-based CLI report."""
    by_person = db.get_matches_by_person()
    stats = db.get_scan_stats()
    lines = []

    lines.append("=" * 70)
    lines.append("  FACE DETECTION REPORT")
    lines.append("=" * 70)

    if stats:
        lines.append(f"  Total files scanned: {stats.get('processed_files', 0)}")
        lines.append(f"  Files with matches:  {stats.get('matched_files', 0)}")
        lines.append(f"  Failed files:        {stats.get('failed_files', 0)}")
        lines.append("")

    if not by_person:
        lines.append("  No matches found.")
        return "\n".join(lines)

    for person_name, matches in sorted(by_person.items()):
        lines.append(f"\n  Person: {person_name}")
        lines.append(f"  {'─' * 50}")

        # Group matches by file
        by_file = {}
        for m in matches:
            fp = m["file_path"]
            if fp not in by_file:
                by_file[fp] = []
            by_file[fp].append(m)

        for file_path, file_matches in sorted(by_file.items()):
            fname = Path(file_path).name
            ft = file_matches[0]["file_type"]

            if ft == "video":
                time_ranges = []
                for m in file_matches:
                    start = format_timestamp(m.get("timestamp_start"))
                    end = format_timestamp(m.get("timestamp_end"))
                    conf = f"{m['confidence']:.2f}"
                    if start and end and start != end:
                        time_ranges.append(f"{start}-{end} ({conf})")
                    elif start:
                        time_ranges.append(f"{start} ({conf})")
                    else:
                        time_ranges.append(f"({conf})")
                times_str = ", ".join(time_ranges)
                lines.append(f"    [VIDEO] {fname}: {times_str}")
            else:
                best_conf = max(m["confidence"] for m in file_matches)
                lines.append(f"    [IMAGE] {fname} (confidence: {best_conf:.2f})")

        lines.append(f"    Total: {len(by_file)} file(s)")

    lines.append("\n" + "=" * 70)
    return "\n".join(lines)


def generate_json_report(db: Database, output_path: str):
    """Export full results as JSON."""
    data = db.export_json()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    log.info("JSON report saved to: %s", output_path)


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Face Detection Report</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f0f0f; color: #e0e0e0; padding: 2rem;
        }
        h1 { color: #fff; margin-bottom: 0.5rem; font-size: 1.8rem; }
        .stats {
            color: #888; margin-bottom: 2rem; font-size: 0.9rem;
        }
        .person-card {
            background: #1a1a1a; border-radius: 12px; padding: 1.5rem;
            margin-bottom: 1.5rem; border: 1px solid #2a2a2a;
        }
        .person-card h2 {
            color: #4fc3f7; margin-bottom: 1rem; font-size: 1.3rem;
            border-bottom: 1px solid #333; padding-bottom: 0.5rem;
        }
        .match-grid {
            display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 1rem;
        }
        .match-item {
            background: #222; border-radius: 8px; overflow: hidden;
            border: 1px solid #333; transition: border-color 0.2s;
        }
        .match-item:hover { border-color: #4fc3f7; }
        .match-item img {
            width: 100%; height: 180px; object-fit: cover;
            background: #111;
        }
        .match-item .no-thumb {
            width: 100%; height: 180px; background: #111;
            display: flex; align-items: center; justify-content: center;
            color: #555; font-size: 0.8rem;
        }
        .match-info {
            padding: 0.75rem; font-size: 0.85rem;
        }
        .match-info .filename {
            color: #ccc; font-weight: 500; word-break: break-all;
            margin-bottom: 0.3rem;
        }
        .match-info .details { color: #888; }
        .match-info .confidence {
            display: inline-block; padding: 2px 8px; border-radius: 4px;
            font-size: 0.75rem; font-weight: 600;
        }
        .conf-high { background: #1b5e20; color: #a5d6a7; }
        .conf-mid { background: #e65100; color: #ffcc80; }
        .conf-low { background: #b71c1c; color: #ef9a9a; }
        .file-type {
            display: inline-block; padding: 2px 6px; border-radius: 3px;
            font-size: 0.7rem; font-weight: 600; margin-right: 0.5rem;
        }
        .type-video { background: #1a237e; color: #9fa8da; }
        .type-image { background: #004d40; color: #80cbc4; }
        .summary { margin-bottom: 0.5rem; color: #aaa; font-size: 0.9rem; }

        /* Lightbox overlay */
        .lightbox {
            display: none; position: fixed; top: 0; left: 0;
            width: 100%; height: 100%; background: rgba(0,0,0,0.92);
            z-index: 1000; justify-content: center; align-items: center;
            flex-direction: column; cursor: pointer;
        }
        .lightbox.active { display: flex; }
        .lightbox img {
            max-width: 92vw; max-height: 80vh; object-fit: contain;
            border-radius: 8px; box-shadow: 0 4px 40px rgba(0,0,0,0.6);
        }
        .lightbox .lb-info {
            color: #ccc; margin-top: 1rem; text-align: center;
            font-size: 0.9rem; max-width: 90vw; word-break: break-all;
        }
        .lightbox .lb-info .lb-path {
            color: #888; font-size: 0.8rem; margin-top: 0.3rem;
        }
        .lightbox .lb-close {
            position: absolute; top: 1.5rem; right: 2rem;
            color: #888; font-size: 2rem; cursor: pointer;
            transition: color 0.2s; line-height: 1;
        }
        .lightbox .lb-close:hover { color: #fff; }
        .lightbox .lb-nav {
            position: absolute; top: 50%; transform: translateY(-50%);
            color: #666; font-size: 3rem; cursor: pointer;
            transition: color 0.2s; user-select: none; padding: 0 1rem;
        }
        .lightbox .lb-nav:hover { color: #fff; }
        .lightbox .lb-prev { left: 1rem; }
        .lightbox .lb-next { right: 1rem; }
        .match-item { cursor: pointer; }
    </style>
</head>
<body>
    <!-- Lightbox overlay -->
    <div class="lightbox" id="lightbox" onclick="closeLightbox(event)">
        <span class="lb-close" onclick="closeLightbox(event)">&times;</span>
        <span class="lb-nav lb-prev" onclick="navLightbox(event, -1)">&#8249;</span>
        <span class="lb-nav lb-next" onclick="navLightbox(event, 1)">&#8250;</span>
        <img id="lb-img" src="" alt="">
        <div class="lb-info">
            <div id="lb-filename"></div>
            <div class="lb-path" id="lb-path"></div>
        </div>
    </div>

    <h1>Face Detection Report</h1>
    <div class="stats">
        {% if stats %}
        Scanned {{ stats.processed_files or 0 }} files |
        {{ stats.matched_files or 0 }} with matches |
        {{ stats.failed_files or 0 }} failed
        {% endif %}
    </div>

    {% for person_name, matches in by_person.items() | sort %}
    <div class="person-card">
        <h2>{{ person_name }}</h2>
        <p class="summary">Found in {{ matches | groupby('file_path') | list | length }} file(s)</p>
        <div class="match-grid">
            {% for match in matches %}
            <div class="match-item" onclick="openLightbox(this)"
                 data-src="{{ match.file_path | file_uri }}"
                 data-filename="{{ match.file_path | basename }}"
                 data-fullpath="{{ match.file_path }}">
                {% if match.thumbnail_path and thumb_exists(match.thumbnail_path) %}
                <img src="{{ thumb_rel(match.thumbnail_path) }}" alt="{{ person_name }}">
                {% else %}
                <div class="no-thumb">No thumbnail</div>
                {% endif %}
                <div class="match-info">
                    <div class="filename">
                        <span class="file-type {{ 'type-video' if match.file_type == 'video' else 'type-image' }}">
                            {{ match.file_type | upper }}
                        </span>
                        {{ match.file_path | basename }}
                    </div>
                    <div class="details">
                        {% if match.file_type == 'video' and match.timestamp_start is not none %}
                        Time: {{ match.timestamp_start | ts }} - {{ match.timestamp_end | ts }}
                        <br>
                        {% endif %}
                        Confidence:
                        <span class="confidence {{ 'conf-high' if match.confidence >= 0.5 else 'conf-mid' if match.confidence >= 0.4 else 'conf-low' }}">
                            {{ "%.1f%%" | format(match.confidence * 100) }}
                        </span>
                    </div>
                </div>
            </div>
            {% endfor %}
        </div>
    </div>
    {% endfor %}

    {% if not by_person %}
    <div class="person-card">
        <h2>No matches found</h2>
        <p class="summary">No faces from the reference set were detected in the scanned media.</p>
    </div>
    {% endif %}

    <script>
    // Lightbox — shows full original image on click
    const allItems = document.querySelectorAll('.match-item[data-src]');
    let currentIdx = -1;

    function openLightbox(el) {
        const idx = Array.from(allItems).indexOf(el);
        if (idx === -1) return;
        showAt(idx);
    }

    function showAt(idx) {
        if (idx < 0 || idx >= allItems.length) return;
        currentIdx = idx;
        const item = allItems[idx];
        const lb = document.getElementById('lightbox');
        const img = document.getElementById('lb-img');
        const fname = document.getElementById('lb-filename');
        const fpath = document.getElementById('lb-path');

        img.src = item.dataset.src;
        fname.textContent = item.dataset.filename;
        fpath.textContent = item.dataset.fullpath;
        lb.classList.add('active');
        document.body.style.overflow = 'hidden';
    }

    function closeLightbox(e) {
        // Don't close when clicking nav arrows or image
        if (e.target.classList.contains('lb-nav') ||
            e.target.classList.contains('lb-prev') ||
            e.target.classList.contains('lb-next')) return;
        if (e.target.id === 'lb-img') return;
        document.getElementById('lightbox').classList.remove('active');
        document.body.style.overflow = '';
        currentIdx = -1;
    }

    function navLightbox(e, dir) {
        e.stopPropagation();
        const next = currentIdx + dir;
        if (next >= 0 && next < allItems.length) showAt(next);
    }

    // Keyboard navigation
    document.addEventListener('keydown', (e) => {
        if (currentIdx === -1) return;
        if (e.key === 'Escape') {
            document.getElementById('lightbox').classList.remove('active');
            document.body.style.overflow = '';
            currentIdx = -1;
        } else if (e.key === 'ArrowLeft') {
            navLightbox(e, -1);
        } else if (e.key === 'ArrowRight') {
            navLightbox(e, 1);
        }
    });
    </script>
</body>
</html>"""


def generate_html_report(db: Database, output_path: str, thumbnails_dir: str):
    """Generate an HTML report with thumbnails."""
    by_person = db.get_matches_by_person()
    stats = db.get_scan_stats()
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    thumbs = Path(thumbnails_dir)

    env = Environment(loader=BaseLoader())
    env.filters["ts"] = format_timestamp
    env.filters["basename"] = lambda p: Path(p).name
    env.filters["file_uri"] = lambda p: "file:///" + Path(p).as_posix()

    def thumb_exists(path):
        return path and Path(path).exists()

    def thumb_rel(path):
        try:
            return Path(path).relative_to(output.parent).as_posix()
        except ValueError:
            return path

    template = env.from_string(HTML_TEMPLATE)
    html = template.render(
        by_person=by_person,
        stats=stats,
        thumb_exists=thumb_exists,
        thumb_rel=thumb_rel,
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    log.info("HTML report saved to: %s", output_path)
