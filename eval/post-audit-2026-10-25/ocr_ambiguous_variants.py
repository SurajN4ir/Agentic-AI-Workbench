"""Controlled OCR preprocessing experiment on the fixed synthetic serial-tag fixture."""

from __future__ import annotations

import base64
import io
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from PIL import Image, ImageEnhance, ImageOps

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "eval" / "fixtures" / "ocr" / "ambiguous_serial_tag.png"
GROUND_TRUTH = ROOT / "eval" / "dataset" / "quantitative_ground_truth.json"
OUTPUT = Path(__file__).with_name("ocr_ambiguous_variants.json")
MODEL = "qwen3.5:4b"
SYSTEM = "You are an OCR engine. Output only the verbatim text found in the image. Do not explain, describe, or converse."
PROMPT = "Extract and transcribe all text from this image verbatim. Output ONLY the extracted text with no other words, no greetings, no descriptions."


def line_composite(image: Image.Image) -> Image.Image:
    """Find text row bands from dark pixels, crop them, and stack with whitespace."""
    gray = image.convert("L")
    pixels = gray.load()
    x0, x1 = 12, gray.width - 12
    y0, y1 = 12, gray.height - 12
    row_hits = [
        any(pixels[x, y] < 130 for x in range(x0, x1))
        for y in range(y0, y1)
    ]
    bands: list[tuple[int, int]] = []
    start: int | None = None
    last_hit: int | None = None
    for index, hit in enumerate(row_hits):
        absolute_y = y0 + index
        if hit:
            if start is None:
                start = absolute_y
            last_hit = absolute_y
        elif start is not None and last_hit is not None and absolute_y - last_hit > 2:
            if last_hit - start >= 2:
                bands.append((max(y0, start - 3), min(y1, last_hit + 4)))
            start = None
            last_hit = None
    if start is not None and last_hit is not None and last_hit - start >= 2:
        bands.append((max(y0, start - 3), min(y1, last_hit + 4)))

    crops: list[Image.Image] = []
    for top, bottom in bands:
        crop = gray.crop((x0, top, x1, bottom))
        bbox = ImageOps.invert(crop).point(lambda value: 255 if value > 125 else 0).getbbox()
        if bbox:
            crop = crop.crop((max(0, bbox[0] - 4), max(0, bbox[1] - 2), min(crop.width, bbox[2] + 4), min(crop.height, bbox[3] + 2)))
            crops.append(crop.resize((crop.width * 4, crop.height * 4), Image.Resampling.LANCZOS))

    if not crops:
        raise RuntimeError("Pixel-only line segmentation found no text bands")
    width = max(crop.width for crop in crops)
    spacer = Image.new("L", (width, 24), 255)
    height = sum(crop.height for crop in crops) + 24 * (len(crops) - 1)
    result = Image.new("L", (width, height), 255)
    cursor_y = 0
    for index, crop in enumerate(crops):
        result.paste(crop, (0, cursor_y))
        cursor_y += crop.height
        if index < len(crops) - 1:
            result.paste(spacer, (0, cursor_y))
            cursor_y += spacer.height
    return result


def variants(source: Image.Image) -> dict[str, Image.Image]:
    lanczos_2x = source.resize((source.width * 2, source.height * 2), Image.Resampling.LANCZOS)
    sharpened = ImageOps.autocontrast(source.convert("L"))
    sharpened = ImageEnhance.Sharpness(sharpened).enhance(2.0)
    return {
        "current_2x_lanczos": lanczos_2x,
        "4x_lanczos": source.resize((source.width * 4, source.height * 4), Image.Resampling.LANCZOS),
        "4x_nearest": source.resize((source.width * 4, source.height * 4), Image.Resampling.NEAREST),
        "autocontrast_sharp_2x": sharpened.resize((source.width * 2, source.height * 2), Image.Resampling.LANCZOS),
        "pixel_segmented_lines_4x": line_composite(source),
    }


def request_ocr(base_url: str, image: Image.Image) -> tuple[str, float]:
    image = image.convert("RGB") if image.mode not in ("RGB", "L") else image
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    payload = {
        "model": MODEL,
        "system": SYSTEM,
        "prompt": PROMPT,
        "images": [base64.b64encode(stream.getvalue()).decode("ascii")],
        "stream": False,
        "think": False,
        "options": {"temperature": 0.0, "num_predict": 1024},
    }
    start = time.perf_counter()
    response = httpx.post(f"{base_url.rstrip('/')}/api/generate", json=payload, timeout=120.0)
    response.raise_for_status()
    result = response.json()
    return str(result.get("response", "")).strip(), (time.perf_counter() - start) * 1000


def main() -> None:
    from app.config import get_settings
    from eval.quantitative_metrics import calculate_cer, calculate_wer

    base_url = get_settings().ollama_base_url
    if urlsplit(base_url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("OCR evaluation refuses non-loopback model endpoints")
    truth = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))["ocr_ground_truth"][FIXTURE.name]["transcription"]
    with Image.open(FIXTURE) as source:
        image_variants = variants(source.copy())

    cases = []
    for name, image in image_variants.items():
        prediction, latency_ms = request_ocr(base_url, image)
        cer = calculate_cer(truth, prediction)
        wer = calculate_wer(truth, prediction)
        case = {
            "variant": name,
            "image_dimensions": list(image.size),
            "reference": truth,
            "prediction": prediction,
            "substitutions": cer.substitutions,
            "deletions": cer.deletions,
            "insertions": cer.insertions,
            "total_edits": cer.total_edits,
            "reference_characters": cer.reference_length,
            "cer": cer.error_rate,
            "wer": wer.error_rate,
            "latency_ms": round(latency_ms, 2),
        }
        cases.append(case)
        print(f"{name}: CER={cer.error_rate:.6f} WER={wer.error_rate:.6f} edits={cer.total_edits} latency={latency_ms:.1f}ms")  # noqa: T201

    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "mode": "live_local_ollama_single_fixture_preprocessing_comparison",
        "model": MODEL,
        "temperature": 0.0,
        "num_predict": 1024,
        "think": False,
        "fixture": str(FIXTURE.relative_to(ROOT)).replace("\\", "/"),
        "ground_truth_source": str(GROUND_TRUTH.relative_to(ROOT)).replace("\\", "/"),
        "reference_unchanged": True,
        "prompt_and_model_identical_for_each_variant": True,
        "cases": cases,
    }
    OUTPUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Saved: {OUTPUT}")  # noqa: T201


if __name__ == "__main__":
    main()
