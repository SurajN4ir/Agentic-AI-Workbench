"""
eval/mock_provider.py
=====================
Deterministic mock model provider for CI testing and offline evaluation runs.
Enables running the full evaluation harness without requiring a live Ollama daemon.
"""

from collections.abc import AsyncIterator
from typing import Any

from app.models.base import BaseModelProvider
from app.models.schemas import (
    ChatMessage,
    ChatResponse,
    EmbeddingResponse,
    GenerateOptions,
    ModelResponse,
)


class MockBenchmarkProvider(BaseModelProvider):
    """Deterministic mock provider that satisfies industrial benchmark criteria."""

    async def generate(
        self,
        model: str,
        prompt: str,
        system: str | None = None,
        options: GenerateOptions | None = None,
    ) -> ModelResponse:
        return ModelResponse(content="Evaluation response", model=model)

    async def stream(
        self,
        model: str,
        prompt: str,
        system: str | None = None,
        options: GenerateOptions | None = None,
    ) -> AsyncIterator[str]:
        yield "Evaluation response"

    async def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        options: GenerateOptions | None = None,
    ) -> ChatResponse:
        last_msg = messages[-1] if messages else {}

        # If previous message was a tool result, synthesize final answer
        if last_msg.get("role") == "tool":
            return ChatResponse(
                message=ChatMessage(
                    role="assistant",
                    content=(
                        "Calculated solution: roots are 1, 2, 3. The conversion of CSTR steady-state "
                        "is verified with tau parameter. LMTD is counter-flow with Delta T. "
                        "NPSH available prevents cavitation at suction. Statistical results: mean is 213.1, "
                        "sample deviation is 3.12, 95th percentile is 217.9. Linear regression gives slope m=0.178 "
                        "and intercept c=0.005. [Source: refinery_manual.pdf | Page 4]"
                    ),
                ),
                model=model,
            )

        # Inspect only the user's input prompt for tool selection
        user_msg = next((m for m in messages if m.get("role") == "user"), {})
        c = user_msg.get("content", "").lower()

        # 1. Sandbox / Python Code execution
        if any(k in c for k in ["python", "script", "sandbox", "regression", "execute python"]):
            return ChatResponse(
                message=ChatMessage(
                    role="assistant",
                    content="",
                    tool_calls=[{
                        "id": "call_code",
                        "function": {
                            "name": "code_sandbox",
                            "arguments": {"code": "print('stats')"},
                        },
                    }],
                ),
                model=model,
            )

        # 2. Deliverable file generation
        if any(k in c for k in ["word", "excel", "deliverable", "document", "docx", "xlsx"]):
            return ChatResponse(
                message=ChatMessage(
                    role="assistant",
                    content="",
                    tool_calls=[{
                        "id": "call_doc",
                        "function": {
                            "name": "doc_gen",
                            "arguments": {"format": "docx", "title": "Report"},
                        },
                    }],
                ),
                model=model,
            )

        # 3. Knowledge retrieval (RAG)
        if any(k in c for k in ["psv-402", "compressor", "manual", "search internal", "operating", "rag_search"]):
            return ChatResponse(
                message=ChatMessage(
                    role="assistant",
                    content="",
                    tool_calls=[{
                        "id": "call_rag",
                        "function": {
                            "name": "rag_search",
                            "arguments": {"query": "pressure limits"},
                        },
                    }],
                ),
                model=model,
            )

        # 4. Symbolic & arithmetic math
        if any(k in c for k in ["lmtd", "npsh", "cstr", "solve", "integral", "roots", "simplify", "calculate", "conversion", "first-order", "cavitation"]):
            return ChatResponse(
                message=ChatMessage(
                    role="assistant",
                    content="",
                    tool_calls=[{
                        "id": "call_math",
                        "function": {
                            "name": "math_eval",
                            "arguments": {"expression": "1+1", "operation": "eval"},
                        },
                    }],
                ),
                model=model,
            )

        # Direct response without tool invocation
        return ChatResponse(
            message=ChatMessage(
                role="assistant",
                content=(
                    "Standard industrial reasoning response with LMTD, counter-flow, conversion, "
                    "CSTR steady-state parameters. [Source: manual.pdf]"
                ),
            ),
            model=model,
        )

    async def stream_chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        options: GenerateOptions | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        yield {}

    async def embed(self, model: str, texts: list[str]) -> EmbeddingResponse:
        return EmbeddingResponse(embeddings=[[0.1] * 768 for _ in texts], model=model, dimension=768)

    async def list_models(self) -> list[str]:
        return ["qwen2.5:3b"]

    async def health_check(self) -> bool:
        return True
