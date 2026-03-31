# Arquive

A self-hosted personal media archive and streaming server with face recognition, AI descriptions, live TV, and distributed GPU transcoding.

## Why This Exists

Cloud photo services (Google Photos, iCloud, Amazon Photos) do face recognition, smart search, and timeline views well — but they require uploading your entire personal archive to servers you don't control, with storage limits, pricing changes, and privacy trade-offs that only get worse over time.

At the same time, self-hosted media servers like Plex and Jellyfin handle streaming well but treat your photos as dumb files. They have no concept of "show me everything with this person in it" and no AI-powered understanding of what's in your media.

There was no single tool that combined both: private, self-hosted, face-aware, streamable from any device.

Arquive is that tool.

### Pain Points Solved

- **Privacy without sacrifice** — face recognition and AI search run locally on your own hardware, never on third-party servers.
- **No storage caps** — index terabytes across local drives, network shares (SMB/CIFS), FTP, and SSH remotes without hitting a paywall.
- **Scattered media, unified view** — sources from multiple machines and network shares appear as a single timeline, organized chronologically with EXIF-accurate dates.
- **People search that works offline** — FAISS-backed face embeddings let you find every photo and video clip of a person without sending a single image to the cloud.
- **AI descriptions without cloud APIs** — uses a local Ollama model (Qwen2.5-VL by default) to generate searchable captions for photos and videos.
- **Streaming you already paid for (IPTV)** — bring your own M3U playlist and watch live TV alongside your archive, with EPG, recording, and a channel guide.
- **GPU fleet transcoding** — distribute re-encoding jobs across multiple GPU machines on your LAN; idle hardware earns its keep.
- **One binary, no Docker maze** — runs as a single Python process with a React frontend served from the same port.

---

## Features

| Area | Capability |
|------|-----------|
| Face recognition | InsightFace + FAISS, distributed across GPU workers |
| Media sources | Local disk, SMB/CIFS, FTP, SSH |
| File types | Photos, videos, audio, documents |
| Web UI | React SPA — timeline, people, folders, documents, live TV |
| Streaming | In-browser HLS with GPU-accelerated transcoding cache |
| IPTV | M3U playlists, XMLTV EPG, stream proxy, recording |
| DLNA | UPnP/DLNA server for smart TVs and media players |
| AI | Local VLM captions and video keyframe descriptions |
| Auth | JWT sessions, simple password or user-account mode |
| Reports | HTML, JSON, and CLI face recognition reports |

---

## Quick Start

```bash
pip install -e .

# 1. Point config at your media
cp config.example.yaml config.yaml
# edit config.yaml: set media_dirs, faces_dir

# 2. Build the face index
face-detect index

# 3. Run a scan
face-detect scan

# 4. Start the server (React UI + API on port 64531)
face-detect serve
```

Open `http://localhost:64531` in your browser.

---

## Configuration

All settings live in `config.yaml`. Key sections:

```yaml
media_dirs:
  - /mnt/photos
  - //nas/media          # SMB share (Windows UNC)

faces_dir: ./recognition/faces   # one subfolder per person

server:
  port: 64531

auth:
  sec_level: simple-password   # or: user-account, forever

ai:
  enabled: true
  model: qwen2.5-vl
  endpoint: http://localhost:11434/api/generate

cache:
  limit_gb: 20.0

iptv:
  enabled: true
```

---

## Architecture

```
face-detect serve
  ├── Flask API + React frontend  (port 64531)
  ├── Coordinator                 (port 8600)  — task scheduler
  ├── Workers                     (GPU nodes)  — face detection, transcoding
  └── Indexer                     — FAISS face embedding index
```

Workers run on remote machines via SSH. The coordinator distributes scan tasks based on file locality — each worker processes files it can access directly, minimising network transfer.

---

## CLI Commands

```
face-detect index          Build FAISS index from reference face images
face-detect scan           Run face detection across all media sources
face-detect serve          Start the web server and API
face-detect worker         Start a detection worker on this machine
face-detect report         Generate HTML / JSON report
face-detect describe       Run AI captioning on un-described media
face-detect cache          Manage the transcoding cache
face-detect fleet          Show GPU worker status
face-detect iptv           Manage IPTV playlists and recordings
face-detect user           Manage user accounts
face-detect set-password   Change the server password
```

---

## Requirements

- Python 3.10+
- [InsightFace](https://github.com/deepinsight/insightface) + ONNX Runtime
- FAISS (`faiss-cpu` or `faiss-gpu`)
- FFmpeg (for transcoding and video thumbnails)
- Node 18+ (to build the React frontend)
- Ollama (optional, for AI descriptions)

GPU acceleration uses CUDA (NVIDIA) or CoreML (Apple Silicon) automatically when available.

---

## License

MIT
