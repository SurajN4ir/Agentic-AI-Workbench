"""
app/agent/parser.py
===================
Robust fallback tool call parser for open-weight models that emit JSON in text.
Strips markdown code fences, normalizes alternative field keys, and validates
against permitted tool registry names.
"""

import json
import logging
import re
import uuid
from typing import Any

logger = logging.getLogger("sovereign.agent.parser")

_FENCE_REGEX = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```")
_TRAILING_COMMA_REGEX = re.compile(r",\s*([\]\}])")


def _try_parse_json(text: str) -> Any | None:
    """Attempts standard json parse, followed by trailing-comma cleanup."""
    try:
        return json.loads(text)
    except Exception:
        try:
            cleaned = _TRAILING_COMMA_REGEX.sub(r"\1", text)
            return json.loads(cleaned)
        except Exception:
            return None


def parse_json_tool_calls(
    content: str,
    available_tools: set[str],
) -> list[dict[str, Any]]:
    """
    Scans model output text for JSON tool call payloads.
    Returns a list of standardized OpenAI/Ollama tool call dictionaries:
    [
        {
            "id": "call_...",
            "function": {
                "name": "tool_name",
                "arguments": {...}
            }
        }
    ]
    """
    if not content or not content.strip():
        return []

    text = content.strip()
    candidates: list[str] = []

    # Check for markdown code fences first
    for match in _FENCE_REGEX.finditer(text):
        candidates.append(match.group(1).strip())

    # Also search for outermost JSON objects/arrays directly in raw text
    start_brace = text.find("{")
    end_brace = text.rfind("}")
    if start_brace != -1 and end_brace > start_brace:
        candidates.append(text[start_brace : end_brace + 1].strip())

    start_bracket = text.find("[")
    end_bracket = text.rfind("]")
    if start_bracket != -1 and end_bracket > start_bracket:
        candidates.append(text[start_bracket : end_bracket + 1].strip())

    tool_calls: list[dict[str, Any]] = []

    for cand in candidates:
        parsed = _try_parse_json(cand)
        if parsed is None:
            continue

        items = parsed if isinstance(parsed, list) else [parsed]
        for item in items:
            if not isinstance(item, dict):
                continue

            name = item.get("name") or item.get("tool") or item.get("function")
            if isinstance(name, dict):
                name = name.get("name")

            if not isinstance(name, str) or name not in available_tools:
                continue

            # Extract arguments
            raw_args = (
                item.get("arguments")
                or item.get("args")
                or item.get("parameters")
                or item.get("params")
                or {}
            )

            if isinstance(raw_args, str):
                parsed_args = _try_parse_json(raw_args)
                raw_args = parsed_args if isinstance(parsed_args, dict) else {}

            if not isinstance(raw_args, dict):
                raw_args = {}

            call_id = f"call_{uuid.uuid4().hex[:8]}"
            tool_calls.append(
                {
                    "id": call_id,
                    "function": {
                        "name": name,
                        "arguments": raw_args,
                    },
                }
            )

        if tool_calls:
            # Successfully extracted valid tool calls from this candidate
            break

    return tool_calls
