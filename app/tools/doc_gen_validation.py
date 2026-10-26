"""Validation and normalization shared by the agent and doc_gen tool handler."""

from __future__ import annotations

from typing import Any

SUPPORTED_FORMATS = {"docx", "xlsx", "markdown"}


def normalize_doc_gen_input(input_data: Any) -> tuple[dict[str, Any] | None, str | None]:
    """Validate a deliverable request and normalize legacy ``content`` to sections.

    DOCX/Markdown require substantive section text or a non-empty table. XLSX
    requires headers and at least one row. Invalid requests never reach a file
    generator, so they cannot create empty title-only artifacts.
    """
    if not isinstance(input_data, dict):
        return None, "Invalid arguments: doc_gen expects a JSON object."

    fmt_raw = input_data.get("format")
    if not isinstance(fmt_raw, str) or not fmt_raw.strip():
        return None, "Validation failed: 'format' is required for doc_gen."
    fmt = fmt_raw.strip().lower()
    if fmt not in SUPPORTED_FORMATS:
        return None, f"Validation failed: unsupported doc_gen format '{fmt}'."

    title = input_data.get("title")
    if not isinstance(title, str) or not title.strip():
        return None, "Validation failed: 'title' is required and cannot be empty for doc_gen."

    filename = input_data.get("filename")
    if filename is not None and (not isinstance(filename, str) or not filename.strip()):
        return None, "Validation failed: 'filename' must be a non-empty string when supplied."

    raw_sections = input_data.get("sections", [])
    if raw_sections is None:
        raw_sections = []
    if not isinstance(raw_sections, list):
        return None, "Validation failed: 'sections' must be a list of section objects."

    sections: list[dict[str, str | None]] = []
    for index, section in enumerate(raw_sections):
        if not isinstance(section, dict):
            return None, f"Validation failed: sections[{index}] must be an object."
        body = section.get("body")
        if not isinstance(body, str) or not body.strip():
            return None, f"Validation failed: sections[{index}].body is required and cannot be empty."
        heading = section.get("heading")
        if heading is not None and not isinstance(heading, str):
            return None, f"Validation failed: sections[{index}].heading must be a string."
        sections.append({"heading": heading.strip() if isinstance(heading, str) and heading.strip() else None, "body": body.strip()})

    # ``content`` is retained as a compatibility alias for older model/tool calls.
    content = input_data.get("content")
    if content is not None and not isinstance(content, str):
        return None, "Validation failed: 'content' must be a string when supplied."
    if isinstance(content, str) and content.strip() and not sections:
        sections = [{"heading": None, "body": content.strip()}]

    raw_table = input_data.get("table")
    table: dict[str, Any] | None = None
    has_table = False
    if raw_table is not None:
        if not isinstance(raw_table, dict):
            return None, "Validation failed: 'table' must be an object when supplied."
        headers = raw_table.get("headers")
        rows = raw_table.get("rows")
        if not isinstance(headers, list) or not headers or any(not isinstance(h, str) or not h.strip() for h in headers):
            return None, "Validation failed: table.headers must contain non-empty strings."
        if not isinstance(rows, list) or not rows:
            return None, "Validation failed: table.rows must contain at least one data row."
        normalized_rows: list[list[Any]] = []
        for index, row in enumerate(rows):
            if not isinstance(row, list) or len(row) != len(headers):
                return None, f"Validation failed: table.rows[{index}] must have exactly {len(headers)} cells."
            if any(isinstance(value, dict | list) for value in row):
                return None, f"Validation failed: table.rows[{index}] cells must be scalar values."
            normalized_rows.append(row)
        caption = raw_table.get("caption")
        if caption is not None and not isinstance(caption, str):
            return None, "Validation failed: table.caption must be a string."
        table = {
            "headers": [header.strip() for header in headers],
            "rows": normalized_rows,
            "caption": caption,
        }
        has_table = True

    if fmt == "xlsx":
        if not has_table:
            return None, "Validation failed: XLSX generation requires non-empty table headers and at least one data row."
    elif not sections and not has_table:
        return None, f"Validation failed: {fmt} generation requires non-empty section content or a non-empty table."

    normalized: dict[str, Any] = {
        "format": fmt,
        "title": title.strip(),
        "sections": sections,
        "table": table,
    }
    if filename is not None:
        normalized["filename"] = filename.strip()
    return normalized, None
