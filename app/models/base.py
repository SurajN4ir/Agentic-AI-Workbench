"""
app/models/base.py
==================
Abstract interface for LLM and embedding providers.
Allows drop-in replacement (e.g. Ollama, vLLM, llama.cpp server)
without touching agent or workflow code.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from app.models.schemas import EmbeddingResponse, GenerateOptions, ModelResponse


class BaseModelProvider(ABC):
    """Abstract base provider for local model inference and embeddings."""

    @abstractmethod
    async def generate(
        self,
        model: str,
        prompt: str,
        system: str | None = None,
        options: GenerateOptions | None = None,
    ) -> ModelResponse:
        """Execute non-streaming text generation."""
        ...

    @abstractmethod
    def stream(
        self,
        model: str,
        prompt: str,
        system: str | None = None,
        options: GenerateOptions | None = None,
    ) -> AsyncIterator[str]:
        """Stream generated text chunks asynchronously."""
        ...

    @abstractmethod
    async def embed(
        self,
        model: str,
        texts: list[str],
    ) -> EmbeddingResponse:
        """Generate vector embeddings for a list of input texts."""
        ...

    @abstractmethod
    async def list_models(self) -> list[str]:
        """List currently installed and available models."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Verify inference backend is reachable and healthy."""
        ...
