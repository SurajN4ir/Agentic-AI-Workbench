"""
tests/test_agent/test_graph.py
==============================
Integration tests for LangGraph Agent StateGraph execution:
  - Routing and system prompt initialization
  - Single-turn direct response
  - Multi-step ReAct tool execution loop
  - Safety bounds (max_iterations cutoff preventing infinite loops)
  - RBAC permission enforcement within graph
"""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from app.agent.graph import AgentGraphBuilder
from app.agent.state import WorkbenchState
from app.models.base import BaseModelProvider
from app.models.schemas import (
    ChatMessage,
    ChatResponse,
    EmbeddingResponse,
    GenerateOptions,
    ModelResponse,
)
from app.routing.service import TaskRouter
from app.tools.registry import ToolRegistry


class MockDirectProvider(BaseModelProvider):
    """Returns direct text response without any tool calls."""

    async def generate(self, model: str, prompt: str, system: str | None = None, options: GenerateOptions | None = None) -> ModelResponse:
        return ModelResponse(content="Direct response", model=model)

    async def stream(self, model: str, prompt: str, system: str | None = None, options: GenerateOptions | None = None) -> AsyncIterator[str]:
        yield "Direct response"

    async def chat(self, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, options: GenerateOptions | None = None) -> ChatResponse:
        return ChatResponse(
            message=ChatMessage(role="assistant", content="Direct reasoning response without tool usage."),
            thinking_content="I analyzed the input directly.",
            model=model,
            total_duration_ms=10.0,
        )

    async def stream_chat(self, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, options: GenerateOptions | None = None) -> AsyncIterator[dict[str, Any]]:
        yield {"message": {"role": "assistant", "content": "Direct reasoning response"}}

    async def embed(self, model: str, texts: list[str]) -> EmbeddingResponse:
        return EmbeddingResponse(embeddings=[[0.1] * 768 for _ in texts], model=model, dimension=768)

    async def list_models(self) -> list[str]:
        return ["qwen2.5:3b"]

    async def health_check(self) -> bool:
        return True


def test_graph_forces_rag_search_for_routed_knowledge_request() -> None:
    builder = AgentGraphBuilder()
    decision = TaskRouter().route(
        "According to the uploaded specification, what is the vibration alarm threshold?"
    )
    requirement = builder.determine_unsatisfied_tool_requirement(
        {
            "user_role": "analyst",
            "prompt": "According to the uploaded specification, what is the vibration alarm threshold?",
            "route_decision": decision.model_dump(),
            "tool_results": [],
            "final_response": "The threshold is 4.5 mm/s.",
        }
    )
    assert requirement is not None
    assert requirement[0] == "rag_search"
    assert "MUST invoke 'rag_search'" in requirement[1]


class MockMathToolProvider(BaseModelProvider):
    """First turn returns a math_eval tool call, second turn synthesizes result."""

    def __init__(self) -> None:
        self.call_count = 0

    async def generate(self, model: str, prompt: str, system: str | None = None, options: GenerateOptions | None = None) -> ModelResponse:
        return ModelResponse(content="Math done", model=model)

    async def stream(self, model: str, prompt: str, system: str | None = None, options: GenerateOptions | None = None) -> AsyncIterator[str]:
        yield "Math done"

    async def chat(self, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, options: GenerateOptions | None = None) -> ChatResponse:
        self.call_count += 1
        # Check if the last message is a tool response
        last_msg = messages[-1] if messages else {}
        if last_msg.get("role") == "tool":
            return ChatResponse(
                message=ChatMessage(role="assistant", content="Based on the tool calculation, the solution is x = 5."),
                model=model,
                total_duration_ms=15.0,
            )

        # First turn: call math_eval
        return ChatResponse(
            message=ChatMessage(
                role="assistant",
                content="",
                tool_calls=[
                    {
                        "id": "call_math_1",
                        "function": {
                            "name": "math_eval",
                            "arguments": {"expression": "2*x - 10 = 0", "operation": "solve", "variable": "x"},
                        },
                    }
                ],
            ),
            thinking_content="I need to solve the linear equation using math_eval.",
            model=model,
            total_duration_ms=20.0,
        )

    async def stream_chat(self, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, options: GenerateOptions | None = None) -> AsyncIterator[dict[str, Any]]:
        yield {}

    async def embed(self, model: str, texts: list[str]) -> EmbeddingResponse:
        return EmbeddingResponse(embeddings=[[0.1] * 768 for _ in texts], model=model, dimension=768)

    async def list_models(self) -> list[str]:
        return ["qwen2.5:3b"]

    async def health_check(self) -> bool:
        return True


class MockInfiniteToolProvider(BaseModelProvider):
    """Simulates a runaway model that constantly returns tool calls on every invocation."""

    async def generate(self, model: str, prompt: str, system: str | None = None, options: GenerateOptions | None = None) -> ModelResponse:
        return ModelResponse(content="", model=model)

    async def stream(self, model: str, prompt: str, system: str | None = None, options: GenerateOptions | None = None) -> AsyncIterator[str]:
        yield ""

    async def chat(self, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, options: GenerateOptions | None = None) -> ChatResponse:
        return ChatResponse(
            message=ChatMessage(
                role="assistant",
                content="",
                tool_calls=[
                    {
                        "id": "call_loop",
                        "function": {
                            "name": "math_eval",
                            "arguments": {"expression": "1 + 1", "operation": "eval"},
                        },
                    }
                ],
            ),
            model=model,
            total_duration_ms=5.0,
        )

    async def stream_chat(self, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, options: GenerateOptions | None = None) -> AsyncIterator[dict[str, Any]]:
        yield {}

    async def embed(self, model: str, texts: list[str]) -> EmbeddingResponse:
        return EmbeddingResponse(embeddings=[[0.1] * 768], model=model, dimension=768)

    async def list_models(self) -> list[str]:
        return ["qwen2.5:3b"]

    async def health_check(self) -> bool:
        return True


@pytest.mark.asyncio
async def test_graph_direct_reasoning():
    """Verifies single-turn reasoning path without tool execution."""
    provider = MockDirectProvider()
    builder = AgentGraphBuilder(provider=provider)
    graph = builder.build()

    state: WorkbenchState = {
        "session_id": "test_direct_session",
        "user_id": "00000000-0000-0000-0000-000000000001",
        "user_role": "user",
        "username": "tester",
        "prompt": "What is the capital of sovereign architecture?",
        "max_iterations": 5,
        "iteration_count": 0,
        "status": "initialized",
    }

    final_state = await graph.ainvoke(state)
    assert final_state["status"] == "completed"
    assert "Direct reasoning response" in final_state["final_response"]
    assert final_state["iteration_count"] == 0
    assert len(final_state["thinking_trace"]) == 1


@pytest.mark.asyncio
async def test_graph_multistep_react_tool_execution():
    """Verifies full ReAct loop: reasoning -> tool dispatch -> math evaluation -> response synthesis."""
    provider = MockMathToolProvider()
    registry = ToolRegistry()
    builder = AgentGraphBuilder(provider=provider, tool_registry=registry)
    graph = builder.build()

    state: WorkbenchState = {
        "session_id": "test_math_session",
        "user_id": "00000000-0000-0000-0000-000000000001",
        "user_role": "user",
        "username": "tester",
        "prompt": "Solve 2*x - 10 = 0",
        "max_iterations": 5,
        "iteration_count": 0,
        "status": "initialized",
    }

    final_state = await graph.ainvoke(state)
    assert final_state["status"] == "completed"
    assert "x = 5" in final_state["final_response"]
    assert final_state["iteration_count"] == 1
    assert len(final_state["tool_results"]) == 1
    assert final_state["tool_results"][0]["tool_name"] == "math_eval"
    assert final_state["tool_results"][0]["status"] == "success"
    assert "5" in str(final_state["tool_results"][0]["output"])


@pytest.mark.asyncio
async def test_graph_loop_safety_bound_cutoff():
    """
    CRITICAL SECURITY & RELIABILITY TEST:
    Verifies that when a model continuously issues tool calls,
    the StateGraph halts at max_iterations without hanging or infinite loops.
    """
    provider = MockInfiniteToolProvider()
    builder = AgentGraphBuilder(provider=provider)
    graph = builder.build()

    state: WorkbenchState = {
        "session_id": "test_loop_cutoff",
        "user_id": "00000000-0000-0000-0000-000000000001",
        "user_role": "user",
        "username": "tester",
        "prompt": "Infinite loop test",
        "max_iterations": 3,  # Hard stop at 3 iterations
        "iteration_count": 0,
        "status": "initialized",
    }

    final_state = await graph.ainvoke(state)
    # Loop must terminate with max_iterations_reached status
    assert final_state["status"] == "max_iterations_reached"
    assert final_state["iteration_count"] == 3
    assert "Reached maximum tool execution limit" in final_state["final_response"]
    assert len(final_state["tool_results"]) == 3


@pytest.mark.asyncio
async def test_graph_rbac_tool_denial():
    """Verifies that an unauthorized tool invocation (e.g. code_sandbox by regular user) is denied by RBAC."""
    class MockSandboxCaller(BaseModelProvider):
        def __init__(self) -> None:
            self.turn = 0

        async def generate(self, model: str, prompt: str, system: str | None = None, options: GenerateOptions | None = None) -> ModelResponse:
            return ModelResponse(content="", model=model)

        async def stream(self, model: str, prompt: str, system: str | None = None, options: GenerateOptions | None = None) -> AsyncIterator[str]:
            yield ""

        async def chat(self, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, options: GenerateOptions | None = None) -> ChatResponse:
            self.turn += 1
            if self.turn > 1:
                return ChatResponse(message=ChatMessage(role="assistant", content="Execution was blocked by policy."), model=model)
            return ChatResponse(
                message=ChatMessage(
                    role="assistant",
                    content="",
                    tool_calls=[{"id": "call_sec", "function": {"name": "code_sandbox", "arguments": {"code": "import os; print('hack')"}}}],
                ),
                model=model,
            )

        async def stream_chat(self, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, options: GenerateOptions | None = None) -> AsyncIterator[dict[str, Any]]:
            yield {}

        async def embed(self, model: str, texts: list[str]) -> EmbeddingResponse:
            return EmbeddingResponse(embeddings=[[0.1] * 768], model=model, dimension=768)

        async def list_models(self) -> list[str]:
            return ["qwen2.5:3b"]

        async def health_check(self) -> bool:
            return True

    builder = AgentGraphBuilder(provider=MockSandboxCaller())
    graph = builder.build()

    # User role is 'user', which is NOT allowed to call 'code_sandbox'
    state: WorkbenchState = {
        "session_id": "test_rbac_denial",
        "user_id": "00000000-0000-0000-0000-000000000001",
        "user_role": "user",
        "username": "regular_user",
        "prompt": "Run arbitrary code",
        "max_iterations": 5,
        "iteration_count": 0,
        "status": "initialized",
    }

    final_state = await graph.ainvoke(state)
    assert len(final_state["tool_results"]) == 1
    res = final_state["tool_results"][0]
    assert res["status"] == "error"
    assert "Permission denied" in str(res["error"])


class MockRetryThenSucceedProvider(BaseModelProvider):
    """Simulates a model that initially returns prose calculation, but on directive invokes math_eval."""

    def __init__(self) -> None:
        self.call_count = 0

    async def generate(self, model: str, prompt: str, system: str | None = None, options: GenerateOptions | None = None) -> ModelResponse:
        return ModelResponse(content="", model=model)

    async def stream(self, model: str, prompt: str, system: str | None = None, options: GenerateOptions | None = None) -> AsyncIterator[str]:
        yield ""

    async def chat(self, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, options: GenerateOptions | None = None) -> ChatResponse:
        self.call_count += 1
        last_msg = messages[-1] if messages else {}

        # Turn 3: Received tool execution output
        if last_msg.get("role") == "tool":
            return ChatResponse(
                message=ChatMessage(role="assistant", content="The verified steady-state conversion is X_A = 0.50."),
                model=model,
            )

        # Turn 2: Received retry directive from system
        if "[SYSTEM TOOL DISPATCH DIRECTIVE]" in str(last_msg.get("content", "")):
            return ChatResponse(
                message=ChatMessage(
                    role="assistant",
                    content="",
                    tool_calls=[{
                        "id": "call_retry_math",
                        "function": {
                            "name": "math_eval",
                            "arguments": {"expression": "0.05 * 50 * 2.0 / (1 + 0.05 * 50 * 2.0)", "operation": "eval"},
                        },
                    }],
                ),
                model=model,
            )

        # Turn 1: Stubbornly returns prose without tool call
        return ChatResponse(
            message=ChatMessage(role="assistant", content="The steady-state conversion is approximately 50% calculated mentally."),
            model=model,
        )

    async def stream_chat(self, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, options: GenerateOptions | None = None) -> AsyncIterator[dict[str, Any]]:
        yield {}

    async def embed(self, model: str, texts: list[str]) -> EmbeddingResponse:
        return EmbeddingResponse(embeddings=[[0.1] * 768], model=model, dimension=768)

    async def list_models(self) -> list[str]:
        return ["qwen2.5:3b"]

    async def health_check(self) -> bool:
        return True


@pytest.mark.asyncio
async def test_graph_tool_retry_when_tool_missing_then_invoked():
    """
    REGRESSION TEST:
    Verifies that when a computation task (CSTR conversion) is answered in prose without a tool call,
    the StateGraph detects the unsatisfied requirement, triggers retry_node, prompts the model,
    and successfully completes once the tool is invoked.
    """
    provider = MockRetryThenSucceedProvider()
    builder = AgentGraphBuilder(provider=provider)
    graph = builder.build()

    state: WorkbenchState = {
        "session_id": "test_tool_retry_success",
        "user_id": "00000000-0000-0000-0000-000000000001",
        "user_role": "user",
        "username": "engineer",
        "prompt": "Calculate the steady-state conversion for a second-order reaction in a CSTR with V=500L, v0=10L/min, k=0.05 L/(mol*min), CA0=2.0 mol/L.",
        "max_iterations": 8,
        "iteration_count": 0,
        "status": "initialized",
    }

    final_state = await graph.ainvoke(state)
    assert final_state["status"] == "completed"
    assert final_state["tool_retry_count"] == 1
    assert len(final_state["tool_results"]) == 1
    assert final_state["tool_results"][0]["tool_name"] == "math_eval"
    assert "0.50" in final_state["final_response"]


class MockStubbornProseProvider(BaseModelProvider):
    """Never issues tool calls, always returns prose code block."""

    async def generate(self, model: str, prompt: str, system: str | None = None, options: GenerateOptions | None = None) -> ModelResponse:
        return ModelResponse(content="", model=model)

    async def stream(self, model: str, prompt: str, system: str | None = None, options: GenerateOptions | None = None) -> AsyncIterator[str]:
        yield ""

    async def chat(self, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, options: GenerateOptions | None = None) -> ChatResponse:
        return ChatResponse(
            message=ChatMessage(
                role="assistant",
                content="Here is the calibration script:\n```python\nimport numpy as np\nprint('calibrated')\n```",
            ),
            model=model,
        )

    async def stream_chat(self, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, options: GenerateOptions | None = None) -> AsyncIterator[dict[str, Any]]:
        yield {}

    async def embed(self, model: str, texts: list[str]) -> EmbeddingResponse:
        return EmbeddingResponse(embeddings=[[0.1] * 768], model=model, dimension=768)

    async def list_models(self) -> list[str]:
        return ["qwen2.5:3b"]

    async def health_check(self) -> bool:
        return True


@pytest.mark.asyncio
async def test_graph_tool_retry_exhaustion_bounds():
    """
    CRITICAL BOUNDS TEST:
    Verifies that when a model stubbornly returns prose and ignores retry directives,
    the StateGraph halts exactly after 2 retries without hanging or infinite loop.
    """
    provider = MockStubbornProseProvider()
    builder = AgentGraphBuilder(provider=provider)
    graph = builder.build()

    state: WorkbenchState = {
        "session_id": "test_retry_exhaustion",
        "user_id": "00000000-0000-0000-0000-000000000001",
        "user_role": "analyst",
        "username": "analyst_user",
        "prompt": "Perform linear calibration regression on sensor calibration data",
        "max_iterations": 8,
        "iteration_count": 0,
        "status": "initialized",
    }

    final_state = await graph.ainvoke(state)
    assert final_state["status"] == "completed"
    assert final_state["tool_retry_count"] == 2
    # Verify iteration count bounded properly
    assert final_state["iteration_count"] <= 8


@pytest.mark.asyncio
async def test_graph_tool_argument_validation_failure():
    """
    SECURITY & VALIDATION TEST:
    Verifies that malformed or empty tool parameters (e.g. empty code string)
    fail validation cleanly at tool_node before execution.
    """
    class MockBadArgCaller(BaseModelProvider):
        def __init__(self) -> None:
            self.turn = 0

        async def generate(self, model: str, prompt: str, system: str | None = None, options: GenerateOptions | None = None) -> ModelResponse:
            return ModelResponse(content="", model=model)

        async def stream(self, model: str, prompt: str, system: str | None = None, options: GenerateOptions | None = None) -> AsyncIterator[str]:
            yield ""

        async def chat(self, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, options: GenerateOptions | None = None) -> ChatResponse:
            self.turn += 1
            if self.turn > 1:
                return ChatResponse(message=ChatMessage(role="assistant", content="Handled invalid argument."), model=model)
            return ChatResponse(
                message=ChatMessage(
                    role="assistant",
                    content="",
                    tool_calls=[{"id": "call_bad_args", "function": {"name": "code_sandbox", "arguments": {"code": "   "}}}],
                ),
                model=model,
            )

        async def stream_chat(self, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, options: GenerateOptions | None = None) -> AsyncIterator[dict[str, Any]]:
            yield {}

        async def embed(self, model: str, texts: list[str]) -> EmbeddingResponse:
            return EmbeddingResponse(embeddings=[[0.1] * 768], model=model, dimension=768)

        async def list_models(self) -> list[str]:
            return ["qwen2.5:3b"]

        async def health_check(self) -> bool:
            return True

    builder = AgentGraphBuilder(provider=MockBadArgCaller())
    graph = builder.build()

    state: WorkbenchState = {
        "session_id": "test_bad_arg_validation",
        "user_id": "00000000-0000-0000-0000-000000000001",
        "user_role": "admin",  # admin has code_sandbox permission
        "username": "admin_user",
        "prompt": "Run code in sandbox",
        "max_iterations": 5,
        "iteration_count": 0,
        "status": "initialized",
    }

    final_state = await graph.ainvoke(state)
    assert len(final_state["tool_results"]) == 1
    res = final_state["tool_results"][0]
    assert res["status"] == "error"
    assert "Validation failed" in str(res["error"])
    assert res["metadata"].get("validation_failed") is True

