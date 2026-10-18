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


def _extract_malformed_tool_call(cand: str, available_tools: set[str]) -> dict[str, Any] | None:
    """Fallback extractor for malformed JSON where code or strings contain unescaped quotes."""
    name_match = re.search(r'["\'](?:name|tool|function)["\']\s*:\s*["\']([a-zA-Z0-9_]+)["\']', cand)
    if not name_match:
        return None
    name = name_match.group(1)
    if name not in available_tools:
        return None

    raw_args: dict[str, Any] = {}
    if name == "code_sandbox":
        code_match = re.search(r'["\']code["\']\s*:\s*"(.*?)"\s*(?:,\s*["\']timeout_s|\s*\})', cand, re.DOTALL)
        if not code_match:
            code_match = re.search(r'["\']code["\']\s*:\s*"(.*)"\s*\}', cand, re.DOTALL)
        if code_match:
            raw_args["code"] = code_match.group(1).replace('\\"', '"').replace('\\n', '\n')

        timeout_match = re.search(r'["\']timeout_s["\']\s*:\s*["\']?(\d+)["\']?', cand)
        if timeout_match:
            raw_args["timeout_s"] = int(timeout_match.group(1))

    elif name == "math_eval":
        expr_match = re.search(r'["\']expression["\']\s*:\s*["\']([^"\']+)["\']', cand)
        if expr_match:
            raw_args["expression"] = expr_match.group(1)
        op_match = re.search(r'["\']operation["\']\s*:\s*["\']([a-zA-Z]+)["\']', cand)
        if op_match:
            raw_args["operation"] = op_match.group(1)
        var_match = re.search(r'["\']variable["\']\s*:\s*["\']([a-zA-Z0-9_]+)["\']', cand)
        if var_match:
            raw_args["variable"] = var_match.group(1)

    elif name == "rag_search":
        q_match = re.search(r'["\']query["\']\s*:\s*["\']([^"\']+)["\']', cand)
        if q_match:
            raw_args["query"] = q_match.group(1)

    elif name == "doc_gen":
        fmt_match = re.search(r'["\']format["\']\s*:\s*["\']([a-zA-Z]+)["\']', cand)
        title_match = re.search(r'["\']title["\']\s*:\s*["\']([^"\']+)["\']', cand)
        if fmt_match:
            raw_args["format"] = fmt_match.group(1)
        if title_match:
            raw_args["title"] = title_match.group(1)

    if raw_args:
        return {"name": name, "arguments": raw_args}
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
            malformed = _extract_malformed_tool_call(cand, available_tools)
            if malformed:
                parsed = malformed
            else:
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

            if "timeout_s" in raw_args:
                try:
                    raw_args["timeout_s"] = int(raw_args["timeout_s"])
                except (ValueError, TypeError):
                    pass

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
