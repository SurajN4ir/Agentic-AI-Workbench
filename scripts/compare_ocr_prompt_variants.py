"""Compare the pre-change and current OCR prompts on fixed synthetic fixtures.

The runner reads only the four paths in the repository's quantitative evaluation
dataset, requires a loopback Ollama endpoint, and writes one report under
eval/reports. It never scans a workspace or accepts arbitrary input paths.
"""

# ruff: noqa: E402

from __future__ import annotations

import base64
import io
import json
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.knowledge.parsers.pdf_parser import PDFParser
from app.models.registry import get_model_for_role
from eval.quantitative_metrics import calculate_cer, calculate_wer

DATASET = ROOT / "eval" / "dataset" / "quantitative_eval_dataset.json"
GROUND_TRUTH = ROOT / "eval" / "dataset" / "quantitative_ground_truth.json"
OUTPUT = ROOT / "eval" / "reports" / "ocr_preprocessing_small_images.json"
BASELINE_PROMPT = (
    "Read and transcribe all visible text, numbers, labels, and units in this image verbatim. "
    "Do not explain."
)
CANDIDATE_SYSTEM = (
    "You are an OCR engine. Output only the verbatim text found in the image. "
    "Do not explain, describe, or converse."
)
CANDIDATE_PROMPT = (
    "Extract and transcribe all text from this image verbatim. Output ONLY the extracted text "
    "with no other words, no greetings, no descriptions."
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sovereign.eval.ocr_prompt_comparison")


def fixture_path(relative_path: str) -> Path:
    path = (ROOT / relative_path).resolve()
    allowed_root = (ROOT / "eval" / "fixtures").resolve()
    if not path.is_relative_to(allowed_root) or not path.is_file():
        raise ValueError(f"Evaluation fixture must be an existing file under {allowed_root}: {relative_path}")
    return path


def image_for_request(image: Image.Image, upscale: int = 1) -> str:
    if upscale > 1:
        image = image.resize((image.width * upscale, image.height * upscale), Image.Resampling.LANCZOS)
    source = image if image.mode in ("RGB", "L") else image.convert("RGB")
    buffer = io.BytesIO()
    source.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


class PromptVariantEngine:
    """Minimal adapter matching VisionModelOCREngine image encoding and output handling."""

    def __init__(self, *, base_url: str, model: str, candidate: bool, upscale: int = 1) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.candidate = candidate
        self.upscale = upscale
        self.errors: list[str] = []

    def extract_text(self, image: Image.Image) -> str:
        effective_upscale = self.upscale if max(image.size) <= 600 else 1
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": CANDIDATE_PROMPT if self.candidate else BASELINE_PROMPT,
            "images": [image_for_request(image, effective_upscale)],
            "stream": False,
            "think": False,
            "options": {"temperature": 0.0, "num_predict": 1024},
        }
        if self.candidate:
            payload["system"] = CANDIDATE_SYSTEM
        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(f"{self.base_url}/api/generate", json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            self.errors.append(f"Ollama HTTP {exc.response.status_code}: {exc.response.text[:300]}")
            raise
        except httpx.HTTPError as exc:
            self.errors.append(f"Ollama request failed: {type(exc).__name__}: {exc}")
            raise
        prediction = str(data.get("response", "")).strip()
        if not self.candidate and not prediction and data.get("thinking"):
            prediction = str(data["thinking"]).strip()
        return prediction


def extract_fixture(path: Path, engine: PromptVariantEngine) -> str:
    if path.suffix.lower() != ".pdf":
        with Image.open(path) as image:
            return engine.extract_text(image)
    parser = PDFParser(ocr_fallback_fn=engine.extract_text)
    return "\n".join(section.text for section in parser.extract_sections(path))


def score_case(reference: str, prediction: str, keywords: list[str]) -> dict[str, Any]:
    cer = calculate_cer(reference, prediction)
    wer = calculate_wer(reference, prediction)
    keyword_recall = sum(keyword.upper() in prediction.upper() for keyword in keywords) / len(keywords) if keywords else 1.0
    return {
        "reference": reference,
        "prediction": prediction,
        "substitutions": cer.substitutions,
        "deletions": cer.deletions,
        "insertions": cer.insertions,
        "total_edits": cer.total_edits,
        "reference_characters": cer.reference_length,
        "prediction_characters": cer.hypothesis_length,
        "reference_words": wer.reference_length,
        "prediction_words": wer.hypothesis_length,
        "cer": cer.error_rate,
        "wer": wer.error_rate,
        "keyword_recall": round(keyword_recall, 4),
    }


def main() -> None:
    settings = get_settings()
    parsed_url = urlsplit(settings.ollama_base_url)
    if parsed_url.scheme != "http" or parsed_url.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("OCR comparison requires an HTTP loopback Ollama endpoint; external hosts are refused.")

    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    ground_truth = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))["ocr_ground_truth"]
    fixtures = dataset["test_suites"]["ocr_suite"]["fixtures"]
    model = get_model_for_role("vision", default="qwen3.5:4b")
    tag_response = httpx.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags", timeout=5.0)
    tag_response.raise_for_status()
    available_models = [item.get("name", "") for item in tag_response.json().get("models", [])]
    if not any(model.split(":")[0] in name for name in available_models):
        raise RuntimeError(f"Configured OCR model {model!r} is not available in local Ollama.")

    case_results: list[dict[str, Any]] = []
    for fixture in fixtures:
        path = fixture_path(fixture["file_path"])
        expected = ground_truth[fixture["ground_truth_key"]]
        variants: dict[str, Any] = {}
        variants_to_run = (
            ("baseline", False, 1),
            ("candidate", True, 1),
            ("candidate_small_image_upscaled_2x", True, 2),
        )
        for label, candidate, upscale in variants_to_run:
            engine = PromptVariantEngine(
                base_url=settings.ollama_base_url,
                model=model,
                candidate=candidate,
                upscale=upscale,
            )
            started = time.perf_counter()
            try:
                prediction = extract_fixture(path, engine)
            except Exception as exc:
                prediction = ""
                if not engine.errors:
                    engine.errors.append(f"Extraction failed: {type(exc).__name__}: {exc}")
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            variants[label] = {
                **score_case(expected["transcription"], prediction, expected.get("expected_keywords", [])),
                "latency_ms": latency_ms,
                "errors": engine.errors,
            }
            logger.info("%s %s: CER %.4f in %.0f ms", fixture["fixture_id"], label, variants[label]["cer"], latency_ms)
        case_results.append({"fixture_id": fixture["fixture_id"], "category": fixture.get("category"), "variants": variants})

    summary: dict[str, Any] = {}
    for label in ("baseline", "candidate", "candidate_small_image_upscaled_2x"):
        scores = [case["variants"][label] for case in case_results]
        total_edits = sum(score["total_edits"] for score in scores)
        total_reference_chars = sum(score["reference_characters"] for score in scores)
        summary[label] = {
            "cases": len(scores),
            "macro_cer": round(sum(score["cer"] for score in scores) / len(scores), 6),
            "micro_cer": round(total_edits / total_reference_chars, 6) if total_reference_chars else 0.0,
            "mean_wer": round(sum(score["wer"] for score in scores) / len(scores), 6),
            "mean_keyword_recall": round(sum(score["keyword_recall"] for score in scores) / len(scores), 6),
            "mean_latency_ms": round(sum(score["latency_ms"] for score in scores) / len(scores), 2),
        }

    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "mode": "live_local_ollama",
        "model": model,
        "temperature": 0.0,
        "num_predict": 1024,
        "think": False,
        "comparison_note": (
            "Both variants hold thinking disabled to isolate the prompt/system-instruction change. "
            "The historical baseline omitted the think field; a separate exact legacy request timed out "
            "before returning a prediction and is not scored here."
        ),
        "fixture_source": str(DATASET.relative_to(ROOT)),
        "ground_truth_source": str(GROUND_TRUTH.relative_to(ROOT)),
        "baseline_prompt": BASELINE_PROMPT,
        "candidate_system_prompt": CANDIDATE_SYSTEM,
        "candidate_prompt": CANDIDATE_PROMPT,
        "candidate_think": False,
        "preprocessing_variant": (
            "candidate_small_image_upscaled_2x uses Lanczos resize at 2x only when the source image's largest "
            "dimension is <=600 px; larger images preserve source dimensions"
        ),
        "normalization": "none beyond the same strip behavior as VisionModelOCREngine and PDFParser",
        "summary": summary,
        "cases": case_results,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "summary": summary}, indent=2))


if __name__ == "__main__":
    main()
