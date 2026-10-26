"""
tests/test_eval/test_runner_and_cli.py
======================================
Tests for the Quantitative Evaluation Runner:
  - CLI execution in deterministic mode
  - Report JSON and Markdown schema integrity
  - Suite subset execution
  - Missing dataset handling
  - Hardware / environment probing reliability
"""

import json
from pathlib import Path
from typing import Any

import pytest
import scripts.run_quantitative_eval as quantitative_runner
from app.knowledge.ocr.base import OCRResult
from PIL import Image
from scripts.run_quantitative_eval import (
    DEFAULT_DATASET,
    DEFAULT_GROUND_TRUTH,
    generate_markdown_summary,
    probe_environment,
    run_evaluation,
)


@pytest.fixture
def tmp_eval_paths(tmp_path: Path) -> tuple[Path, Path]:
    out_json = tmp_path / "test_report.json"
    out_md = tmp_path / "test_report.md"
    return out_json, out_md


class TestRunnerAndCLI:
    def test_live_ocr_unavailable_is_not_scored_as_transcription_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class UnavailablePipeline:
            def process_image(self, _image: Any) -> OCRResult:
                return OCRResult(text="", confidence=0.0, engine="ocr_unavailable")

            def extract_text(self, _image: Any) -> str:
                return ""

        class ScannedPDFParser:
            def __init__(self, ocr_fallback_fn: Any) -> None:
                self.ocr_fallback_fn = ocr_fallback_fn

            def extract_sections(self, _path: Path) -> list[Any]:
                self.ocr_fallback_fn(Image.new("RGB", (2, 2)))
                return []

        monkeypatch.setattr(quantitative_runner, "OCRPipeline", UnavailablePipeline)
        monkeypatch.setattr(quantitative_runner, "PDFParser", ScannedPDFParser)
        dataset = json.loads(DEFAULT_DATASET.read_text(encoding="utf-8"))
        ground_truth = json.loads(DEFAULT_GROUND_TRUTH.read_text(encoding="utf-8"))

        result = quantitative_runner.evaluate_ocr_suite(
            dataset["test_suites"]["ocr_suite"],
            ground_truth["ocr_ground_truth"],
            mode="live",
        )

        assert result["status"] == "unavailable"
        assert result["attempted_cases"] == 4
        assert result["unavailable_cases"] == 4
        assert result["cases_evaluated"] == 0
        assert result["aggregate_cer"]["total_evaluations"] == 0
        assert {case["engine_used"] for case in result["cases"]} == {"ocr_unavailable"}
        assert all(case["cer"] is None and case["wer"] is None for case in result["cases"])
        summary = generate_markdown_summary({"environment": {}, "results": {"ocr_suite": result}})
        assert "unavailable outputs are excluded" in summary
        assert "`N/A`" in summary

    def test_probe_environment_deterministic(self) -> None:
        env = probe_environment("deterministic")
        assert env["mode"] == "deterministic"
        assert env["is_live_inference"] is False
        assert "python_version" in env
        assert "timestamp" in env
        assert "hardware_profiling" in env

    def test_run_evaluation_deterministic_full(self, tmp_eval_paths: tuple[Path, Path]) -> None:
        out_json, out_md = tmp_eval_paths
        report = run_evaluation(
            dataset_path=DEFAULT_DATASET,
            ground_truth_path=DEFAULT_GROUND_TRUTH,
            output_json=out_json,
            output_md=out_md,
            mode="deterministic",
        )

        assert out_json.exists()
        assert out_md.exists()
        assert report["version"] == "1.0.0"

        results = report["results"]
        assert "ocr_suite" in results
        assert "routing_suite" in results
        assert "retrieval_suite" in results
        assert "grounding_suite" in results
        assert "tool_suite" in results

        # Verify OCR aggregate metrics
        ocr = results["ocr_suite"]
        assert ocr["status"] == "completed"
        assert ocr["cases_evaluated"] == 4
        assert ocr["aggregate_cer"]["valid_evaluations"] == 4
        assert "micro_cer" in ocr["aggregate_cer"]
        assert "macro_cer" in ocr["aggregate_cer"]
        assert "convention" in ocr["aggregate_cer"]

        # Verify routing confusion matrix and accuracy
        routing = results["routing_suite"]
        assert routing["status"] == "completed"
        assert "confusion_matrix" in routing
        assert routing["overall_accuracy"] == 1.0
        assert routing["cases_evaluated"] == 7

        # Verify retrieval metrics
        retrieval = results["retrieval_suite"]
        assert retrieval["status"] == "completed"
        assert "mean_recall_at_3" in retrieval
        assert "mean_mrr" in retrieval

        # Verify grounding metrics
        grounding = results["grounding_suite"]
        assert grounding["status"] == "completed"
        gr = grounding["grounding_report"]
        assert "hallucination_detection_rate" in gr
        assert "false_acceptance_rate" in gr

        # Verify tools metrics
        tools = results["tool_suite"]
        assert tools["status"] == "completed"
        assert tools["numerical_accuracy"] == 1.0

    def test_run_evaluation_subset_suites(self, tmp_eval_paths: tuple[Path, Path]) -> None:
        out_json, out_md = tmp_eval_paths
        report = run_evaluation(
            dataset_path=DEFAULT_DATASET,
            ground_truth_path=DEFAULT_GROUND_TRUTH,
            output_json=out_json,
            output_md=out_md,
            mode="deterministic",
            suites=["tools", "routing"],
        )

        results = report["results"]
        assert "tool_suite" in results
        assert "routing_suite" in results
        assert "ocr_suite" not in results
        assert "retrieval_suite" not in results
        assert "grounding_suite" not in results

    def test_missing_dataset_file_raises(self, tmp_eval_paths: tuple[Path, Path]) -> None:
        out_json, out_md = tmp_eval_paths
        with pytest.raises(FileNotFoundError, match="Evaluation dataset missing"):
            run_evaluation(
                dataset_path=Path("nonexistent_dataset.json"),
                ground_truth_path=DEFAULT_GROUND_TRUTH,
                output_json=out_json,
                output_md=out_md,
            )

    def test_markdown_summary_structure(self) -> None:
        mock_report: dict[str, Any] = {
            "version": "1.0.0",
            "environment": {
                "timestamp": "2026-10-22T00:00:00Z",
                "mode": "deterministic",
                "is_live_inference": False,
                "python_version": "3.11.15",
                "platform": "win32",
                "ollama_reachable": False,
            },
            "results": {
                "tool_suite": {
                    "status": "completed",
                    "tasks_evaluated": 3,
                    "numerical_accuracy": 1.0,
                }
            },
        }

        md = generate_markdown_summary(mock_report)
        assert "# Quantitative Evaluation Report" in md
        assert "Executive Summary" in md
        assert "Deterministic Tools" in md
        assert "1.0000" in md
