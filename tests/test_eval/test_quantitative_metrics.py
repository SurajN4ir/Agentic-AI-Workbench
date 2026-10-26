"""
tests/test_eval/test_quantitative_metrics.py
============================================
Unit tests for quantitative evaluation metrics:
  - CER & WER (Levenshtein distance, backtrace, edge cases, zero-division, empty references)
  - Multi-class routing confusion matrix & precision/recall/F1 (missing classes, zero division)
  - Information Retrieval metrics (Recall@k, MRR, empty ground truths, multiple chunks)
  - Grounding & citation faithfulness metrics (hallucination detection, false acceptance)
"""

import pytest
from eval.quantitative_metrics import (
    calculate_cer,
    calculate_grounding_metrics,
    calculate_mrr,
    calculate_recall_at_k,
    calculate_wer,
    compute_aggregate_ocr_metrics,
    compute_classification_metrics,
    compute_confusion_matrix,
    compute_mean_mrr,
    compute_mean_recall_at_k,
    levenshtein_operations,
)

# ============================================================================
# 1. CER & WER Tests
# ============================================================================

class TestCERAndWER:
    def test_levenshtein_operations_known_pairs(self) -> None:
        # Exact match
        subs, dels, inss, total = levenshtein_operations("test", "test")
        assert (subs, dels, inss, total) == (0, 0, 0, 0)

        # Single substitution
        subs, dels, inss, total = levenshtein_operations("cat", "bat")
        assert (subs, dels, inss, total) == (1, 0, 0, 1)

        # Single insertion
        subs, dels, inss, total = levenshtein_operations("cat", "cats")
        assert (subs, dels, inss, total) == (0, 0, 1, 1)

        # Single deletion
        subs, dels, inss, total = levenshtein_operations("cats", "cat")
        assert (subs, dels, inss, total) == (0, 1, 0, 1)

        # Classical example: kitten -> sitting (2 subs, 0 dels, 1 ins = 3 edits)
        subs, dels, inss, total = levenshtein_operations("kitten", "sitting")
        assert (subs, dels, inss, total) == (2, 0, 1, 3)

    def test_cer_exact_match(self) -> None:
        res = calculate_cer("Turbine Model 400", "Turbine Model 400")
        assert res.error_rate == 0.0
        assert res.total_edits == 0
        assert res.reference_length == 17

    def test_cer_substitutions_and_insertions(self) -> None:
        # Reference: "12345" (len 5)
        # Hypothesis: "12X45Y" -> 1 sub ('3'->'X'), 1 ins ('Y') -> 2 edits -> 2/5 = 0.4
        res = calculate_cer("12345", "12X45Y")
        assert res.substitutions == 1
        assert res.insertions == 1
        assert res.deletions == 0
        assert res.total_edits == 2
        assert res.error_rate == 0.4

    def test_cer_empty_reference_conventions(self) -> None:
        # Convention: both empty -> 0.0
        res_both_empty = calculate_cer("", "")
        assert res_both_empty.error_rate == 0.0
        assert res_both_empty.total_edits == 0

        # Convention: reference empty, hypothesis non-empty -> 1.0 (pure insertion)
        res_empty_ref = calculate_cer("", "unexpected")
        assert res_empty_ref.error_rate == 1.0
        assert res_empty_ref.insertions == 10

        # strict_empty raises ValueError
        with pytest.raises(ValueError, match="Reference string is empty"):
            calculate_cer("", "unexpected", strict_empty=True)

        # Reference non-empty, hypothesis empty -> 1.0 (100% deletion)
        res_empty_hyp = calculate_cer("abc", "")
        assert res_empty_hyp.error_rate == 1.0
        assert res_empty_hyp.deletions == 3

    def test_cer_case_sensitivity(self) -> None:
        res_case_sensitive = calculate_cer("ABC", "abc", case_sensitive=True)
        assert res_case_sensitive.error_rate == 1.0  # 3 substitutions

        res_case_insensitive = calculate_cer("ABC", "abc", case_sensitive=False)
        assert res_case_insensitive.error_rate == 0.0

    def test_wer_standard_calculation(self) -> None:
        ref = "The quick brown fox jumps over the lazy dog"
        hyp = "The fast brown fox jumps the lazy dog"
        # Words in ref: 9
        # 'quick' -> 'fast' (1 sub)
        # 'over' -> deleted (1 del)
        # Edits = 2 / 9 = 0.222222
        res = calculate_wer(ref, hyp)
        assert res.substitutions == 1
        assert res.deletions == 1
        assert res.insertions == 0
        assert res.total_edits == 2
        assert res.reference_length == 9
        assert pytest.approx(res.error_rate, 0.0001) == 0.222222

    def test_wer_empty_conventions(self) -> None:
        assert calculate_wer("", "").error_rate == 0.0
        assert calculate_wer("", "one two").error_rate == 1.0
        with pytest.raises(ValueError):
            calculate_wer("", "one two", strict_empty=True)
        assert calculate_wer("one two", "").error_rate == 1.0

    def test_aggregate_ocr_segregates_empty_and_undefined(self) -> None:
        r1 = calculate_cer("valid turbine text", "valid turbine text")  # 0.0, valid
        r2 = calculate_cer("valve 100", "valve 101")                   # 1 edit / 9 = 0.1111, valid
        r3 = calculate_cer("", "")                                     # 0.0, empty ref, not undefined
        r4 = calculate_cer("", "phantom text")                         # 1.0, empty ref, undefined

        agg = compute_aggregate_ocr_metrics([r1, r2, r3, r4])
        assert agg["total_evaluations"] == 4
        assert agg["valid_evaluations"] == 2
        assert agg["empty_reference_evaluations"] == 2
        assert agg["undefined_evaluations"] == 1
        # Valid only mean: (0.0 + 0.111111) / 2 = 0.0556
        assert pytest.approx(agg["mean_error_rate_valid_only"], 0.001) == 0.0556
        assert pytest.approx(agg["macro_cer"], 0.001) == 0.0556
        # Global mean includes the empty conventions: (0.0 + 0.111111 + 0.0 + 1.0) / 4 = 0.2778
        assert pytest.approx(agg["global_mean_error_rate"], 0.001) == 0.2778
        # Micro CER = (0 + 1) / (18 + 9) = 1 / 27 = 0.0370
        assert pytest.approx(agg["micro_cer"], 0.001) == 0.0370

    def test_micro_vs_macro_cer_weighting(self) -> None:
        """
        Verify that micro CER (sum(edits)/sum(refs)) and macro CER (mean of ratios)
        accurately reflect NIST standards and do not conflate short vs long sequences.
        """
        # Case 1: Short sequence (10 chars), 1 edit -> ratio = 0.10
        r1 = calculate_cer("0123456789", "012345678X")
        # Case 2: Long sequence (100 chars), 30 edits -> ratio = 0.30
        ref_long = "A" * 100
        hyp_long = "A" * 70 + "B" * 30
        r2 = calculate_cer(ref_long, hyp_long)

        agg = compute_aggregate_ocr_metrics([r1, r2])
        assert agg["valid_evaluations"] == 2
        # Macro CER: (0.10 + 0.30) / 2 = 0.2000
        assert agg["macro_cer"] == 0.2000
        assert agg["macro_cer_percent"] == 20.0
        # Micro CER: (1 + 30) / (10 + 100) = 31 / 110 = 0.2818
        assert agg["micro_cer"] == 0.2818

    def test_ratio_convention_and_unit_bounds(self) -> None:
        """
        Ensure metric conventions adhere to documented fractional ratios (not percentages),
        preventing unit mismatch in reporting.
        """
        r1 = calculate_cer("test", "best")  # 1 / 4 = 0.25
        agg = compute_aggregate_ocr_metrics([r1])
        assert "ratio (0.0=0%, 1.0=100%" in agg["convention"]
        assert 0.0 <= agg["macro_cer"] <= 1.0
        assert agg["macro_cer"] == 0.25
        assert agg["macro_cer_percent"] == 25.0
        # Insertion exceeding reference length yields ratio > 1.0
        r_overflow = calculate_cer("cat", "catastrophe")  # 8 insertions / 3 = 2.6667
        assert r_overflow.error_rate > 1.0
        agg_overflow = compute_aggregate_ocr_metrics([r_overflow])
        assert agg_overflow["macro_cer"] > 1.0



# ============================================================================
# 2. Multi-class Routing & Confusion Matrix Tests
# ============================================================================

class TestRoutingAndClassificationMetrics:
    def test_perfect_routing_confusion_matrix(self) -> None:
        y_true = ["rag", "code", "math", "rag", "code"]
        y_pred = ["rag", "code", "math", "rag", "code"]
        cm = compute_confusion_matrix(y_true, y_pred)

        assert cm["total"] == 5
        assert set(cm["labels"]) == {"code", "math", "rag"}
        assert cm["matrix"]["rag"]["rag"] == 2
        assert cm["matrix"]["code"]["code"] == 2
        assert cm["matrix"]["math"]["math"] == 1
        assert cm["matrix"]["rag"]["code"] == 0

        report = compute_classification_metrics(y_true, y_pred)
        assert report.accuracy == 1.0
        assert report.macro_f1 == 1.0
        assert report.weighted_f1 == 1.0
        for c in ["rag", "code", "math"]:
            assert report.per_class[c].precision == 1.0
            assert report.per_class[c].recall == 1.0
            assert report.per_class[c].f1 == 1.0

    def test_missing_predicted_class_zero_division(self) -> None:
        """Verify that when a class is never predicted, it produces 0.0 without crash."""
        y_true = ["rag", "code", "math"]
        y_pred = ["rag", "code", "code"]  # 'math' is never predicted
        labels = ["rag", "code", "math"]

        report = compute_classification_metrics(y_true, y_pred, labels=labels)
        assert report.per_class["math"].support == 1
        assert report.per_class["math"].true_positives == 0
        assert report.per_class["math"].recall == 0.0
        assert report.per_class["math"].precision == 0.0
        assert report.per_class["math"].f1 == 0.0

        # 'code' has 1 TP, 1 FP (math predicted as code) -> precision = 1/2 = 0.5, recall = 1/1 = 1.0
        assert report.per_class["code"].true_positives == 1
        assert report.per_class["code"].false_positives == 1
        assert report.per_class["code"].precision == 0.5
        assert report.per_class["code"].recall == 1.0

        assert report.total_samples == 3

    def test_unseen_class_in_ground_truth(self) -> None:
        """Verify handling when an explicit label never appears in ground truth."""
        y_true = ["rag", "rag"]
        y_pred = ["rag", "rag"]
        labels = ["rag", "code", "document"]  # 'code' and 'document' are unrepresented

        report = compute_classification_metrics(y_true, y_pred, labels=labels)
        assert report.per_class["code"].support == 0
        assert report.per_class["code"].precision == 0.0
        assert report.per_class["code"].recall == 0.0
        assert report.per_class["code"].f1 == 0.0
        # Accuracy is 1.0 over evaluated samples
        assert report.accuracy == 1.0

    def test_empty_classification_inputs(self) -> None:
        report = compute_classification_metrics([], [], labels=["rag", "code"])
        assert report.total_samples == 0
        assert report.accuracy == 0.0
        assert report.macro_f1 == 0.0

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="Length mismatch"):
            compute_confusion_matrix(["rag"], ["rag", "code"])

    def test_confusion_matrix_unknown_label_handling(self) -> None:
        y_true = ["rag", "code"]
        y_pred = ["rag", "unseen_class"]
        labels = ["rag", "code"]

        # Default allow_unknown=False -> raises ValueError
        with pytest.raises(ValueError, match="Encountered unknown labels not in provided labels"):
            compute_confusion_matrix(y_true, y_pred, labels=labels, allow_unknown=False)

        # allow_unknown=True -> routes to __UNKNOWN__
        cm = compute_confusion_matrix(y_true, y_pred, labels=labels, allow_unknown=True)
        assert "__UNKNOWN__" in cm["labels"]
        assert cm["matrix"]["code"]["__UNKNOWN__"] == 1



# ============================================================================
# 3. Information Retrieval (RAG) Metrics Tests
# ============================================================================

class TestRetrievalMetrics:
    def test_recall_at_k_single_chunk_hit(self) -> None:
        retrieved = ["doc_a#chunk1", "doc_b#chunk2", "doc_c#chunk3"]
        gt = ["doc_b#chunk2"]

        assert calculate_recall_at_k(retrieved, gt, k=1) == 0.0
        assert calculate_recall_at_k(retrieved, gt, k=2) == 1.0
        assert calculate_recall_at_k(retrieved, gt, k=3) == 1.0

    def test_recall_at_k_multiple_relevant_chunks(self) -> None:
        retrieved = ["c1", "noise_1", "c2", "noise_2", "c3"]
        gt = ["c1", "c2", "c3"]  # 3 relevant chunks

        # k=1: retrieved ['c1'] -> 1/3 = 0.3333
        assert calculate_recall_at_k(retrieved, gt, k=1) == 0.3333
        # k=2: retrieved ['c1', 'noise_1'] -> 1/3 = 0.3333
        assert calculate_recall_at_k(retrieved, gt, k=2) == 0.3333
        # k=3: retrieved ['c1', 'noise_1', 'c2'] -> 2/3 = 0.6667
        assert calculate_recall_at_k(retrieved, gt, k=3) == 0.6667
        # k=5: retrieved all 3 -> 3/3 = 1.0
        assert calculate_recall_at_k(retrieved, gt, k=5) == 1.0

    def test_recall_at_k_empty_ground_truth_conventions(self) -> None:
        # Convention: If no relevant chunks exist and none were retrieved -> 1.0
        assert calculate_recall_at_k([], [], k=3) == 1.0
        # If no relevant chunks exist but model returned items -> 0.0
        assert calculate_recall_at_k(["noise"], [], k=3) == 0.0

    def test_recall_at_k_invalid_k_raises(self) -> None:
        with pytest.raises(ValueError, match="k must be >= 1"):
            calculate_recall_at_k(["c1"], ["c1"], k=0)

    def test_mrr_calculations(self) -> None:
        # Hit at rank 1 -> 1.0 / 1 = 1.0
        assert calculate_mrr(["target", "noise"], ["target"]) == 1.0

        # Hit at rank 2 -> 1.0 / 2 = 0.5
        assert calculate_mrr(["noise", "target"], ["target"]) == 0.5

        # Hit at rank 4 -> 1.0 / 4 = 0.25
        assert calculate_mrr(["n1", "n2", "n3", "target"], ["target"]) == 0.25

        # No hit -> 0.0
        assert calculate_mrr(["n1", "n2"], ["target"]) == 0.0

        # Empty ground truth -> 0.0
        assert calculate_mrr(["n1"], []) == 0.0

    def test_mean_recall_and_mrr(self) -> None:
        queries_ret = [
            ["target1", "other"],
            ["other", "target2"],
        ]
        queries_gt = [
            ["target1"],
            ["target2"],
        ]

        # Mean Recall@1: (1.0 + 0.0) / 2 = 0.5
        assert compute_mean_recall_at_k(queries_ret, queries_gt, k=1) == 0.5
        # Mean Recall@2: (1.0 + 1.0) / 2 = 1.0
        assert compute_mean_recall_at_k(queries_ret, queries_gt, k=2) == 1.0
        # Mean MRR: (1.0 + 0.5) / 2 = 0.75
        assert compute_mean_mrr(queries_ret, queries_gt) == 0.75


# ============================================================================
# 4. Grounding & Citation Faithfulness Tests
# ============================================================================

class TestGroundingMetrics:
    def test_grounding_perfect_classification(self) -> None:
        # 2 actual supported, 2 actual unsupported/hallucinations
        gt = [True, True, False, False]
        pred = [True, True, False, False]

        res = calculate_grounding_metrics(gt, pred)
        assert res.accuracy == 1.0
        assert res.precision == 1.0
        assert res.recall == 1.0
        assert res.specificity == 1.0
        assert res.hallucination_detection_rate == 1.0
        assert res.false_acceptance_rate == 0.0
        assert res.true_grounded == 2
        assert res.true_hallucination == 2
        assert res.false_grounded == 0
        assert res.false_rejection == 0

    def test_grounding_pure_hallucination_acceptance(self) -> None:
        """When the system fails to reject any hallucination, false acceptance is 1.0."""
        gt = [False, False]  # Both claims are fabricated
        pred = [True, True]  # Both mistakenly accepted

        res = calculate_grounding_metrics(gt, pred)
        assert res.accuracy == 0.0
        assert res.precision == 0.0
        assert res.hallucination_detection_rate == 0.0
        assert res.false_acceptance_rate == 1.0
        assert res.false_grounded == 2
        assert res.true_hallucination == 0

    def test_grounding_string_labels(self) -> None:
        gt = ["supported", "supported", "unsupported", "unsupported"]
        pred = ["supported", "unsupported", "unsupported", "supported"]

        res = calculate_grounding_metrics(gt, pred, positive_label="supported")
        # TP = 1 (gt[0] == pred[0] == supported)
        # FN = 1 (gt[1] == supported, pred[1] == unsupported)
        # TN = 1 (gt[2] == unsupported, pred[2] == unsupported)
        # FP = 1 (gt[3] == unsupported, pred[3] == supported)
        assert res.true_grounded == 1
        assert res.false_rejection == 1
        assert res.true_hallucination == 1
        assert res.false_grounded == 1
        assert res.total_claims == 4
        assert res.precision == 0.5
        assert res.recall == 0.5
        assert res.specificity == 0.5
        assert res.accuracy == 0.5

    def test_grounding_empty_inputs_zero_division(self) -> None:
        res = calculate_grounding_metrics([], [])
        assert res.total_claims == 0
        assert res.accuracy == 0.0
        assert res.precision == 0.0
        assert res.recall == 0.0
        assert res.f1 == 0.0

    def test_grounding_length_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="Length mismatch"):
            calculate_grounding_metrics([True], [True, False])
