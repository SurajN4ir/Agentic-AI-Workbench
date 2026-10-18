"""
app/agent/citation_validator.py
===============================
Backend Citation & Hallucination Validator.
Verifies that all document sources, page numbers, and factual numerical claims cited in
an LLM agent's response are genuinely grounded in evidence chunks retrieved by RAG tools.
Distinguishes citation existence from claim-to-evidence support.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("sovereign.agent.citation_validator")


class CitationSupportStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED_NUMERIC = "UNSUPPORTED_NUMERIC"
    FABRICATED_SOURCE = "FABRICATED_SOURCE"
    FABRICATED_PAGE = "FABRICATED_PAGE"
    EMPTY_RETRIEVAL = "EMPTY_RETRIEVAL"
    UNVERIFIABLE_SEMANTIC = "UNVERIFIABLE_SEMANTIC"


@dataclass
class CitationAuditDetail:
    citation_text: str
    source_file: str
    page_number: int | None
    associated_sentence: str
    status: CitationSupportStatus
    reason: str
    extracted_numbers: list[str] = field(default_factory=list)
    ground_truth_numbers: list[str] = field(default_factory=list)


@dataclass
class CitationValidationResult:
    is_valid: bool
    verified_citations: list[str] = field(default_factory=list)
    ungrounded_citations: list[str] = field(default_factory=list)
    retrieved_sources: list[str] = field(default_factory=list)
    details: list[CitationAuditDetail] = field(default_factory=list)
    conflicting_sources: list[str] = field(default_factory=list)
    sanitized_response: str = ""
    audit_flag: str | None = None
    audit_flags: list[str] = field(default_factory=list)


@dataclass
class EvidenceChunk:
    source: str
    page: int | None
    content: str
    numbers: set[str] = field(default_factory=set)


class CitationValidator:
    """
    Validates model citations and claim support against retrieved RAG evidence chunks.
    Ensures filename existence, page number authenticity, and numerical claim alignment.
    """

    CITATION_PATTERN = re.compile(
        r"\[(?:Source(?:\s+\d+)?:?\s*)?([a-zA-Z0-9_\-\.]+\.(?:pdf|docx|xlsx|csv|txt|png|jpg|jpeg|webp|tiff|bmp))(?:\s*,\s*Page:?\s*(\d+))?\]",
        re.IGNORECASE,
    )

    NUM_PATTERN = re.compile(r"\b\d+(?:\.\d+)?%?\b")

    @classmethod
    def extract_numbers(cls, text: str) -> set[str]:
        """Extracts normalized numeric tokens from text."""
        tokens = set()
        for match in cls.NUM_PATTERN.finditer(text):
            val = match.group(0).strip()
            clean = val.rstrip(".")
            if clean:
                tokens.add(clean)
        return tokens

    def extract_evidence_chunks(self, tool_results: list[dict[str, Any]]) -> list[EvidenceChunk]:
        """Extracts structured evidence chunks from RAG and document tool outputs."""
        chunks: list[EvidenceChunk] = []

        for res in tool_results:
            data = res.get("data")
            has_structured_chunks = False
            if isinstance(data, dict):
                results = data.get("results")
                if isinstance(results, list):
                    for item in results:
                        if isinstance(item, dict):
                            src = str(item.get("source") or item.get("filename") or "").strip().lower()
                            page = item.get("page")
                            page_int = int(page) if page is not None and str(page).isdigit() else None
                            content = str(item.get("content") or "")
                            if src and content:
                                has_structured_chunks = True
                                chunks.append(
                                    EvidenceChunk(
                                        source=src,
                                        page=page_int,
                                        content=content,
                                        numbers=self.extract_numbers(content),
                                    )
                                )

            # Only fallback to scanning output_str if structured results were not present
            if not has_structured_chunks:
                output_str = str(res.get("output", ""))
                if "[Source" in output_str:
                    for match in self.CITATION_PATTERN.finditer(output_str):
                        src = match.group(1).strip().lower()
                        page = match.group(2) if len(match.groups()) >= 2 else None
                        page_int = int(page) if page and page.isdigit() else None
                        chunks.append(
                            EvidenceChunk(
                                source=src,
                                page=page_int,
                                content=output_str,
                                numbers=self.extract_numbers(output_str),
                            )
                        )

        return chunks

    def extract_citations(self, text: str) -> list[str]:
        """Extracts unique cited source document names from generated response text."""
        citations: set[str] = set()
        for match in self.CITATION_PATTERN.finditer(text):
            src = match.group(1).strip().strip("'\"` ").lower()
            if src and "." in src:
                citations.add(src)
        return sorted(citations)

    def extract_ground_truth_sources(self, tool_results: list[dict[str, Any]]) -> set[str]:
        """Extracts unique document filenames returned in session tool results."""
        chunks = self.extract_evidence_chunks(tool_results)
        return {c.source for c in chunks}

    def detect_conflicting_evidence(self, chunks: list[EvidenceChunk]) -> list[str]:
        """Detects whether multiple chunks for the same source contain divergent numeric telemetry."""
        conflicts: list[str] = []
        by_source: dict[str, list[EvidenceChunk]] = {}
        for c in chunks:
            by_source.setdefault(c.source, []).append(c)

        for src, src_chunks in by_source.items():
            if len(src_chunks) > 1:
                all_nums = [c.numbers for c in src_chunks if c.numbers]
                if len(all_nums) >= 2 and all_nums[0] != all_nums[1]:
                    diff = all_nums[0].symmetric_difference(all_nums[1])
                    if diff:
                        conflicts.append(
                            f"Source '{src}' contains multiple chunks with differing numerical specifications: {sorted(diff)}"
                        )
        return conflicts

    def validate(
        self,
        response_text: str,
        tool_results: list[dict[str, Any]],
    ) -> CitationValidationResult:
        """
        Comprehensive validation of citations, page references, and numerical claims
        against session tool evidence.
        """
        if not response_text:
            return CitationValidationResult(is_valid=True, sanitized_response=response_text)

        chunks = self.extract_evidence_chunks(tool_results)
        ground_truth_sources = {c.source for c in chunks}
        conflicts = self.detect_conflicting_evidence(chunks)

        # Split response into sentences for granular claim attribution
        raw_sentences = re.split(r"(?<=[.!?])\s+", response_text)
        details: list[CitationAuditDetail] = []
        verified: list[str] = []
        ungrounded: list[str] = []
        audit_flags: list[str] = []

        total_citations_found = 0

        for sent in raw_sentences:
            matches = list(self.CITATION_PATTERN.finditer(sent))
            for match in matches:
                total_citations_found += 1
                raw_cit = match.group(0).strip()
                src_file = match.group(1).strip().strip("'\"` ").lower()
                page_str = match.group(2) if len(match.groups()) >= 2 and match.group(2) else None
                page_num = int(page_str) if page_str and page_str.isdigit() else None

                # Extract numbers only from the claim portion of the sentence (excluding citation block)
                claim_text = sent.replace(raw_cit, "")
                sent_numbers = self.extract_numbers(claim_text)

                # 1. Empty retrieval check
                if not chunks:
                    status = CitationSupportStatus.EMPTY_RETRIEVAL
                    reason = "No documents were retrieved by RAG, but response asserts source citations."
                    ungrounded.append(src_file)
                    flag = f"CITATION_VERIFICATION_FAILURE: Empty retrieval for citation '{raw_cit}'"
                    audit_flags.append(flag)
                    details.append(
                        CitationAuditDetail(
                            citation_text=raw_cit,
                            source_file=src_file,
                            page_number=page_num,
                            associated_sentence=sent,
                            status=status,
                            reason=reason,
                            extracted_numbers=sorted(sent_numbers),
                        )
                    )
                    continue

                # 2. Fabricated source file check
                matching_chunks = [c for c in chunks if c.source == src_file or src_file in c.source or c.source in src_file]
                if not matching_chunks:
                    status = CitationSupportStatus.FABRICATED_SOURCE
                    reason = f"Source '{src_file}' was not found in retrieved session evidence {sorted(ground_truth_sources)}."
                    ungrounded.append(src_file)
                    flag = f"CITATION_VERIFICATION_FAILURE: Fabricated source '{src_file}'"
                    audit_flags.append(flag)
                    details.append(
                        CitationAuditDetail(
                            citation_text=raw_cit,
                            source_file=src_file,
                            page_number=page_num,
                            associated_sentence=sent,
                            status=status,
                            reason=reason,
                            extracted_numbers=sorted(sent_numbers),
                        )
                    )
                    continue

                # 3. Fabricated page number check
                if page_num is not None:
                    pages_present = {c.page for c in matching_chunks if c.page is not None}
                    if pages_present and page_num not in pages_present:
                        status = CitationSupportStatus.FABRICATED_PAGE
                        reason = f"Source '{src_file}' was retrieved, but cited page {page_num} is absent from retrieved pages {sorted(pages_present)}."
                        ungrounded.append(f"{src_file}:p{page_num}")
                        flag = f"CITATION_VERIFICATION_FAILURE: Fabricated page {page_num} for '{src_file}'"
                        audit_flags.append(flag)
                        details.append(
                            CitationAuditDetail(
                                citation_text=raw_cit,
                                source_file=src_file,
                                page_number=page_num,
                                associated_sentence=sent,
                                status=status,
                                reason=reason,
                                extracted_numbers=sorted(sent_numbers),
                                ground_truth_numbers=sorted(set().union(*(c.numbers for c in matching_chunks))),
                            )
                        )
                        continue

                # 4. Numerical claim grounding check
                target_chunks = [c for c in matching_chunks if (page_num is None or c.page == page_num or c.page is None)]
                gt_numbers: set[str] = set().union(*(c.numbers for c in target_chunks)) if target_chunks else set()

                unsupported_nums = sent_numbers.difference(gt_numbers)
                if unsupported_nums:
                    status = CitationSupportStatus.UNSUPPORTED_NUMERIC
                    reason = f"Sentence asserts numerical values {sorted(unsupported_nums)} that do not exist in retrieved chunk content."
                    ungrounded.append(f"{src_file}(unsupported_numbers={sorted(unsupported_nums)})")
                    flag = f"CITATION_VERIFICATION_FAILURE: Unsupported numbers {sorted(unsupported_nums)} for '{src_file}'"
                    audit_flags.append(flag)
                    details.append(
                        CitationAuditDetail(
                            citation_text=raw_cit,
                            source_file=src_file,
                            page_number=page_num,
                            associated_sentence=sent,
                            status=status,
                            reason=reason,
                            extracted_numbers=sorted(sent_numbers),
                            ground_truth_numbers=sorted(gt_numbers),
                        )
                    )
                    continue

                # 5. Fully grounded citation
                status = CitationSupportStatus.SUPPORTED
                reason = "Citation source, page provenance, and numerical facts verified against retrieved chunk."
                verified.append(src_file)
                details.append(
                    CitationAuditDetail(
                        citation_text=raw_cit,
                        source_file=src_file,
                        page_number=page_num,
                        associated_sentence=sent,
                        status=status,
                        reason=reason,
                        extracted_numbers=sorted(sent_numbers),
                        ground_truth_numbers=sorted(gt_numbers),
                    )
                )

        is_valid = len(ungrounded) == 0

        # Construct sanitized response with audit notices if any violations occurred
        sanitized_response = response_text
        if not is_valid:
            violations_summary = [f"- {d.citation_text}: {d.reason}" for d in details if d.status != CitationSupportStatus.SUPPORTED]
            warning_banner = (
                "\n\n> [!CAUTION]\n"
                "> **Ungrounded Citation & Evidence Warning**:\n"
                "> The following claims or sources could not be verified against retrieved knowledge base chunks:\n"
                + "\n".join(violations_summary)
                + "\n> *Deterministic claim validation failed. Manual engineering inspection required before industrial operation.*"
            )
            sanitized_response += warning_banner

        if conflicts:
            conflict_banner = (
                "\n\n> [!WARNING]\n"
                "> **Conflicting Industrial Evidence Detected**:\n"
                + "\n".join([f"> - {c}" for c in conflicts])
            )
            sanitized_response += conflict_banner

        primary_audit_flag = audit_flags[0] if audit_flags else None

        return CitationValidationResult(
            is_valid=is_valid,
            verified_citations=sorted(set(verified)),
            ungrounded_citations=sorted(set(ungrounded)),
            retrieved_sources=sorted(ground_truth_sources),
            details=details,
            conflicting_sources=conflicts,
            sanitized_response=sanitized_response,
            audit_flag=primary_audit_flag,
            audit_flags=audit_flags,
        )
