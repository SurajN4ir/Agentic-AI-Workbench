"""
tests/test_citation_validator.py
================================
Unit tests for CitationValidator.
Ensures citations in agent responses are strictly cross-referenced against retrieved evidence.
"""

from app.agent.citation_validator import CitationValidator


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
                        "content": "Max operating pressure is 450 PSI.",
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


def test_fabricated_ungrounded_citation():
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
    assert "ungrounded_secret_report.pdf" in result.ungrounded_citations
    assert "[!CAUTION]" in result.sanitized_response
    assert "Ungrounded Citation Warning" in result.sanitized_response
    assert result.audit_flag is not None
    assert "CITATION_VERIFICATION_FAILURE" in result.audit_flag


def test_no_citation_present():
    validator = CitationValidator()
    response = "The calculated value is 42."
    tool_results = []

    result = validator.validate(response, tool_results)
    assert result.is_valid is True
    assert len(result.verified_citations) == 0
    assert len(result.ungrounded_citations) == 0


def test_mixed_grounded_and_ungrounded_citations():
    validator = CitationValidator()
    response = (
        "Primary pump operates at 60 Hz [Source: pump_manual.pdf]. "
        "Auxiliary pump was replaced in 2025 [Source: maintenance_log.xlsx]."
    )
    tool_results = [
        {
            "tool": "rag_search",
            "data": {
                "results": [
                    {
                        "source": "pump_manual.pdf",
                        "page": 3,
                        "content": "Pump operates at 60 Hz.",
                    }
                ]
            },
        }
    ]

    result = validator.validate(response, tool_results)
    assert result.is_valid is False
    assert "pump_manual.pdf" in result.verified_citations
    assert "maintenance_log.xlsx" in result.ungrounded_citations
    assert "Ungrounded Citation Warning" in result.sanitized_response
