"""
app/models/registry.py
======================
Central model registry for Sovereign Workbench.
Loads dynamic model mappings and options from models_config.json.
Provides role-to-tag resolution and provider instantiation.
"""

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.models.base import BaseModelProvider
from app.models.ollama import OllamaProvider
from app.models.schemas import ModelConfig, ModelOption

logger = logging.getLogger("sovereign.models.registry")

CONFIG_FILE_PATH = Path(__file__).resolve().parent.parent.parent / "models_config.json"

DEFAULT_MODELS: dict[str, dict[str, Any]] = {
    "reasoning": {
        "tag": "llama3.2:latest",
        "label": "Reasoning (Llama 3.2 3B)",
        "context_window": 131072,
        "supports_thinking": False,
    },
    "coding": {
        "tag": "llama3.2:latest",
        "label": "Coding (Llama 3.2 3B)",
        "context_window": 131072,
        "supports_thinking": False,
    },
    "vision": {
        "tag": "qwen3.5:4b",
        "label": "Vision (Qwen 3.5 4B)",
        "context_window": 32768,
        "supports_thinking": True,
    },
    "ocr": {
        "tag": "qwen3.5:4b",
        "label": "OCR VLM (Qwen 3.5 4B)",
        "context_window": 32768,
        "supports_thinking": True,
    },
    "embedding": {
        "tag": "all-minilm:l6-v2",
        "label": "Embedding (All-MiniLM L6-v2)",
        "context_window": 512,
        "supports_thinking": False,
    },
}

DEFAULT_OPTIONS: list[dict[str, str]] = [
    {
        "id": "auto",
        "role": "auto",
        "label": "Auto (Router)",
        "desc": "Dynamic 3-Stage Waterfall Routing",
    },
    {
        "id": "reasoning",
        "role": "reasoning",
        "label": "Reasoning",
        "desc": "Step-by-step reasoning, analytical synthesis & math",
    },
    {
        "id": "coding",
        "role": "coding",
        "label": "Coding",
        "desc": "Code generation, debugging & tool execution",
    },
]


def load_models_config() -> dict[str, Any]:
    """Reads models_config.json from project root, with graceful built-in fallback."""
    if CONFIG_FILE_PATH.exists():
        try:
            with open(CONFIG_FILE_PATH, encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "models" in data:
                    return data
        except Exception as e:
            logger.warning(f"Error reading models_config.json: {e}. Falling back to default configuration.")

    return {
        "models": DEFAULT_MODELS,
        "options": DEFAULT_OPTIONS,
    }


def get_model_registry() -> dict[str, str]:
    """Returns mapping of role -> model tag (e.g. {'coding': 'qwen2.5-coder:3b'})."""
    cfg = load_models_config()
    models = cfg.get("models", {})
    return {role: meta.get("tag", "") for role, meta in models.items() if isinstance(meta, dict)}


def get_model_config(role: str) -> ModelConfig:
    """Returns typed configuration for a specific role."""
    cfg = load_models_config()
    models = cfg.get("models", {})
    raw = models.get(role, DEFAULT_MODELS.get(role, DEFAULT_MODELS["reasoning"]))
    return ModelConfig(**raw)


def get_model_for_role(role: str, default: str | None = None) -> str:
    """Resolves a role name to its configured model tag."""
    registry = get_model_registry()
    if role in registry and registry[role]:
        return registry[role]
    if default:
        return default
    return registry.get("reasoning", "llama3.2:latest")


def get_role_context_windows() -> dict[str, int]:
    """Returns mapping of role -> maximum token context window."""
    cfg = load_models_config()
    models = cfg.get("models", {})
    return {
        role: meta.get("context_window", 8192)
        for role, meta in models.items()
        if isinstance(meta, dict) and "context_window" in meta
    }


def get_model_options() -> list[ModelOption]:
    """Returns selectable model options for UI selection dropdowns."""
    cfg = load_models_config()
    raw_options = cfg.get("options", DEFAULT_OPTIONS)
    return [ModelOption(**opt) for opt in raw_options if isinstance(opt, dict)]


@lru_cache(maxsize=1)
def get_default_provider() -> BaseModelProvider:
    """Returns the default configured model provider instance (OllamaProvider)."""
    return OllamaProvider()
