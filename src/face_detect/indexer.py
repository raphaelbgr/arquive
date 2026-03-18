"""Face Indexer — builds FAISS index from reference face images."""

import json
import logging
from pathlib import Path

import cv2
import faiss
import numpy as np
from insightface.app import FaceAnalysis

from .config import Config
from .gpu import get_providers

log = logging.getLogger(__name__)


class FaceIndexer:
    """Loads reference faces from disk, generates embeddings, builds FAISS index."""

    def __init__(self, config: Config):
        self.config = config
        self.faces_dir = Path(config.faces_dir)
        self.app = None
        self.index = None
        self.labels = []  # parallel list: labels[i] = person name for embedding i
        self.person_stats = {}  # person_name -> {count, avg_embedding}

    def _init_model(self):
        """Initialize InsightFace model."""
        if self.app is not None:
            return
        providers = get_providers()
        log.info("Initializing InsightFace model: %s (providers: %s)",
                 self.config.recognition.model, providers)
        self.app = FaceAnalysis(name=self.config.recognition.model, providers=providers)
        det_w, det_h = self.config.recognition.det_size
        self.app.prepare(ctx_id=0, det_size=(det_w, det_h))
        log.info("InsightFace model ready")

    def build_index(self) -> tuple:
        """Build FAISS index from all reference faces.

        Returns:
            (faiss.Index, list of label strings, dict of person stats)
        """
        self._init_model()

        if not self.faces_dir.exists():
            raise FileNotFoundError(f"Faces directory not found: {self.faces_dir}")

        all_embeddings = []
        self.labels = []
        self.person_stats = {}

        person_dirs = sorted([
            d for d in self.faces_dir.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        ])

        if not person_dirs:
            raise ValueError(f"No person folders found in {self.faces_dir}")

        log.info("Found %d person(s) to index", len(person_dirs))

        for person_dir in person_dirs:
            person_name = person_dir.name
            person_embeddings = []

            image_files = sorted([
                f for f in person_dir.iterdir()
                if f.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}
            ])

            if not image_files:
                log.warning("No images found for person: %s", person_name)
                continue

            for img_path in image_files:
                img = cv2.imread(str(img_path))
                if img is None:
                    log.warning("Failed to read image: %s", img_path)
                    continue

                faces = self.app.get(img)
                if not faces:
                    log.warning("No face detected in: %s", img_path)
                    continue

                # Use the largest face (by bounding box area) if multiple detected
                face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
                emb = face.normed_embedding
                person_embeddings.append(emb)
                log.debug("  %s: extracted embedding from %s", person_name, img_path.name)

            if not person_embeddings:
                log.warning("No valid face embeddings for person: %s", person_name)
                continue

            # Store individual embeddings (not averaged) for better matching
            # But also compute average for stats
            avg_embedding = np.mean(person_embeddings, axis=0)
            avg_embedding = avg_embedding / np.linalg.norm(avg_embedding)

            for emb in person_embeddings:
                all_embeddings.append(emb)
                self.labels.append(person_name)

            self.person_stats[person_name] = {
                "image_count": len(image_files),
                "embedding_count": len(person_embeddings),
            }

            log.info("  %s: %d images, %d embeddings",
                     person_name, len(image_files), len(person_embeddings))

        if not all_embeddings:
            raise ValueError("No face embeddings could be generated from any reference images")

        # Build FAISS index (Inner Product = cosine similarity on normalized vectors)
        dim = all_embeddings[0].shape[0]  # 512 for buffalo_l
        self.index = faiss.IndexFlatIP(dim)

        embeddings_matrix = np.array(all_embeddings, dtype=np.float32)
        # Ensure L2-normalized for cosine similarity
        faiss.normalize_L2(embeddings_matrix)
        self.index.add(embeddings_matrix)

        log.info("FAISS index built: %d embeddings, %d dimensions, %d persons",
                 self.index.ntotal, dim, len(self.person_stats))

        return self.index, self.labels, self.person_stats

    def save(self, output_dir: str):
        """Save FAISS index and labels to disk."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        index_path = out / "index.faiss"
        labels_path = out / "labels.json"
        stats_path = out / "person_stats.json"

        faiss.write_index(self.index, str(index_path))

        with open(labels_path, "w") as f:
            json.dump(self.labels, f)

        with open(stats_path, "w") as f:
            json.dump(self.person_stats, f, indent=2)

        log.info("Index saved to: %s", out)

    @staticmethod
    def load(index_dir: str) -> tuple:
        """Load FAISS index and labels from disk.

        Returns:
            (faiss.Index, list of labels, dict of person stats)
        """
        d = Path(index_dir)
        index = faiss.read_index(str(d / "index.faiss"))

        with open(d / "labels.json", "r") as f:
            labels = json.load(f)

        stats_path = d / "person_stats.json"
        stats = {}
        if stats_path.exists():
            with open(stats_path, "r") as f:
                stats = json.load(f)

        log.info("Loaded FAISS index: %d embeddings, %d labels", index.ntotal, len(labels))
        return index, labels, stats
