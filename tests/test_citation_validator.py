"""
tests/test_citation_validator.py
================================
Unit tests for CitationValidator verifying:
1. Genuine citation to a retrieved source.
2. Fabricated filename.
3. Fabricated page number.
4. Real citation that asserts unsupported numerical claims.
5. Empty retrieval result.
6. Conflicting source passages.
7. Answer containing both supported and unsupported claims.
8. Distinguishing citation existence from factual numerical grounding.
"""

from app.agent.citation_validator import CitationSupportStatus, CitationValidator


def test_valid_grounded_citation():
    validator = CitationValidator()
    response = (
        "According to the documentation [Source: turbine_specs.docx, Page 12], "
        "the maximum operating pressure is 450 PSI."
    )
    tool_results = [
        {
            "tool": "rag_search",
            "data": {
                "results": [
                    {
                        "source": "turbine_specs.docx",
                        "page": 12,
                        "content": "Operating envelope: maximum operating pressure is 450 PSI under full load.",
                    }
                ]
            },
        }
    ]

    result = validator.validate(response, tool_results)
    assert result.is_valid is True
    assert "turbine_specs.docx" in result.verified_citations
    assert len(result.ungrounded_citations) == 0
    assert result.audit_flag is None
    assert len(result.details) == 1
    assert result.details[0].status == CitationSupportStatus.SUPPORTED


def test_fabricated_source_filename():
    validator = CitationValidator()
    response = (
        "The system has a safety margin of 20% [Source: ungrounded_secret_report.pdf, Page 4]."
    )
    tool_results = [
        {
            "tool": "rag_search",
            "data": {
                "results": [
                    {
                        "source": "turbine_specs.docx",
                        "page": 1,
                        "content": "General turbine specifications.",
                    }
                ]
            },
        }
    ]

    result = validator.validate(response, tool_results)
    assert result.is_valid is False
    assert any("ungrounded_secret_report.pdf" in c for c in result.ungrounded_citations)
    assert "[!CAUTION]" in result.sanitized_response
    assert "Ungrounded Citation" in result.sanitized_response
    assert result.audit_flag is not None
    assert result.details[0].status == CitationSupportStatus.FABRICATED_SOURCE


def test_fabricated_page_number():
    validator = CitationValidator()
    # File exists in retrieved chunks, but page 45 is fabricated (retrieved chunk is only page 2)
    response = (
        "Turbine vibration limits are specified at 4.5 mm/s [Source: turbine_specs.docx, Page 45]."
    )
    tool_results = [
        {
            "tool": "rag_search",
            "data": {
                "results": [
                    {
                        "source": "turbine_specs.docx",
                        "page": 2,
                        "content": "Vibration limit is 4.5 mm/s RMS under continuous load.",
                    }
                ]
            },
        }
    ]

    result = validator.validate(response, tool_results)
    assert result.is_valid is False
    assert any("p45" in c for c in result.ungrounded_citations)
    assert result.details[0].status == CitationSupportStatus.FABRICATED_PAGE
    assert "page 45 is absent" in result.details[0].reason


def test_real_citation_unsupported_numerical_claim():
    validator = CitationValidator()
    # Source and page match, but claim asserts 950 PSI when source says 150 PSI
    response = (
        "The boiler safety valve trips at 950 PSI [Source: boiler_specs.docx, Page 1]."
    )
    tool_results = [
        {
            "tool": "rag_search",
            "data": {
                "results": [
                    {
                        "source": "boiler_specs.docx",
                        "page": 1,
                        "content": "Boiler safety valve rating: maximum trip pressure is 150 PSI.",
                    }
                ]
            },
        }
    ]

    result = validator.validate(response, tool_results)
    assert result.is_valid is False
    assert result.details[0].status == CitationSupportStatus.UNSUPPORTED_NUMERIC
    assert "950" in result.details[0].reason
    assert "[!CAUTION]" in result.sanitized_response


def test_empty_retrieval_with_citations():
    validator = CitationValidator()
    response = (
        "The standard test speed is 3000 RPM [Source: test_spec.docx, Page 1]."
    )
    tool_results = [
        {
            "tool": "rag_search",
            "data": {"results": []},
            "output": "No matching knowledge base documents found.",
        }
    ]

    result = validator.validate(response, tool_results)
    assert result.is_valid is False
    assert result.details[0].status == CitationSupportStatus.EMPTY_RETRIEVAL
    assert "No documents were retrieved" in result.details[0].reason


def test_conflicting_source_passages():
    validator = CitationValidator()
    response = (
        "Operating pressure is 150 PSI [Source: pump_manual.pdf, Page 1]."
    )
    # Retrieved 2 chunks from same document with conflicting numbers
    tool_results = [
        {
            "tool": "rag_search",
            "data": {
                "results": [
                    {
                        "source": "pump_manual.pdf",
                        "page": 1,
                        "content": "Continuous pressure: 150 PSI.",
                    },
                    {
                        "source": "pump_manual.pdf",
                        "page": 4,
                        "content": "Peak design pressure: 220 PSI with 300 GPM.",
                    },
                ]
            },
        }
    ]

    result = validator.validate(response, tool_results)
    # The citation to page 1 itself is supported
    assert result.is_valid is True
    assert len(result.conflicting_sources) > 0
    assert "Conflicting Industrial Evidence Detected" in result.sanitized_response


def test_mixed_grounded_and_ungrounded_citations():
    validator = CitationValidator()
    response = (
        "Primary pump operates at 60 Hz [Source: pump_manual.pdf, Page 1]. "
        "Auxiliary pump was replaced in 2025 [Source: maintenance_log.xlsx, Page 1]."
    )
    tool_results = [
        {
            "tool": "rag_search",
            "data": {
                "results": [
                    {
                        "source": "pump_manual.pdf",
                        "page": 1,
                        "content": "Pump operates at 60 Hz continuous frequency.",
                    }
                ]
            },
        }
    ]

    result = validator.validate(response, tool_results)
    assert result.is_valid is False
    assert "pump_manual.pdf" in result.verified_citations
    assert any("maintenance_log.xlsx" in c for c in result.ungrounded_citations)
    assert result.details[0].status == CitationSupportStatus.SUPPORTED
    assert result.details[1].status == CitationSupportStatus.FABRICATED_SOURCE


def test_pipe_separated_citation_and_chunk_provenance():
    validator = CitationValidator()
    response = (
        "The turbine operating pressure is 450 PSI [Source 1: turbine_specs.docx | Page 2 | SPECS]."
    )
    tool_results = [
        {
            "tool": "rag_search",
            "data": {
                "results": [
                    {
                        "source": "turbine_specs.docx",
                        "page": 2,
                        "content": "Turbine envelope: nominal operating pressure is 450 PSI at 3000 RPM.",
                        "chunk_id": "chunk-101",
                        "document_id": "doc-901",
                        "section": "SPECS",
                        "similarity": 0.94,
                        "dense_similarity": 0.93,
                        "dense_rank": 1,
                        "sparse_score": 18.2,
                        "sparse_rank": 1,
                        "rrf_score": 0.033,
                    }
                ]
            },
        }
    ]

    result = validator.validate(response, tool_results)
    assert result.is_valid is True
    assert "turbine_specs.docx" in result.verified_citations
    assert len(result.details) == 1

    detail = result.details[0]
    assert detail.source_file == "turbine_specs.docx"
    assert detail.page_number == 2
    assert detail.status == CitationSupportStatus.SUPPORTED
    assert detail.chunk_id == "chunk-101"
    assert detail.document_id == "doc-901"
    assert detail.section == "SPECS"
    assert detail.similarity == 0.94
    assert detail.dense_similarity == 0.93
    assert detail.dense_rank == 1
    assert detail.sparse_score == 18.2
    assert detail.rrf_score == 0.033
    assert "450" in detail.ground_truth_numbers
    assert "450" in detail.extracted_numbers

