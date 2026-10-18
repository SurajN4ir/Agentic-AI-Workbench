"""
tests/test_integration/test_real_ollama.py
==========================================
Integration tests verifying inference against the real local Ollama daemon.
"""

import pytest
from app.models.ollama import OllamaProvider

from tests.test_integration.helpers import get_available_ollama_models, is_ollama_reachable

pytestmark = pytest.mark.skipif(
    not is_ollama_reachable(),
    reason="Local Ollama daemon is not running on 127.0.0.1:11434",
)


@pytest.mark.asyncio
async def test_real_ollama_health_and_list() -> None:
    provider = OllamaProvider()
    assert await provider.health_check() is True

    models = await provider.list_models()
    assert len(models) > 0
    available = get_available_ollama_models()
    assert any("llama3.2" in m for m in available)


@pytest.mark.asyncio
async def test_real_ollama_generate() -> None:
    available = get_available_ollama_models()
    if not any("llama3.2" in m for m in available):
        pytest.skip("llama3.2 model not pulled in local Ollama")

    provider = OllamaProvider()
    resp = await provider.generate(
        model="llama3.2:latest",
        prompt="Respond with exactly two words: 'SYSTEM OPERATIONAL'.",
    )
    assert len(resp.content.strip()) > 0
    assert "SYSTEM" in resp.content.upper() or "OPERATIONAL" in resp.content.upper()


@pytest.mark.asyncio
async def test_real_ollama_native_tool_calling() -> None:
    available = get_available_ollama_models()
    if not any("llama3.2" in m for m in available):
        pytest.skip("llama3.2 model not pulled in local Ollama")

    provider = OllamaProvider()
    tools = [
        {
            "type": "function",
            "function": {
                "name": "math_eval",
                "description": "Calculate exact mathematical expressions.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expression": {"type": "string", "description": "Expression to compute"},
                    },
                    "required": ["expression"],
                },
            },
        }
    ]

    messages = [{"role": "user", "content": "Compute 35 * 14 using math_eval."}]
    chat_resp = await provider.chat(
        model="llama3.2:latest",
        messages=messages,
        tools=tools,
    )

    assert chat_resp.message.tool_calls is not None
    assert len(chat_resp.message.tool_calls) > 0
    call = chat_resp.message.tool_calls[0]
    assert call["function"]["name"] == "math_eval"


@pytest.mark.asyncio
async def test_real_ollama_embedding_generation() -> None:
    available = get_available_ollama_models()
    if not any("all-minilm" in m for m in available):
        pytest.skip("all-minilm:l6-v2 embedding model not pulled in local Ollama")

    provider = OllamaProvider()
    texts = ["Turbine rotor vibration threshold", "Emergency cooling valve"]
    res = await provider.embed(model="all-minilm:l6-v2", texts=texts)

    assert len(res.embeddings) == 2
    assert res.dimension == 384
    assert len(res.embeddings[0]) == 384
