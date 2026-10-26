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
    FABRICATED_QUOTE = "FABRICATED_QUOTE"
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
    chunk_id: str | None = None
    document_id: str | None = None
    section: str | None = None
    chunk_content: str | None = None
    similarity: float = 0.0
    dense_similarity: float = 0.0
    dense_rank: int = 1
    sparse_score: float = 0.0
    sparse_rank: int = 1
    rrf_score: float = 0.0


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
    chunk_id: str | None = None
    document_id: str | None = None
    section: str | None = None
    similarity: float = 0.0
    dense_similarity: float = 0.0
    dense_rank: int = 1
    sparse_score: float = 0.0
    sparse_rank: int = 1
    rrf_score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class CitationValidator:
    """
    Validates model citations and claim support against retrieved RAG evidence chunks.
    Ensures filename existence, page number authenticity, and numerical claim alignment.
    """

    CITATION_PATTERN = re.compile(
        r"\[(?:Source(?:\s+\d+)?:?\s*)?([a-zA-Z0-9_\-\.]+\.(?:pdf|docx|xlsx|csv|txt|png|jpg|jpeg|webp|tiff|bmp))(?:\s*[,|]\s*(?:Page|p\.?):?\s*(\d+))?(?:[^\]]*)?\]",
        re.IGNORECASE,
    )
    REFERENCE_ID_PATTERN = re.compile(
        r"\[(?:Source|Document|Chunk)\s+ID\s*:\s*([^\]]+)\]",
        re.IGNORECASE,
    )
    QUOTED_TEXT_PATTERN = re.compile(r'[\"“]([^\"”]+)[\"”]')
    CLAIM_TOKEN_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z0-9_-]{2,}")
    CLAIM_STOP_WORDS = {
        "about", "according", "after", "also", "and", "are", "based", "because",
        "before", "being", "between", "both", "can", "could", "does", "document",
        "documents", "each", "from", "has", "have", "into", "its", "manual", "more",
        "not", "only", "other", "our", "over", "page", "reference", "report", "shall",
        "should", "source", "specifies", "states", "that", "the", "their", "there", "these",
        "they", "this", "those", "through", "under", "using", "was", "were", "what", "when",
        "where", "which", "while", "with", "would",
    }

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
        """Extract only structured chunks returned by this request's RAG operation."""
        chunks: list[EvidenceChunk] = []

        for res in tool_results:
            tool_name = res.get("tool_name") or res.get("tool")
            if tool_name != "rag_search":
                continue
            data = res.get("data")
            if isinstance(data, dict):
                results = data.get("results")
                if isinstance(results, list):
                    for item in results:
                        if isinstance(item, dict):
                            src_raw = str(item.get("source") or item.get("filename") or "").strip()
                            src = src_raw.replace("\\", "/").rsplit("/", 1)[-1].casefold()
                            page = item.get("page")
                            page_int = int(page) if page is not None and str(page).isdigit() else None
                            content = str(item.get("content") or "")
                            chunk_id = str(item.get("chunk_id")) if item.get("chunk_id") else None
                            doc_id = str(item.get("document_id")) if item.get("document_id") else None
                            section = str(item.get("section") or "") if item.get("section") else None
                            sim = float(item.get("similarity") or 0.0)
                            dense_sim = float(item.get("dense_similarity") or 0.0)
                            dense_rank = int(item.get("dense_rank") or 1)
                            sparse_score = float(item.get("sparse_score") or 0.0)
                            sparse_rank = int(item.get("sparse_rank") or 1)
                            rrf_score = float(item.get("rrf_score") or 0.0)
                            raw_meta = item.get("metadata")
                            meta: dict[str, Any] = dict(raw_meta) if isinstance(raw_meta, dict) else {}
                            if src and content:
                                chunks.append(
                                    EvidenceChunk(
                                        source=src,
                                        page=page_int,
                                        content=content,
                                        numbers=self.extract_numbers(content),
                                        chunk_id=chunk_id,
                                        document_id=doc_id,
                                        section=section,
                                        similarity=sim,
                                        dense_similarity=dense_sim,
                                        dense_rank=dense_rank,
                                        sparse_score=sparse_score,
                                        sparse_rank=sparse_rank,
                                        rrf_score=rrf_score,
                                        metadata=meta,
                                    )
                                )

        return chunks

    @classmethod
    def _claim_tokens(cls, text: str) -> set[str]:
        """Return informative lexical tokens for conservative claim/evidence linkage."""
        return {
            token.casefold()
            for token in cls.CLAIM_TOKEN_PATTERN.findall(text)
            if token.casefold() not in cls.CLAIM_STOP_WORDS
        }

    @classmethod
    def _claim_has_lexical_support(cls, claim: str, evidence: str) -> bool:
        """Reject citations with no meaningful subject overlap in retrieved text.

        This is a deterministic relevance screen, not a semantic entailment proof.
        """
        claim_tokens = cls._claim_tokens(claim)
        evidence_tokens = cls._claim_tokens(evidence)
        if not claim_tokens:
            return False
        overlap = len(claim_tokens & evidence_tokens)
        return overlap > 0 and overlap / len(claim_tokens) >= 0.5

    @staticmethod
    def _normalized_quote(text: str) -> str:
        return " ".join(text.casefold().split())

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

    def build_retrieved_excerpt(
        self,
        question: str,
        tool_results: list[dict[str, Any]],
        *,
        minimum_overlap: float = 0.5,
        maximum_characters: int = 800,
    ) -> tuple[str, str] | None:
        """Select a verbatim sentence from request-local RAG evidence for safe fallback.

        This is used only when the model's answer fails citation validation. It does
        not paraphrase or synthesize facts: the source sentence must itself overlap
        with the user's informative terms and is validated again before display.
        """
        question_tokens = self._claim_tokens(question)
        if not question_tokens:
            return None

        candidates: list[tuple[float, float, str, str]] = []
        for chunk in self.extract_evidence_chunks(tool_results):
            for raw_sentence in re.split(r"(?<=[.!?])\s+", chunk.content.strip()):
                sentence = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", raw_sentence).strip()
                if not sentence or len(sentence) > maximum_characters:
                    continue
                sentence_tokens = self._claim_tokens(sentence)
                if not sentence_tokens:
                    continue
                overlap = len(question_tokens & sentence_tokens) / len(question_tokens)
                if overlap >= minimum_overlap:
                    candidates.append((overlap, chunk.similarity, sentence, chunk.source))

        if not candidates:
            return None
        _, _, sentence, source = max(candidates, key=lambda item: (item[0], item[1]))
        return sentence, source

    def detect_conflicting_evidence(self, chunks: list[EvidenceChunk]) -> list[str]:
        """Detects whether multiple chunks for the same source and section contain divergent numeric telemetry."""
        conflicts: list[str] = []
        by_source_and_sec: dict[tuple[str, str], list[EvidenceChunk]] = {}
        for c in chunks:
            sec = (c.section or "").strip().lower()
            by_source_and_sec.setdefault((c.source, sec), []).append(c)

        for (src, sec), src_chunks in by_source_and_sec.items():
            if len(src_chunks) > 1:
                all_nums = [c.numbers for c in src_chunks if c.numbers]
                if len(all_nums) >= 2 and all_nums[0] != all_nums[1]:
                    diff = all_nums[0].symmetric_difference(all_nums[1])
                    if diff:
                        sec_label = f" (section '{sec}')" if sec else ""
                        conflicts.append(
                            f"Source '{src}'{sec_label} contains divergent numerical specifications: {sorted(diff)}"
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
            id_matches = list(self.REFERENCE_ID_PATTERN.finditer(sent))
            total_citations_found += len(id_matches)
            for id_match in id_matches:
                identifier = id_match.group(1).strip()
                ungrounded.append(f"identifier:{identifier}")
                audit_flags.append("CITATION_VERIFICATION_FAILURE: model-supplied source identifiers are not provenance")
                details.append(
                    CitationAuditDetail(
                        citation_text=id_match.group(0),
                        source_file=f"identifier:{identifier}",
                        page_number=None,
                        associated_sentence=sent,
                        status=CitationSupportStatus.FABRICATED_SOURCE,
                        reason="Document and chunk identifiers must come from retrieval metadata, not model-written text.",
                    )
                )
            for match in matches:
                total_citations_found += 1
                raw_cit = match.group(0).strip()
                src_file = match.group(1).strip().strip("'\"` ").replace("\\", "/").rsplit("/", 1)[-1].casefold()
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
                matching_chunks = [c for c in chunks if c.source.casefold() == src_file]
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
                best_chunk = None
                if matching_chunks:
                    if page_num is not None:
                        for c in matching_chunks:
                            if c.page == page_num:
                                best_chunk = c
                                break
                    if best_chunk is None:
                        best_chunk = matching_chunks[0]

                if page_num is not None:
                    pages_present = {c.page for c in matching_chunks if c.page is not None}
                    if page_num not in pages_present:
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
                                chunk_id=best_chunk.chunk_id if best_chunk else None,
                                document_id=best_chunk.document_id if best_chunk else None,
                                section=best_chunk.section if best_chunk else None,
                                chunk_content=best_chunk.content if best_chunk else None,
                                similarity=best_chunk.similarity if best_chunk else 0.0,
                                dense_similarity=best_chunk.dense_similarity if best_chunk else 0.0,
                                dense_rank=best_chunk.dense_rank if best_chunk else 1,
                                sparse_score=best_chunk.sparse_score if best_chunk else 0.0,
                                sparse_rank=best_chunk.sparse_rank if best_chunk else 1,
                                rrf_score=best_chunk.rrf_score if best_chunk else 0.0,
                            )
                        )
                        continue

                # 4. Numerical claim grounding check
                target_chunks = [c for c in matching_chunks if (page_num is None or c.page == page_num or c.page is None)]
                target_best_chunk = target_chunks[0] if target_chunks else best_chunk
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
                            chunk_id=target_best_chunk.chunk_id if target_best_chunk else None,
                            document_id=target_best_chunk.document_id if target_best_chunk else None,
                            section=target_best_chunk.section if target_best_chunk else None,
                            chunk_content=target_best_chunk.content if target_best_chunk else None,
                            similarity=target_best_chunk.similarity if target_best_chunk else 0.0,
                            dense_similarity=target_best_chunk.dense_similarity if target_best_chunk else 0.0,
                            dense_rank=target_best_chunk.dense_rank if target_best_chunk else 1,
                            sparse_score=target_best_chunk.sparse_score if target_best_chunk else 0.0,
                            sparse_rank=target_best_chunk.sparse_rank if target_best_chunk else 1,
                            rrf_score=target_best_chunk.rrf_score if target_best_chunk else 0.0,
                        )
                    )
                    continue

                evidence_text = "\n".join(chunk.content for chunk in target_chunks)
                quoted_phrases = [
                    self._normalized_quote(value)
                    for value in self.QUOTED_TEXT_PATTERN.findall(claim_text)
                ]
                normalized_evidence = self._normalized_quote(evidence_text)
                if any(not phrase or phrase not in normalized_evidence for phrase in quoted_phrases):
                    status = CitationSupportStatus.FABRICATED_QUOTE
                    reason = "Quoted wording is not present in the cited retrieved chunk text."
                    ungrounded.append(f"{src_file}(unverified_quote)")
                    audit_flags.append(f"CITATION_VERIFICATION_FAILURE: fabricated quotation for '{src_file}'")
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
                            chunk_id=target_best_chunk.chunk_id if target_best_chunk else None,
                            document_id=target_best_chunk.document_id if target_best_chunk else None,
                            section=target_best_chunk.section if target_best_chunk else None,
                            chunk_content=target_best_chunk.content if target_best_chunk else None,
                        )
                    )
                    continue

                claim_tokens = self._claim_tokens(claim_text)
                evidence_tokens = self._claim_tokens(evidence_text)
                overlap = claim_tokens & evidence_tokens
                if not claim_tokens or not overlap or len(overlap) / len(claim_tokens) < 0.5:
                    status = CitationSupportStatus.UNVERIFIABLE_SEMANTIC
                    reason = "The cited chunk has insufficient informative-word overlap with the claim; semantic entailment is not established."
                    ungrounded.append(f"{src_file}(claim_not_lexically_linked)")
                    audit_flags.append(f"CITATION_VERIFICATION_FAILURE: claim not linked to evidence for '{src_file}'")
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
                            chunk_id=target_best_chunk.chunk_id if target_best_chunk else None,
                            document_id=target_best_chunk.document_id if target_best_chunk else None,
                            section=target_best_chunk.section if target_best_chunk else None,
                            chunk_content=target_best_chunk.content if target_best_chunk else None,
                        )
                    )
                    continue

                # 5. Fully grounded citation
                status = CitationSupportStatus.SUPPORTED
                reason = "Exact source/page, quote/numeric checks, and lexical relevance screen passed; this is not semantic entailment proof."
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
                        chunk_id=target_best_chunk.chunk_id if target_best_chunk else None,
                        document_id=target_best_chunk.document_id if target_best_chunk else None,
                        section=target_best_chunk.section if target_best_chunk else None,
                        chunk_content=target_best_chunk.content if target_best_chunk else None,
                        similarity=target_best_chunk.similarity if target_best_chunk else 0.0,
                        dense_similarity=target_best_chunk.dense_similarity if target_best_chunk else 0.0,
                        dense_rank=target_best_chunk.dense_rank if target_best_chunk else 1,
                        sparse_score=target_best_chunk.sparse_score if target_best_chunk else 0.0,
                        sparse_rank=target_best_chunk.sparse_rank if target_best_chunk else 1,
                        rrf_score=target_best_chunk.rrf_score if target_best_chunk else 0.0,
                    )
                )

        has_chunks = bool(chunks)
        rag_was_called = any(
            (result.get("tool_name") or result.get("tool")) == "rag_search"
            for result in tool_results
        )
        response_lower = response_text.casefold()
        is_honest_refusal = any(
            phrase in response_lower
            for phrase in (
                "insufficient evidence",
                "could not find",
                "couldn't find",
                "no matching information",
                "no relevant information",
                "no documents were retrieved",
                "cannot provide a source-grounded answer",
            )
        )

        if has_chunks and rag_was_called and total_citations_found == 0 and not is_honest_refusal:
            audit_flags.append(
                "UNCITED_RAG_RESPONSE: Knowledge base evidence was retrieved, but the response contained no source citations."
            )
        if rag_was_called and not has_chunks:
            audit_flags.append("EMPTY_RETRIEVAL_ABSTENTION: no evidence was retrieved for this request")

        if rag_was_called and has_chunks:
            for sentence in raw_sentences:
                if self.CITATION_PATTERN.search(sentence) or self.REFERENCE_ID_PATTERN.search(sentence):
                    continue
                if any(
                    phrase in sentence.casefold()
                    for phrase in (
                        "insufficient evidence", "could not find", "couldn't find",
                        "no matching information", "no relevant information",
                        "no documents were retrieved",
                    )
                ):
                    continue
                if len(self._claim_tokens(sentence)) >= 3:
                    audit_flags.append("UNCITED_RAG_CLAIM: a substantive answer sentence has no source citation")

        is_valid = not ungrounded and not any(
            flag.startswith(("UNCITED_RAG_RESPONSE", "UNCITED_RAG_CLAIM", "EMPTY_RETRIEVAL_ABSTENTION"))
            for flag in audit_flags
        )

        # Do not return model-written unsupported claims/citations as if they were
        # sources. On failure retain only a refusal or complete sentences whose
        # every displayed citation passed the deterministic checks.
        sanitized_response = response_text
        if not is_valid:
            safe_sentences: list[str] = []
            details_by_sentence: dict[str, list[CitationAuditDetail]] = {}
            for detail in details:
                details_by_sentence.setdefault(detail.associated_sentence, []).append(detail)

            for sentence in raw_sentences:
                sentence_details = details_by_sentence.get(sentence, [])
                has_citation_markup = bool(
                    self.CITATION_PATTERN.search(sentence) or self.REFERENCE_ID_PATTERN.search(sentence)
                )
                if has_citation_markup:
                    if sentence_details and all(d.status == CitationSupportStatus.SUPPORTED for d in sentence_details):
                        safe_sentences.append(sentence)
                elif is_honest_refusal:
                    lowered = sentence.casefold()
                    if any(
                        phrase in lowered
                        for phrase in (
                            "insufficient evidence", "could not find", "couldn't find",
                            "no matching information", "no relevant information",
                            "no documents were retrieved", "cannot provide a source-grounded answer",
                        )
                    ):
                        safe_sentences.append(sentence)

            safe_text = " ".join(dict.fromkeys(safe_sentences)).strip()
            if rag_was_called and not has_chunks:
                safe_text = (
                    "I could not find relevant information in the internal knowledge base, "
                    "so I cannot provide a source-grounded answer."
                )
            if not safe_text:
                safe_text = (
                    "I could not find relevant information in the internal knowledge base, "
                    "so I cannot provide a source-grounded answer."
                )
            sanitized_response = (
                safe_text
                + "\n\n> [!CAUTION]\n"
                + "> **Ungrounded Citation & Evidence Warning**: unsupported claims and unverified references were omitted. "
                + "> Remaining statements passed source, page, quote, numeric, and lexical checks only; this is not semantic entailment proof."
            )

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
