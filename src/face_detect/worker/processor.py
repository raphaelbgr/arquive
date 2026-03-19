"""Media processor — handles face detection in images and videos."""

import hashlib
import logging
from pathlib import Path

import cv2
import faiss
import numpy as np
from insightface.app import FaceAnalysis

from ..config import Config, IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
from ..gpu import get_providers

log = logging.getLogger(__name__)


class MediaProcessor:
    """Processes images and videos for face detection using InsightFace + FAISS."""

    def __init__(self, config: Config, faiss_index, labels: list, thumbnails_dir: str):
        self.config = config
        self.index = faiss_index
        self.labels = labels
        self.threshold = config.recognition.threshold
        self.thumbnails_dir = Path(thumbnails_dir)
        self.thumbnails_dir.mkdir(parents=True, exist_ok=True)
        self.app = None
        self._batch_size = config.video.batch_size

    def init_model(self):
        """Initialize InsightFace model for detection + embedding.

        Only loads detection + recognition models (skips landmarks, gender/age)
        for faster processing.
        """
        if self.app is not None:
            return
        providers = get_providers()
        log.info("Initializing InsightFace model: %s (providers: %s)",
                 self.config.recognition.model, providers)
        self.app = FaceAnalysis(
            name=self.config.recognition.model,
            providers=providers,
            allowed_modules=["detection", "recognition"],
        )
        det_w, det_h = self.config.recognition.det_size
        self.app.prepare(ctx_id=0, det_size=(det_w, det_h))
        log.info("InsightFace model ready (detection + recognition only)")

    def process_file(self, file_path: str) -> dict:
        """Process a single image or video file.

        Returns:
            {
                "file_path": str,
                "file_type": "image" | "video",
                "file_hash": str,
                "matches": [
                    {
                        "person_name": str,
                        "confidence": float,
                        "timestamp_start": float | None,
                        "timestamp_end": float | None,
                        "thumbnail_path": str | None,
                    }
                ]
            }
        """
        self.init_model()
        path = Path(file_path)
        suffix = path.suffix.lower()

        if suffix in IMAGE_EXTENSIONS:
            return self._process_image(file_path)
        elif suffix in VIDEO_EXTENSIONS:
            return self._process_video(file_path)
        else:
            log.warning("Unsupported file type: %s", file_path)
            return {"file_path": file_path, "file_type": "unknown", "file_hash": "", "matches": []}

    def _file_hash(self, file_path: str) -> str:
        """Compute a fast partial hash (first 64KB) for dedup."""
        h = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                h.update(f.read(65536))
        except OSError:
            return ""
        return h.hexdigest()

    def _search_faces(self, embeddings: list) -> list:
        """Search FAISS index for matching persons.

        Returns list of (person_name, confidence) for each embedding that matches.
        """
        if not embeddings:
            return []

        query = np.array(embeddings, dtype=np.float32)
        faiss.normalize_L2(query)

        # Search top-1 neighbor per embedding
        scores, indices = self.index.search(query, 1)

        results = []
        for i, (score, idx) in enumerate(zip(scores, indices)):
            s = float(score[0])
            ix = int(idx[0])
            if s >= self.threshold and ix >= 0:
                results.append((self.labels[ix], s, i))

        return results

    def _process_image(self, file_path: str) -> dict:
        """Process a single image."""
        img = cv2.imread(file_path)
        if img is None:
            log.warning("Failed to read image: %s", file_path)
            return {"file_path": file_path, "file_type": "image", "file_hash": "", "matches": []}

        faces = self.app.get(img)
        if not faces:
            return {
                "file_path": file_path,
                "file_type": "image",
                "file_hash": self._file_hash(file_path),
                "matches": [],
            }

        embeddings = [f.normed_embedding for f in faces]
        search_results = self._search_faces(embeddings)

        # Deduplicate by person (keep highest confidence)
        best_by_person = {}
        for person_name, confidence, face_idx in search_results:
            if person_name not in best_by_person or confidence > best_by_person[person_name][0]:
                best_by_person[person_name] = (confidence, face_idx)

        matches = []
        for person_name, (confidence, face_idx) in best_by_person.items():
            face = faces[face_idx]
            thumb_path = self._save_thumbnail(img, face, file_path, person_name)
            matches.append({
                "person_name": person_name,
                "confidence": confidence,
                "timestamp_start": None,
                "timestamp_end": None,
                "thumbnail_path": thumb_path,
            })

        return {
            "file_path": file_path,
            "file_type": "image",
            "file_hash": self._file_hash(file_path),
            "matches": matches,
        }

    def _process_video(self, file_path: str) -> dict:
        """Process a video file — sample frames, detect faces, group into time ranges."""
        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            log.warning("Failed to open video: %s", file_path)
            return {"file_path": file_path, "file_type": "video", "file_hash": "", "matches": []}

        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if fps <= 0:
            fps = 30.0

        sample_interval = max(1, int(fps / self.config.video.sample_fps))
        merge_gap = self.config.video.merge_gap_seconds

        log.info("Processing video: %s (%.1f fps, %d frames, sampling every %d frames)",
                 file_path, fps, total_frames, sample_interval)

        # Collect all frame-level detections
        # {person_name: [(timestamp, confidence, frame, face)]}
        person_detections = {}
        frame_idx = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % sample_interval == 0:
                timestamp = frame_idx / fps
                faces = self.app.get(frame)

                if faces:
                    embeddings = [f.normed_embedding for f in faces]
                    search_results = self._search_faces(embeddings)

                    for person_name, confidence, face_idx in search_results:
                        if person_name not in person_detections:
                            person_detections[person_name] = []
                        person_detections[person_name].append(
                            (timestamp, confidence, frame.copy(), faces[face_idx])
                        )

            frame_idx += 1

        cap.release()

        # Group detections into time ranges and pick best thumbnail
        matches = []
        for person_name, detections in person_detections.items():
            ranges = self._merge_detections(detections, merge_gap)
            for time_range in ranges:
                thumb_path = self._save_thumbnail(
                    time_range["best_frame"], time_range["best_face"],
                    file_path, person_name, time_range["start"]
                )
                matches.append({
                    "person_name": person_name,
                    "confidence": time_range["best_confidence"],
                    "timestamp_start": time_range["start"],
                    "timestamp_end": time_range["end"],
                    "thumbnail_path": thumb_path,
                })

        log.info("Video %s: %d person matches across %d ranges",
                 Path(file_path).name, len(person_detections), len(matches))

        return {
            "file_path": file_path,
            "file_type": "video",
            "file_hash": self._file_hash(file_path),
            "matches": matches,
        }

    def _merge_detections(self, detections: list, merge_gap: float) -> list:
        """Merge consecutive detections into time ranges.

        Args:
            detections: [(timestamp, confidence, frame, face)]
            merge_gap: max gap in seconds to merge

        Returns:
            [{"start", "end", "best_confidence", "best_frame", "best_face"}]
        """
        if not detections:
            return []

        detections.sort(key=lambda d: d[0])
        ranges = []
        current = {
            "start": detections[0][0],
            "end": detections[0][0],
            "best_confidence": detections[0][1],
            "best_frame": detections[0][2],
            "best_face": detections[0][3],
        }

        for ts, conf, frame, face in detections[1:]:
            if ts - current["end"] <= merge_gap:
                # Extend current range
                current["end"] = ts
                if conf > current["best_confidence"]:
                    current["best_confidence"] = conf
                    current["best_frame"] = frame
                    current["best_face"] = face
            else:
                # Start new range
                ranges.append(current)
                current = {
                    "start": ts,
                    "end": ts,
                    "best_confidence": conf,
                    "best_frame": frame,
                    "best_face": face,
                }

        ranges.append(current)
        return ranges

    def _save_thumbnail(self, img, face, source_path: str,
                        person_name: str, timestamp: float = None) -> str:
        """Save a thumbnail of the detected face with some context.

        Returns the thumbnail file path.
        """
        bbox = face.bbox.astype(int)
        x1, y1, x2, y2 = bbox
        h, w = img.shape[:2]

        # Add 40% padding around the face for context
        face_w = x2 - x1
        face_h = y2 - y1
        pad_x = int(face_w * 0.4)
        pad_y = int(face_h * 0.4)
        x1 = max(0, x1 - pad_x)
        y1 = max(0, y1 - pad_y)
        x2 = min(w, x2 + pad_x)
        y2 = min(h, y2 + pad_y)

        crop = img[y1:y2, x1:x2]
        if crop.size == 0:
            return ""

        # Generate filename
        source_stem = Path(source_path).stem
        ts_str = f"_{timestamp:.1f}s" if timestamp is not None else ""
        thumb_name = f"{person_name}_{source_stem}{ts_str}.jpg"
        thumb_path = self.thumbnails_dir / thumb_name

        cv2.imwrite(str(thumb_path), crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return str(thumb_path)
