"""
app/knowledge/ocr/vision_engine.py
==================================
Multimodal vision-model OCR engine using local open-weight vision models (e.g. Qwen 2.5/3.5 VL)
via the sovereign local Ollama inference provider.
Serves as an on-premise alternative or fallback when native Tesseract binaries are absent.
"""

import base64
import io
import logging
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

from app.config import get_settings
from app.knowledge.ocr.base import BaseOCREngine, OCRResult
from app.models.registry import get_model_for_role

logger = logging.getLogger("sovereign.knowledge.ocr.vision")


class VisionModelOCREngine(BaseOCREngine):
    """Extracts text and numeric telemetry from industrial images using a local vision model."""

    def __init__(self, model_tag: str | None = None, base_url: str | None = None) -> None:
        self.model_tag = model_tag or get_model_for_role("vision", default="qwen3.5:4b")
        raw_url = base_url or get_settings().ollama_base_url
        self.base_url = raw_url.rstrip("/")
        self._available: bool | None = None

    def is_available(self) -> bool:
        """Checks if Ollama is reachable and has a vision-capable model available."""
        try:
            resp = httpx.get(f"{self.base_url}/api/tags", timeout=2.0)
            if resp.status_code == 200:
                models = [m.get("name", "") for m in resp.json().get("models", [])]
                # Check for configured vision model or any model with vision capability
                tag_base = self.model_tag.split(":")[0]
                has_model = any(tag_base in m for m in models)
                self._available = has_model
                return self._available
        except Exception as exc:
            logger.debug("Vision engine availability check failed: %s", exc)
        self._available = False
        return False

    def extract_text(self, image: Image.Image | Path) -> OCRResult:
        """Sends image to local vision model for optical text and numeric transcription."""
        if not self.is_available():
            return OCRResult(
                text="",
                confidence=0.0,
                engine="vision_model_unavailable",
            )

        try:
            # Convert image to base64
            pil_img: Image.Image
            if isinstance(image, Path):
                pil_img = Image.open(image)
            else:
                pil_img = image

            # Convert to RGB if necessary
            if pil_img.mode not in ("RGB", "L"):
                pil_img = pil_img.convert("RGB")

            buf = io.BytesIO()
            pil_img.save(buf, format="PNG")
            b64_image = base64.b64encode(buf.getvalue()).decode("utf-8")

            payload: dict[str, Any] = {
                "model": self.model_tag,
                "prompt": (
                    "Read and transcribe all visible text, numbers, labels, and units in this image verbatim. "
                    "Do not explain."
                ),
                "images": [b64_image],
                "stream": False,
                "options": {
                    "temperature": 0.0,
                    "num_predict": 1024,
                },
            }

            with httpx.Client(timeout=60.0) as client:
                resp = client.post(f"{self.base_url}/api/generate", json=payload)
                resp.raise_for_status()
                data = resp.json()

            extracted = data.get("response", "").strip()
            if not extracted and data.get("thinking"):
                extracted = data.get("thinking", "").strip()

            return OCRResult(
                text=extracted,
                confidence=0.90 if extracted else 0.0,
                engine=f"ollama_vision:{self.model_tag}",
            )

        except Exception as exc:
            logger.warning("Vision model OCR extraction failed: %s", exc)
            return OCRResult(
                text="",
                confidence=0.0,
                engine="vision_model_error",
            )
