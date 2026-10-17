"""
app/models/ollama.py
====================
Asynchronous Ollama model provider implementation for local-first inference.
Strictly talks to local/loopback endpoints, rejecting remote network egress.
"""

import json
import logging
import re
import uuid
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import get_settings
from app.models.base import BaseModelProvider
from app.models.schemas import ChatMessage, ChatResponse, EmbeddingResponse, GenerateOptions, ModelResponse

logger = logging.getLogger("sovereign.models.ollama")

_THINK_REGEX = re.compile(r"<think>(.*?)</think>", re.DOTALL)



class OllamaProvider(BaseModelProvider):
    """Local Ollama HTTP client supporting generation, streaming, and embeddings."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        raw_url = base_url or get_settings().ollama_base_url
        self.base_url = raw_url.rstrip("/")
        self.timeout = timeout
        self._transport = transport
        self._validate_local_target(self.base_url)

    @staticmethod
    def _validate_local_target(url: str) -> None:
        """Enforces that Ollama target is on a sovereign local interface."""
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        allowed = {"127.0.0.1", "localhost", "::1", "ollama", "host.docker.internal"}
        if host not in allowed:
            raise ValueError(
                f"Sovereignty violation: Ollama provider target '{host}' is not a permitted local or loopback address."
            )

    def _get_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout, connect=5.0),
            transport=self._transport,
        )

    async def generate(
        self,
        model: str,
        prompt: str,
        system: str | None = None,
        options: GenerateOptions | None = None,
    ) -> ModelResponse:
        opts = options or GenerateOptions()
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": opts.temperature,
                "top_p": opts.top_p,
            },
        }
        if system or opts.system_prompt:
            payload["system"] = system or opts.system_prompt
        if opts.max_tokens:
            payload["options"]["num_predict"] = opts.max_tokens
        if opts.stop:
            payload["options"]["stop"] = opts.stop
        if opts.extra_params:
            payload["options"].update(opts.extra_params)

        async with self._get_client() as client:
            resp = await client.post("/api/generate", json=payload)
            resp.raise_for_status()
            data = resp.json()

        raw_response = data.get("response", "")
        thinking: str | None = None
        content = raw_response

        # Extract thinking tags if present (e.g. DeepSeek-R1 / Qwen 2.5/3.5 thinking traces)
        match = _THINK_REGEX.search(raw_response)
        if match:
            thinking = match.group(1).strip()
            content = _THINK_REGEX.sub("", raw_response).strip()

        # Total duration in milliseconds (Ollama reports nanoseconds in total_duration)
        duration_ns = data.get("total_duration")
        duration_ms = duration_ns / 1_000_000.0 if duration_ns else None

        return ModelResponse(
            content=content,
            thinking_content=thinking,
            model=data.get("model", model),
            total_duration_ms=duration_ms,
            prompt_eval_count=data.get("prompt_eval_count"),
            eval_count=data.get("eval_count"),
        )

    async def stream(
        self,
        model: str,
        prompt: str,
        system: str | None = None,
        options: GenerateOptions | None = None,
    ) -> AsyncIterator[str]:
        opts = options or GenerateOptions()
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": opts.temperature,
                "top_p": opts.top_p,
            },
        }
        if system or opts.system_prompt:
            payload["system"] = system or opts.system_prompt
        if opts.max_tokens:
            payload["options"]["num_predict"] = opts.max_tokens
        if opts.stop:
            payload["options"]["stop"] = opts.stop

        async with self._get_client() as client:
            async with client.stream("POST", "/api/generate", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        text = chunk.get("response", "")
                        if text:
                            yield text
                    except json.JSONDecodeError:
                        continue

    async def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        options: GenerateOptions | None = None,
    ) -> ChatResponse:
        opts = options or GenerateOptions()
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": opts.temperature,
                "top_p": opts.top_p,
            },
        }
        if tools:
            payload["tools"] = tools
        if opts.max_tokens:
            payload["options"]["num_predict"] = opts.max_tokens
        if opts.stop:
            payload["options"]["stop"] = opts.stop
        if opts.extra_params:
            payload["options"].update(opts.extra_params)

        async with self._get_client() as client:
            resp = await client.post("/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()

        msg_data = data.get("message", {})
        raw_content = msg_data.get("content", "")
        thinking: str | None = None
        content = raw_content

        match = _THINK_REGEX.search(raw_content)
        if match:
            thinking = match.group(1).strip()
            content = _THINK_REGEX.sub("", raw_content).strip()

        raw_tool_calls = msg_data.get("tool_calls")
        tool_calls: list[dict[str, Any]] | None = None
        if raw_tool_calls:
            tool_calls = []
            for tc in raw_tool_calls:
                tc_dict = dict(tc)
                if not tc_dict.get("id"):
                    tc_dict["id"] = f"call_{uuid.uuid4().hex[:8]}"
                tool_calls.append(tc_dict)

        duration_ns = data.get("total_duration")
        duration_ms = duration_ns / 1_000_000.0 if duration_ns else None

        chat_msg = ChatMessage(
            role=msg_data.get("role", "assistant"),
            content=content,
            tool_calls=tool_calls,
        )
        return ChatResponse(
            message=chat_msg,
            thinking_content=thinking,
            model=data.get("model", model),
            total_duration_ms=duration_ms,
            prompt_eval_count=data.get("prompt_eval_count"),
            eval_count=data.get("eval_count"),
        )

    async def stream_chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        options: GenerateOptions | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        opts = options or GenerateOptions()
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": opts.temperature,
                "top_p": opts.top_p,
            },
        }
        if tools:
            payload["tools"] = tools
        if opts.max_tokens:
            payload["options"]["num_predict"] = opts.max_tokens
        if opts.stop:
            payload["options"]["stop"] = opts.stop

        async with self._get_client() as client:
            async with client.stream("POST", "/api/chat", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        yield chunk
                    except json.JSONDecodeError:
                        continue

    async def embed(

        self,
        model: str,
        texts: list[str],
    ) -> EmbeddingResponse:
        """Generate vector embeddings. Uses /api/embed (batch) with /api/embeddings fallback."""
        if not texts:
            return EmbeddingResponse(embeddings=[], model=model, dimension=0)

        async with self._get_client() as client:
            # Try new batch /api/embed first
            try:
                resp = await client.post("/api/embed", json={"model": model, "input": texts})
                if resp.status_code == 200:
                    data = resp.json()
                    embeddings: list[list[float]] = data.get("embeddings", [])
                    dim = len(embeddings[0]) if embeddings else 0
                    return EmbeddingResponse(embeddings=embeddings, model=model, dimension=dim)
            except Exception as e:
                logger.debug(f"/api/embed not available or failed: {e}; attempting legacy /api/embeddings")

            # Fallback to single /api/embeddings
            all_embeddings: list[list[float]] = []
            for text in texts:
                resp = await client.post("/api/embeddings", json={"model": model, "prompt": text})
                resp.raise_for_status()
                vec = resp.json().get("embedding", [])
                all_embeddings.append(vec)

            dim = len(all_embeddings[0]) if all_embeddings else 0
            return EmbeddingResponse(embeddings=all_embeddings, model=model, dimension=dim)

    async def list_models(self) -> list[str]:
        async with self._get_client() as client:
            resp = await client.get("/api/tags")
            resp.raise_for_status()
            models_list = resp.json().get("models", [])
            return [m.get("name", "") for m in models_list if m.get("name")]

    async def health_check(self) -> bool:
        try:
            async with self._get_client() as client:
                resp = await client.get("/api/tags")
                return resp.status_code == 200
        except Exception:
            return False
