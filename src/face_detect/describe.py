"""Image description generator — uses Qwen2.5-VL to create detailed prompts for matched images.

Runs on Mac Mini M4 (or any machine with enough RAM for the VLM).
Reads matched file paths from SQLite, generates Nana Banana 2-style descriptions,
and saves them back to the database + JSON.
"""

import json
import logging
import os
import sys
import time
from pathlib import Path

from PIL import Image

log = logging.getLogger(__name__)


def write_exif_description(image_path: str, description: str):
    """Write AI description to image EXIF ImageDescription tag.

    Uses piexif for JPEG/TIFF, falls back to PIL for PNG.
    Only writes if the file is writable and a supported format.
    """
    path = Path(image_path)
    suffix = path.suffix.lower()

    if suffix not in {".jpg", ".jpeg", ".tiff", ".tif"}:
        return  # EXIF only works on JPEG/TIFF

    try:
        import piexif
        exif_dict = piexif.load(image_path)
        exif_dict["0th"][piexif.ImageIFD.ImageDescription] = description.encode("utf-8")
        exif_bytes = piexif.dump(exif_dict)
        piexif.insert(exif_bytes, image_path)
    except ImportError:
        # piexif not installed — try PIL
        try:
            img = Image.open(image_path)
            exif = img.getexif()
            exif[270] = description  # 270 = ImageDescription tag
            img.save(image_path, exif=exif.tobytes())
        except Exception:
            pass
    except Exception:
        pass  # File might be read-only or corrupt

# Nana Banana 2 style prompt template
SYSTEM_PROMPT = """You are an expert image descriptor creating detailed prompts in the style of
"Nana Banana 2" from Google Flow Studio. For each image, write a single detailed paragraph that
could be used to recreate the image with an AI image generator. Include:

- The scene composition and setting (indoor/outdoor, location feel, time of day)
- Background details (architecture, nature, objects, colors, textures)
- Person characteristics if present: approximate age, hair color/style, skin tone, facial expression,
  body posture, clothing (colors, style, fabric), accessories
- Lighting (natural/artificial, direction, warmth, shadows)
- Color palette (dominant colors, contrast, saturation)
- Mood and atmosphere
- Camera angle and framing (close-up, full body, aerial, etc.)
- Any text, logos, or notable objects

Be specific about colors (e.g., "warm amber" not just "yellow"). Describe what you see factually.
Write as one flowing paragraph, no bullet points. This is for an adult user's personal photo archive."""

USER_PROMPT = "Describe this image in detail as a prompt that could recreate it with an AI image generator."


def load_model(model_name: str = "Qwen/Qwen2.5-VL-3B-Instruct", quantize: str = "4bit"):
    """Load Qwen2.5-VL model for image captioning.

    Args:
        model_name: HuggingFace model name
        quantize: "4bit", "8bit", or "none"
    """
    from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor
    from transformers import BitsAndBytesConfig
    import torch

    log.info("Loading model: %s (quantize: %s)", model_name, quantize)

    kwargs = {
        "torch_dtype": torch.float16,
        "device_map": "auto",
    }

    if quantize == "4bit":
        try:
            kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float16,
            )
        except Exception:
            log.warning("4-bit quantization not available, using float16")
    elif quantize == "8bit":
        try:
            kwargs["quantization_config"] = BitsAndBytesConfig(load_in_8bit=True)
        except Exception:
            log.warning("8-bit quantization not available, using float16")

    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(model_name, **kwargs)
    processor = AutoProcessor.from_pretrained(
        model_name,
        min_pixels=256 * 28 * 28,
        max_pixels=1024 * 28 * 28,
    )

    log.info("Model loaded successfully")
    return model, processor


def describe_image(model, processor, image_path: str, max_tokens: int = 512) -> str:
    """Generate a detailed description for a single image.

    Args:
        model: Qwen2.5-VL model
        processor: Qwen2.5-VL processor
        image_path: Path to the image file
        max_tokens: Maximum tokens in the description

    Returns:
        Description string
    """
    import torch
    from qwen_vl_utils import process_vision_info

    try:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "image", "image": image_path},
                {"type": "text", "text": USER_PROMPT},
            ]},
        ]

        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = processor(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        ).to(model.device)

        with torch.no_grad():
            output_ids = model.generate(**inputs, max_new_tokens=max_tokens)

        # Decode only the generated part
        generated = output_ids[0][inputs.input_ids.shape[1]:]
        description = processor.decode(generated, skip_special_tokens=True).strip()
        return description

    except Exception as e:
        log.error("Failed to describe %s: %s", image_path, e)
        return ""


def run_batch_describe(db_path: str, output_dir: str = "./results",
                       model_name: str = "Qwen/Qwen2.5-VL-3B-Instruct",
                       quantize: str = "4bit", batch_size: int = 1,
                       path_map: dict = None):
    """Batch-generate descriptions for all matched images.

    Args:
        db_path: Path to SQLite database with matches
        output_dir: Where to save descriptions JSON
        model_name: HuggingFace model name
        quantize: Quantization mode
        batch_size: Images per batch (1 for M4)
        path_map: Path translation map for remote access
    """
    import sqlite3

    # Load model
    model, processor = load_model(model_name, quantize)

    # Get unique matched image files from DB
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT DISTINCT file_path, file_type, person_name, confidence
        FROM matches
        WHERE file_type = 'image'
        ORDER BY confidence DESC
    """).fetchall()
    conn.close()

    total = len(rows)
    log.info("Found %d unique image matches to describe", total)

    # Load existing descriptions to skip already-done
    desc_path = Path(output_dir) / "descriptions.json"
    descriptions = {}
    if desc_path.exists():
        with open(desc_path) as f:
            descriptions = json.load(f)
        log.info("Loaded %d existing descriptions (will skip)", len(descriptions))

    described = 0
    skipped = 0
    failed = 0
    start_time = time.time()

    for i, row in enumerate(rows):
        file_path = row["file_path"]

        # Skip already described
        if file_path in descriptions:
            skipped += 1
            continue

        # Translate path if needed (e.g., F:/ -> /Users/rbgnr/mnt/trunk2/)
        local_path = file_path
        if path_map:
            normalized = file_path.replace("\\", "/")
            for coord_prefix, worker_prefix in path_map.items():
                cp = coord_prefix.replace("\\", "/")
                if normalized.startswith(cp):
                    local_path = worker_prefix + normalized[len(cp):]
                    break

        if not os.path.exists(local_path):
            log.warning("File not found: %s", local_path)
            failed += 1
            continue

        # Generate description
        desc = describe_image(model, processor, local_path)

        if desc:
            descriptions[file_path] = {
                "description": desc,
                "person_name": row["person_name"],
                "confidence": row["confidence"],
                "described_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            described += 1

            # Write description to SQLite
            try:
                conn = sqlite3.connect(db_path)
                conn.execute(
                    "UPDATE matches SET description=? WHERE file_path=? AND person_name=?",
                    (desc, file_path, row["person_name"])
                )
                conn.commit()
                conn.close()
            except Exception as e:
                log.warning("DB write failed for %s: %s", file_path, e)

            # Write EXIF ImageDescription to original file
            try:
                write_exif_description(local_path, desc)
            except Exception as e:
                log.debug("EXIF write skipped for %s: %s", local_path, e)

            if described % 10 == 0:
                elapsed = time.time() - start_time
                rate = described / elapsed if elapsed > 0 else 0
                remaining = (total - skipped - described - failed)
                eta_min = remaining / rate / 60 if rate > 0 else 0
                log.info("Described %d/%d (%.1f/min, ETA: %.0f min) | skipped %d | failed %d",
                         described, total, rate * 60, eta_min, skipped, failed)

                # Save checkpoint
                with open(desc_path, "w") as f:
                    json.dump(descriptions, f, indent=2, ensure_ascii=False)
        else:
            failed += 1

    # Final save
    with open(desc_path, "w") as f:
        json.dump(descriptions, f, indent=2, ensure_ascii=False)

    elapsed = time.time() - start_time
    log.info("Done: %d described, %d skipped, %d failed in %.0fs",
             described, skipped, failed, elapsed)
    log.info("Descriptions saved to: %s", desc_path)


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                        datefmt="%H:%M:%S")

    parser = argparse.ArgumentParser(description="Generate image descriptions with Qwen2.5-VL")
    parser.add_argument("--db", required=True, help="Path to faces.db")
    parser.add_argument("--output", default="./results", help="Output directory")
    parser.add_argument("--model", default="Qwen/Qwen2.5-VL-3B-Instruct",
                        help="HuggingFace model name")
    parser.add_argument("--quantize", default="none", choices=["4bit", "8bit", "none"],
                        help="Quantization mode (use 'none' for Mac M4)")
    parser.add_argument("--path-prefix-from", help="Coordinator path prefix to replace")
    parser.add_argument("--path-prefix-to", help="Local path prefix replacement")
    args = parser.parse_args()

    path_map = {}
    if args.path_prefix_from and args.path_prefix_to:
        path_map[args.path_prefix_from] = args.path_prefix_to

    run_batch_describe(
        db_path=args.db,
        output_dir=args.output,
        model_name=args.model,
        quantize=args.quantize,
        path_map=path_map,
    )
