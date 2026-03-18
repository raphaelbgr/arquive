# Face Detection & Recognition System — Design Spec

**Date:** 2026-03-18
**Status:** Approved

## Overview

A distributed face recognition system that scans large media archives (terabytes of photos and videos) to find which files contain specific people. Uses InsightFace (buffalo_l / ArcFace) for state-of-the-art accuracy (99.86% LFW), with work distributed across multiple GPU-equipped machines.

## Input

- Reference faces: `recognition/faces/<person-name>/` — one folder per person, containing 1+ photos of that person
- Media directories: configured list of local and network paths containing images and videos

## Output

- SQLite database with all match results
- JSON export of full results
- CLI summary report
- HTML report with thumbnails, timestamps, and browseable person cards

## Machines

| Machine | GPU | VRAM | Role |
|---------|-----|------|------|
| Windows Desktop (192.168.7.101) | RTX 3080 Ti + GTX 1060 | 12GB + 6GB | Coordinator + Primary Worker |
| Avell (192.168.7.103) | RTX 3050 | ~4-8GB | Remote Worker |
| Mac Mini M4 (192.168.7.102) | Apple Silicon (ANE) | Unified | Remote Worker |

## Architecture

```
Coordinator (Desktop :8600)
├── Face Indexer — builds FAISS index from reference faces
├── Task Scheduler — walks media dirs, creates tasks, assigns locality-aware
├── HTTP API — serves tasks to workers, collects results
├── Results Collector — SQLite + JSON + HTML report generator
└── Local Worker (3080 Ti + 1060)

Remote Workers (Avell, Mac Mini)
├── Pull tasks from coordinator via HTTP
├── Download FAISS index on startup
├── Process images/videos → report matches
└── Platform-adaptive: CUDA (NVIDIA) or CoreML (Mac)
```

## Components

### Face Indexer
- Reads reference face folders
- InsightFace buffalo_l extracts 512-dim embeddings per face
- Averages multiple embeddings per person
- Builds FAISS IndexFlatIP (cosine similarity)
- Serializes index.faiss + labels.json to disk

### Task Scheduler
- Recursive walk of configured media directories
- One task per file (images: jpg/png/webp/bmp/tiff, videos: mp4/mkv/avi/mov/webm)
- Each task: file_path, file_type, locality, status (pending/assigned/done/failed)
- Locality-first assignment based on worker mount points
- Re-queues tasks after 300s timeout if worker doesn't report back

### Worker
- Pulls tasks via `GET /task?worker=<name>&mounts=<paths>`
- Loads FAISS index (downloaded once from coordinator)
- Images: detect → embed → FAISS search → report
- Videos: sample frames (default 2/sec) → batch 16-32 frames → detect → embed → search → group into time ranges → extract best thumbnail per range
- Reports via `POST /result`
- Platform-adaptive: onnxruntime-gpu (CUDA) or onnxruntime (CoreML)

### HTTP API (port 8600)
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/index` | GET | Download FAISS index + labels |
| `/task` | GET | Pull next task (locality hint) |
| `/result` | POST | Submit match results |
| `/progress` | GET | Scan progress stats |
| `/health` | GET | Worker heartbeat |

### Results & Reports
- SQLite tables: persons, matches, scan_jobs
- JSON: full structured export
- CLI: summary table per person with file list and timestamps
- HTML: person cards, media grid, clickable thumbnails

## Video Processing Pipeline

1. OpenCV VideoCapture → sample every N frames (default 2/sec)
2. Batch frames into groups of 16-32 (VRAM dependent)
3. InsightFace app.get() per frame → bounding boxes + embeddings
4. FAISS search each embedding → person matches with confidence
5. Group consecutive matches into time ranges (merge gap: 3 seconds)
6. Pick highest-confidence frame per range → extract thumbnail
7. Report: [{person, start, end, confidence, thumbnail_path}]

## Configuration

`config.yaml` at project root controls all settings:
- faces_dir, media_dirs
- recognition: model, det_size, threshold (default 0.45, presets available)
- video: sample_fps, batch_size, merge_gap_seconds
- coordinator: host, port, task_timeout
- workers: list with name, host, ssh_alias, gpu type
- output: db_path, thumbnails_dir, json_path, html_path

## Error Handling

- Worker crash: task re-queued after timeout
- Corrupt media file: logged as failed, skipped
- Network path unavailable: task stays pending, reassigned to worker with access
- GPU OOM: worker auto-reduces batch size and retries
- Duplicate scans: file hash tracked in SQLite, skippable on re-run

## Python Environment

- Python 3.11 (3.14 incompatible with InsightFace/ONNX)
- Key deps: insightface, onnxruntime-gpu, faiss-cpu, opencv-python, flask, pyyaml, numpy, jinja2

## CLI Interface

```bash
face-detect index                    # Build FAISS index from reference faces
face-detect scan                     # Start coordinator + local worker
face-detect scan --distributed       # Also SSH-bootstrap remote workers
face-detect worker --coordinator IP  # Run as remote worker
face-detect report                   # Generate reports from results DB
face-detect report --format html     # Specific format
face-detect status                   # Show scan progress
```
