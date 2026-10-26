"""
tests/test_eval/test_dataset_integrity.py
=========================================
Dataset schema and fixture-integrity test suite for the Sovereign AI Workbench
Quantitative Evaluation Dataset.

Verifies:
  1. JSON schema and structural validity of evaluation dataset and ground truth files.
  2. Physical presence and readability of all synthetic fixtures (PNG, PDF, TXT).
  3. Ground-truth key alignment between test suite specifications and ground-truth answers.
  4. Genuine textual alignment: verification that expected retrieval phrases exist verbatim
     in referenced corpus fixtures, and that absent targets are truly absent.
  5. Privacy invariance: zero references to personal directories, usernames, or host paths.
"""

import json
from pathlib import Path
from typing import Any, cast

import pypdfium2
import pytest
from PIL import Image

DATASET_FILE = Path("eval/dataset/quantitative_eval_dataset.json")
GROUND_TRUTH_FILE = Path("eval/dataset/quantitative_ground_truth.json")


@pytest.fixture(scope="module")
def eval_dataset() -> dict[str, Any]:
    assert DATASET_FILE.exists(), f"Missing dataset file: {DATASET_FILE}"
    with open(DATASET_FILE, encoding="utf-8") as f:
        return cast(dict[str, Any], json.load(f))


@pytest.fixture(scope="module")
def ground_truth() -> dict[str, Any]:
    assert GROUND_TRUTH_FILE.exists(), f"Missing ground truth file: {GROUND_TRUTH_FILE}"
    with open(GROUND_TRUTH_FILE, encoding="utf-8") as f:
        return cast(dict[str, Any], json.load(f))


class TestDatasetSchemaAndFixtureIntegrity:
    def test_dataset_json_schemas(self, eval_dataset: dict[str, Any], ground_truth: dict[str, Any]) -> None:
        """Validate structural fields in dataset and ground truth specifications."""
        assert eval_dataset["version"] == "1.0.0"
        assert "test_suites" in eval_dataset
        assert set(eval_dataset["test_suites"].keys()) == {
            "ocr_suite",
            "routing_suite",
            "retrieval_suite",
            "grounding_suite",
            "tool_suite",
        }

        assert ground_truth["version"] == "1.0.0"
        assert "ocr_ground_truth" in ground_truth
        assert "routing_ground_truth" in ground_truth
        assert "retrieval_ground_truth" in ground_truth
        assert "grounding_ground_truth" in ground_truth
        assert "tool_ground_truth" in ground_truth

    def test_all_ocr_fixtures_exist_and_readable(self, ground_truth: dict[str, Any]) -> None:
        """Verify each OCR fixture exists and can be physically loaded."""
        ocr_gt = ground_truth["ocr_ground_truth"]
        assert len(ocr_gt) == 4

        for _key, entry in ocr_gt.items():
            fixture_path = Path(entry["fixture_path"])
            assert fixture_path.exists(), f"OCR fixture not found: {fixture_path}"

            if fixture_path.suffix.lower() == ".png":
                with Image.open(fixture_path) as img:
                    assert img.width > 100
                    assert img.height > 50
                    assert img.mode in ("RGB", "RGBA", "L")
            elif fixture_path.suffix.lower() == ".pdf":
                pdf = pypdfium2.PdfDocument(str(fixture_path))
                assert len(pdf) == entry.get("page_count", 2)
                pdf.close()

    def test_all_corpus_fixtures_exist_and_readable(self, eval_dataset: dict[str, Any]) -> None:
        """Verify all text corpus documents exist and have substantive technical content."""
        corpus_fixtures = eval_dataset["test_suites"]["retrieval_suite"]["corpus_fixtures"]
        assert len(corpus_fixtures) >= 3

        for fpath_str in corpus_fixtures:
            fpath = Path(fpath_str)
            assert fpath.exists(), f"Corpus fixture missing: {fpath}"
            content = fpath.read_text(encoding="utf-8")
            assert len(content.strip()) > 100, f"Corpus fixture {fpath} is suspiciously short"

    def test_ground_truth_alignment_with_dataset(self, eval_dataset: dict[str, Any], ground_truth: dict[str, Any]) -> None:
        """Ensure every ground_truth_id in dataset specification resolves in ground truth."""
        # 1. OCR fixtures
        ocr_fixtures = eval_dataset["test_suites"]["ocr_suite"]["fixtures"]
        for item in ocr_fixtures:
            gt_key = item["ground_truth_key"]
            assert gt_key in ground_truth["ocr_ground_truth"]

        # 2. Routing cases
        route_cases = eval_dataset["test_suites"]["routing_suite"]["test_cases"]
        route_gt_ids = {r["id"] for r in ground_truth["routing_ground_truth"]}
        for rc in route_cases:
            assert rc["ground_truth_id"] in route_gt_ids

        # 3. Retrieval queries
        ret_queries = eval_dataset["test_suites"]["retrieval_suite"]["queries"]
        ret_gt_ids = {r["id"] for r in ground_truth["retrieval_ground_truth"]}
        for rq in ret_queries:
            assert rq["ground_truth_id"] in ret_gt_ids

        # 4. Grounding claims
        grounding_cases = eval_dataset["test_suites"]["grounding_suite"]["test_cases"]
        grounding_gt_ids = {g["id"] for g in ground_truth["grounding_ground_truth"]}
        for gc in grounding_cases:
            assert gc["ground_truth_id"] in grounding_gt_ids

        # 5. Tool tasks
        tool_tasks = eval_dataset["test_suites"]["tool_suite"]["math_tasks"]
        tool_gt_ids = {t["id"] for t in ground_truth["tool_ground_truth"]}
        for tt in tool_tasks:
            assert tt["ground_truth_id"] in tool_gt_ids

    def test_retrieval_ground_truth_verbatim_alignment(self, ground_truth: dict[str, Any]) -> None:
        """
        Verify that for every answerable retrieval target, the expected relevant phrases
        literally appear in the referenced corpus fixture file.
        """
        for item in ground_truth["retrieval_ground_truth"]:
            if item["is_answerable"]:
                fixture_path = Path(item["relevant_fixture"])
                assert fixture_path.exists(), f"Missing target fixture: {fixture_path}"
                corpus_text = fixture_path.read_text(encoding="utf-8")

                for phrase in item["relevant_phrases"]:
                    assert phrase in corpus_text, (
                        f"Target phrase '{phrase}' not found in corpus file {fixture_path}"
                    )
            else:
                # For unanswerable queries, verify relevant_fixture is null and phrases empty
                assert item["relevant_fixture"] is None
                assert len(item["relevant_phrases"]) == 0

    def test_grounding_claims_variety(self, ground_truth: dict[str, Any]) -> None:
        """Verify presence of supported, conflicting, fabricated, and absent claims."""
        claims = ground_truth["grounding_ground_truth"]
        supported = [c for c in claims if c["is_supported"]]
        unsupported = [c for c in claims if not c["is_supported"]]

        assert len(supported) >= 3, "Insufficient supported ground-truth claims"
        assert len(unsupported) >= 4, "Insufficient unsupported ground-truth claims"

        claim_types = {c["claim_type"] for c in claims}
        assert "factual_supported" in claim_types
        assert "conflicting_numerical" in claim_types
        assert "fabricated_unsupported" in claim_types
        assert "absent_component" in claim_types

    def test_zero_personal_paths_or_secrets_in_eval_artifacts(self) -> None:
        """Strict privacy check: verify zero personal folders or usernames exist in eval files."""
        forbidden_substrings = [
            "c:\\users\\suraj",
            "c:/users/suraj",
            "users/suraj",
            "users\\suraj",
            "d:\\",
            "d:/",
            "resume",
            "curriculum_vitae",
        ]

        files_to_check = [
            DATASET_FILE,
            GROUND_TRUTH_FILE,
            Path("eval/fixtures/corpus/turbine_operating_manual.txt"),
            Path("eval/fixtures/corpus/pump_maintenance_spec.txt"),
            Path("eval/fixtures/corpus/unrelated_facility_memo.txt"),
            Path("scripts/generate_synthetic_eval_fixtures.py"),
        ]

        for fpath in files_to_check:
            text = fpath.read_text(encoding="utf-8").lower()
            for forbidden in forbidden_substrings:
                assert forbidden not in text, f"Forbidden privacy token '{forbidden}' detected in {fpath}"
