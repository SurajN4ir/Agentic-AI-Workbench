"""
app/models/__init__.py
======================
Model provider abstraction and local model registry.
"""

from app.models.base import BaseModelProvider
from app.models.ollama import OllamaProvider
from app.models.registry import get_model_registry, load_models_config

__all__ = [
    "BaseModelProvider",
    "OllamaProvider",
    "get_model_registry",
    "load_models_config",
]
