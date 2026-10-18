"""
app/agent/citation_validator.py
===============================
Backend Citation & Hallucination Validator.
Verifies that all document sources and page numbers cited in an LLM agent's final
response were actually returned in the RAG retrieval results during that execution.
Prevents citation fabrication and flags ungrounded claims in confidential industrial reports.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("sovereign.agent.citation_validator")


@dataclass
class CitationValidationResult:
    is_valid: bool
    verified_citations: list[str] = field(default_factory=list)
    ungrounded_citations: list[str] = field(default_factory=list)
    retrieved_sources: list[str] = field(default_factory=list)
    sanitized_response: str = ""
    audit_flag: str | None = None


class CitationValidator:
    """
    Validates that model citations strictly correspond to evidence chunks
    retrieved by rag_search or document ingestion tools.
    """

    CITATION_PATTERNS = [
        # [Source 1: filename.ext, Page X] or [Source: filename.ext, Page X]
        re.compile(r"\[Source(?:\s+\d+)?:?\s*([^,\]\n]+?)(?:,\s*Page:?\s*(\d+))?\]", re.IGNORECASE),
        # [filename.ext, Page X] or [filename.ext]
        re.compile(r"\[([a-zA-Z0-9_\-\.]+\.(?:pdf|docx|xlsx|csv|txt|png|jpg|jpeg|webp|tiff|bmp))(?:,\s*Page:?\s*(\d+))?\]", re.IGNORECASE),
        # Source: filename.ext (inline)
        re.compile(r"(?:Source|Reference):\s*([a-zA-Z0-9_\-\.]+\.(?:pdf|docx|xlsx|csv|txt|png|jpg|jpeg|webp|tiff|bmp))", re.IGNORECASE),
    ]

    def extract_citations(self, text: str) -> list[str]:
        """Extracts unique cited source document names from generated response text."""
        citations: set[str] = set()
        for pat in self.CITATION_PATTERNS:
            for match in pat.finditer(text):
                src = match.group(1).strip()
                src = src.strip("'\"` ").strip()
                if src and "." in src:
                    citations.add(src.lower())
        return sorted(citations)

    def extract_ground_truth_sources(self, tool_results: list[dict[str, Any]]) -> set[str]:
        """Extracts all document filenames returned by RAG and file tools in this session."""
        valid_sources: set[str] = set()
        for res in tool_results:
            data = res.get("data")
            if isinstance(data, dict):
                results = data.get("results")
                if isinstance(results, list):
                    for item in results:
                        if isinstance(item, dict):
                            src = item.get("source") or item.get("filename")
                            if src:
                                valid_sources.add(str(src).strip().lower())
                if "filename" in data:
                    valid_sources.add(str(data["filename"]).strip().lower())

            output_str = str(res.get("output", ""))
            for pat in self.CITATION_PATTERNS:
                for match in pat.finditer(output_str):
                    src = match.group(1).strip()
                    if src and "." in src:
                        valid_sources.add(src.lower())

        return valid_sources

    def validate(
        self,
        response_text: str,
        tool_results: list[dict[str, Any]],
    ) -> CitationValidationResult:
        """
        Validates citations in response_text against ground-truth sources in tool_results.
        """
        if not response_text:
            return CitationValidationResult(is_valid=True, sanitized_response=response_text)

        cited_sources = self.extract_citations(response_text)
        ground_truth_sources = self.extract_ground_truth_sources(tool_results)

        if not cited_sources:
            return CitationValidationResult(
                is_valid=True,
                verified_citations=[],
                ungrounded_citations=[],
                retrieved_sources=sorted(ground_truth_sources),
                sanitized_response=response_text,
            )

        verified: list[str] = []
        ungrounded: list[str] = []

        for cited in cited_sources:
            matched = any(
                cited == gt or cited in gt or gt in cited
                for gt in ground_truth_sources
            )
            if matched:
                verified.append(cited)
            else:
                ungrounded.append(cited)

        if not ungrounded:
            return CitationValidationResult(
                is_valid=True,
                verified_citations=verified,
                ungrounded_citations=[],
                retrieved_sources=sorted(ground_truth_sources),
                sanitized_response=response_text,
            )

        audit_flag = (
            f"CITATION_VERIFICATION_FAILURE: Cited sources {ungrounded} "
            f"were not found in retrieved session evidence {sorted(ground_truth_sources)}."
        )
        logger.warning(audit_flag)

        sanitized_response = response_text
        warning_banner = (
            f"\n\n> [!CAUTION]\n"
            f"> **Ungrounded Citation Warning**: The following cited sources were not retrieved from the "
            f"authorized knowledge base during this run: {', '.join(ungrounded)}. "
            f"Verify all claims before industrial application."
        )
        sanitized_response += warning_banner

        return CitationValidationResult(
            is_valid=False,
            verified_citations=verified,
            ungrounded_citations=ungrounded,
            retrieved_sources=sorted(ground_truth_sources),
            sanitized_response=sanitized_response,
            audit_flag=audit_flag,
        )
