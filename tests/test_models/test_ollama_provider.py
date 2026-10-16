"""
tests/test_models/test_ollama_provider.py
=========================================
Unit tests for the OllamaProvider and BaseModelProvider interfaces.
Uses httpx.MockTransport to test HTTP communication without external network egress.
"""

import json

import httpx
import pytest
from app.models.ollama import OllamaProvider


class TestOllamaProvider:
    @pytest.mark.asyncio
    async def test_generate_success_and_thinking_extraction(self) -> None:
        """Verifies generate posts to /api/generate and extracts <think> tags."""

        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/generate"
            body = json.loads(request.content)
            assert body["model"] == "qwen2.5:3b"
            assert body["prompt"] == "Calculate 2+2"
            assert body["stream"] is False

            response_payload = {
                "model": "qwen2.5:3b",
                "response": "<think>2+2 is 4.</think>The answer is 4.",
                "total_duration": 1500000000,  # 1.5s in ns
                "prompt_eval_count": 12,
                "eval_count": 8,
            }
            return httpx.Response(200, json=response_payload)

        transport = httpx.MockTransport(handler)
        provider = OllamaProvider(base_url="http://127.0.0.1:11434", transport=transport)

        resp = await provider.generate("qwen2.5:3b", "Calculate 2+2")
        assert resp.content == "The answer is 4."
        assert resp.thinking_content == "2+2 is 4."
        assert resp.model == "qwen2.5:3b"
        assert resp.total_duration_ms == 1500.0
        assert resp.prompt_eval_count == 12
        assert resp.eval_count == 8

    @pytest.mark.asyncio
    async def test_stream_chunks(self) -> None:
        """Verifies streaming generation parses JSON lines into text chunks."""

        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/generate"
            lines = [
                json.dumps({"response": "Hello"}),
                json.dumps({"response": " "}),
                json.dumps({"response": "world"}),
                json.dumps({"response": "!"}),
            ]
            content = "\n".join(lines).encode("utf-8")
            return httpx.Response(200, content=content)

        transport = httpx.MockTransport(handler)
        provider = OllamaProvider(base_url="http://127.0.0.1:11434", transport=transport)

        collected = []
        async for chunk in provider.stream("qwen2.5:3b", "Greet me"):
            collected.append(chunk)

        assert "".join(collected) == "Hello world!"

    @pytest.mark.asyncio
    async def test_embed_batch_success(self) -> None:
        """Verifies /api/embed generates vector embeddings."""

        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/embed"
            body = json.loads(request.content)
            assert body["model"] == "nomic-embed-text"
            assert len(body["input"]) == 2

            payload = {
                "embeddings": [
                    [0.1, 0.2, 0.3],
                    [0.4, 0.5, 0.6],
                ]
            }
            return httpx.Response(200, json=payload)

        transport = httpx.MockTransport(handler)
        provider = OllamaProvider(base_url="http://127.0.0.1:11434", transport=transport)

        result = await provider.embed("nomic-embed-text", ["doc 1", "doc 2"])
        assert len(result.embeddings) == 2
        assert result.dimension == 3
        assert result.embeddings[0] == [0.1, 0.2, 0.3]

    @pytest.mark.asyncio
    async def test_embed_legacy_fallback(self) -> None:
        """Verifies fallback to /api/embeddings when /api/embed returns 404."""

        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/embed":
                return httpx.Response(404)
            if request.url.path == "/api/embeddings":
                body = json.loads(request.content)
                assert body["prompt"] == "test"
                return httpx.Response(200, json={"embedding": [0.9, 0.8]})
            return httpx.Response(500)

        transport = httpx.MockTransport(handler)
        provider = OllamaProvider(base_url="http://127.0.0.1:11434", transport=transport)

        result = await provider.embed("nomic-embed-text", ["test"])
        assert len(result.embeddings) == 1
        assert result.dimension == 2
        assert result.embeddings[0] == [0.9, 0.8]

    @pytest.mark.asyncio
    async def test_health_check_true_on_200(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/tags"
            return httpx.Response(200, json={"models": [{"name": "qwen2.5:3b"}]})

        transport = httpx.MockTransport(handler)
        provider = OllamaProvider(base_url="http://127.0.0.1:11434", transport=transport)
        assert await provider.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_false_on_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500)

        transport = httpx.MockTransport(handler)
        provider = OllamaProvider(base_url="http://127.0.0.1:11434", transport=transport)
        assert await provider.health_check() is False

    def test_sovereignty_enforcement_rejects_external_host(self) -> None:
        """Provider must reject non-local target URLs to prevent data exfiltration."""
        with pytest.raises(ValueError, match="Sovereignty violation"):
            OllamaProvider(base_url="https://api.openai.com/v1")

        with pytest.raises(ValueError, match="Sovereignty violation"):
            OllamaProvider(base_url="http://192.168.1.100:11434")

        # Allowed targets must not raise:
        p1 = OllamaProvider(base_url="http://127.0.0.1:11434")
        assert p1.base_url == "http://127.0.0.1:11434"

        p2 = OllamaProvider(base_url="http://localhost:11434")
        assert p2.base_url == "http://localhost:11434"

        p3 = OllamaProvider(base_url="http://ollama:11434")
        assert p3.base_url == "http://ollama:11434"
