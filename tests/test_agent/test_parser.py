"""
tests/test_agent/test_parser.py
===============================
Unit tests for fallback JSON tool call parser.
"""

from app.agent.parser import parse_json_tool_calls

AVAILABLE_TOOLS = {"math_eval", "code_sandbox", "rag_search"}


def test_parse_markdown_fence_json():
    """Extracts tool call from markdown json code block."""
    content = """I will evaluate this integral for you.
```json
{
  "name": "math_eval",
  "arguments": {
    "expression": "integrate(x**2, x)",
    "operation": "integrate"
  }
}
```
Let me compute this now."""

    calls = parse_json_tool_calls(content, AVAILABLE_TOOLS)
    assert len(calls) == 1
    call = calls[0]
    assert call["function"]["name"] == "math_eval"
    assert call["function"]["arguments"]["expression"] == "integrate(x**2, x)"
    assert call["function"]["arguments"]["operation"] == "integrate"
    assert call["id"].startswith("call_")


def test_parse_raw_json_without_fences():
    """Extracts tool call from raw JSON embedded in text."""
    content = '{"name": "math_eval", "arguments": {"expression": "2 + 2"}}'
    calls = parse_json_tool_calls(content, AVAILABLE_TOOLS)
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "math_eval"
    assert calls[0]["function"]["arguments"]["expression"] == "2 + 2"


def test_parse_alternative_keys():
    """Tests alternative keys like tool/parameters and args."""
    content = """```json
    {
      "tool": "code_sandbox",
      "parameters": {
        "code": "print('hello from sandbox')",
        "timeout_s": 15
      }
    }
    ```"""
    calls = parse_json_tool_calls(content, AVAILABLE_TOOLS)
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "code_sandbox"
    assert calls[0]["function"]["arguments"]["code"] == "print('hello from sandbox')"
    assert calls[0]["function"]["arguments"]["timeout_s"] == 15


def test_parse_json_array_of_calls():
    """Tests multiple tool calls specified in a JSON array."""
    content = """```json
    [
      {"name": "math_eval", "arguments": {"expression": "2*x"}},
      {"name": "rag_search", "arguments": {"query": "safety valve pressure"}}
    ]
    ```"""
    calls = parse_json_tool_calls(content, AVAILABLE_TOOLS)
    assert len(calls) == 2
    assert calls[0]["function"]["name"] == "math_eval"
    assert calls[1]["function"]["name"] == "rag_search"
    assert calls[1]["function"]["arguments"]["query"] == "safety valve pressure"


def test_ignore_unregistered_tools():
    """Filters out hallucinated or unregistered tool names."""
    content = """```json
    {"name": "non_existent_shell_hack", "arguments": {"cmd": "rm -rf /"}}
    ```"""
    calls = parse_json_tool_calls(content, AVAILABLE_TOOLS)
    assert calls == []


def test_resilience_to_malformed_text():
    """Verifies that plain text or malformed JSON does not crash the parser."""
    assert parse_json_tool_calls("", AVAILABLE_TOOLS) == []
    assert parse_json_tool_calls("   \n\t  ", AVAILABLE_TOOLS) == []
    assert parse_json_tool_calls("Regular assistant response with no tools.", AVAILABLE_TOOLS) == []
    assert parse_json_tool_calls("```json\n{ broken json here \n```", AVAILABLE_TOOLS) == []
