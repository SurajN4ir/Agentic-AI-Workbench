"""
eval/quantitative_metrics.py
============================
Reproducible, deterministic quantitative evaluation metrics for the Sovereign
On-Premise Agentic AI Workbench.

Covers:
  1. OCR Error Rates: Character Error Rate (CER) and Word Error Rate (WER)
     via Wagner-Fischer dynamic programming edit distance decomposition
     (substitutions, deletions, insertions).
  2. Classification & Routing: Multi-class confusion matrix, per-class
     precision, recall, F1, and macro/weighted summary metrics.
  3. Information Retrieval (RAG): Recall@k and Mean Reciprocal Rank (MRR)
     with deterministic handling for multi-chunk ground truth.
  4. Grounding & Citation Faithfulness: Binary classification metrics for
     supported vs. unsupported/fabricated claims, including hallucination
     detection rate and false acceptance rate.

Metric Conventions & Edge Case Specifications:
----------------------------------------------
  - CER / WER with Empty Reference:
      * If both reference and hypothesis are empty, CER = 0.0, WER = 0.0.
      * If reference is empty and hypothesis is non-empty, division by zero is
        avoided: by convention, returns 1.0 (pure insertion error) unless
        strict_empty=True is set (which raises ValueError).
      * If reference is non-empty and hypothesis is empty, rate = 1.0 (100% deletion).
      * Standard unclipped rate: rate = (S + D + I) / N. If insertions exceed
        reference length, rate can be > 1.0 (standard ASR/OCR evaluation convention).
  - Recall@k with Empty Ground Truth:
      * If relevant_ground_truth is empty and actual_retrieved[:k] is also empty,
        returns 1.0 (correctly retrieved zero items when none exist).
      * If relevant_ground_truth is empty and actual_retrieved[:k] is non-empty,
        returns 0.0 (irrelevant items retrieved when none were expected).
  - MRR with Empty Ground Truth:
      * If relevant_ground_truth is empty, MRR = 0.0 (no relevant rank exists).
  - Multi-class Missing Class & Zero-Division:
      * If (TP + FP) == 0, Precision defaults to zero_division (default 0.0).
      * If (TP + FN) == 0, Recall defaults to zero_division (default 0.0).
      * If (Precision + Recall) == 0, F1 defaults to zero_division (default 0.0).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any

# ============================================================================
# 1. OCR Error Rates (CER & WER)
# ============================================================================

@dataclass(frozen=True)
class EditDistanceResult:
    """Detailed breakdown of Levenshtein edit distance operations."""
    substitutions: int
    deletions: int
    insertions: int
    total_edits: int
    reference_length: int
    hypothesis_length: int
    error_rate: float
    is_empty_reference: bool = False
    is_undefined: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def levenshtein_operations(
    seq1: Sequence[Any],
    seq2: Sequence[Any],
) -> tuple[int, int, int, int]:
    """
    Computes exact substitutions, deletions, insertions, and total distance
    between two sequences using the Wagner-Fischer dynamic programming algorithm
    with backtrace alignment.

    Args:
        seq1: Reference sequence (ground truth).
        seq2: Hypothesis sequence (prediction).

    Returns:
        (substitutions, deletions, insertions, total_distance)
    """
    n, m = len(seq1), len(seq2)
    dp = [[0] * (m + 1) for _ in range(n + 1)]

    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if seq1[i - 1] == seq2[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,      # deletion from seq1
                dp[i][j - 1] + 1,      # insertion into seq1
                dp[i - 1][j - 1] + cost  # match or substitution
            )

    # Backtrace to count operation types
    i, j = n, m
    subs = dels = inss = 0

    while i > 0 or j > 0:
        if i > 0 and j > 0 and seq1[i - 1] == seq2[j - 1] and dp[i][j] == dp[i - 1][j - 1]:
            # Exact match - 0 cost
            i -= 1
            j -= 1
        elif i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + 1:
            # Substitution
            subs += 1
            i -= 1
            j -= 1
        elif i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            # Deletion from reference
            dels += 1
            i -= 1
        elif j > 0 and dp[i][j] == dp[i][j - 1] + 1:
            # Insertion into reference
            inss += 1
            j -= 1
        else:
            raise RuntimeError(f"Levenshtein backtrace failed at index ({i}, {j})")

    total = dp[n][m]
    return subs, dels, inss, total


def calculate_cer(
    reference: str,
    hypothesis: str,
    case_sensitive: bool = True,
    strict_empty: bool = False,
) -> EditDistanceResult:
    """
    Calculates Character Error Rate (CER) between ground truth reference and hypothesis.

    CER = (Substitutions + Deletions + Insertions) / len(reference)

    Edge Case Conventions:
      - If reference == "" and hypothesis == "": CER = 0.0.
      - If reference == "" and hypothesis != "":
          * If strict_empty is True: raises ValueError.
          * Otherwise: CER = 1.0 (pure insertion against empty ground truth).
      - If reference != "" and hypothesis == "": CER = 1.0 (100% deletion).
    """
    ref = reference if case_sensitive else reference.lower()
    hyp = hypothesis if case_sensitive else hypothesis.lower()

    ref_len = len(ref)
    hyp_len = len(hyp)

    if ref_len == 0:
        if hyp_len == 0:
            return EditDistanceResult(
                substitutions=0,
                deletions=0,
                insertions=0,
                total_edits=0,
                reference_length=0,
                hypothesis_length=0,
                error_rate=0.0,
                is_empty_reference=True,
                is_undefined=False,
            )
        if strict_empty:
            raise ValueError("Reference string is empty with non-empty hypothesis under strict_empty=True.")
        return EditDistanceResult(
            substitutions=0,
            deletions=0,
            insertions=hyp_len,
            total_edits=hyp_len,
            reference_length=0,
            hypothesis_length=hyp_len,
            error_rate=1.0,
            is_empty_reference=True,
            is_undefined=True,
        )

    subs, dels, inss, total = levenshtein_operations(ref, hyp)
    rate = total / ref_len

    return EditDistanceResult(
        substitutions=subs,
        deletions=dels,
        insertions=inss,
        total_edits=total,
        reference_length=ref_len,
        hypothesis_length=hyp_len,
        error_rate=round(rate, 6),
        is_empty_reference=False,
        is_undefined=False,
    )


def calculate_wer(
    reference: str,
    hypothesis: str,
    case_sensitive: bool = True,
    strict_empty: bool = False,
) -> EditDistanceResult:
    """
    Calculates Word Error Rate (WER) between ground truth reference and hypothesis.

    Words are tokenized by whitespace splitting.
    WER = (Substitutions + Deletions + Insertions) / count(reference_words)

    Edge Case Conventions:
      - If reference words == [] and hypothesis words == []: WER = 0.0, is_empty_reference=True, is_undefined=False.
      - If reference words == [] and hypothesis words != []:
          * If strict_empty is True: raises ValueError.
          * Otherwise: WER = 1.0, is_empty_reference=True, is_undefined=True.
      - If reference words != [] and hypothesis words == []: WER = 1.0.
    """
    ref_raw = reference if case_sensitive else reference.lower()
    hyp_raw = hypothesis if case_sensitive else hypothesis.lower()

    ref_words = ref_raw.strip().split()
    hyp_words = hyp_raw.strip().split()

    ref_len = len(ref_words)
    hyp_len = len(hyp_words)

    if ref_len == 0:
        if hyp_len == 0:
            return EditDistanceResult(
                substitutions=0,
                deletions=0,
                insertions=0,
                total_edits=0,
                reference_length=0,
                hypothesis_length=0,
                error_rate=0.0,
                is_empty_reference=True,
                is_undefined=False,
            )
        if strict_empty:
            raise ValueError("Reference word sequence is empty with non-empty hypothesis under strict_empty=True.")
        return EditDistanceResult(
            substitutions=0,
            deletions=0,
            insertions=hyp_len,
            total_edits=hyp_len,
            reference_length=0,
            hypothesis_length=hyp_len,
            error_rate=1.0,
            is_empty_reference=True,
            is_undefined=True,
        )

    subs, dels, inss, total = levenshtein_operations(ref_words, hyp_words)
    rate = total / ref_len

    return EditDistanceResult(
        substitutions=subs,
        deletions=dels,
        insertions=inss,
        total_edits=total,
        reference_length=ref_len,
        hypothesis_length=hyp_len,
        error_rate=round(rate, 6),
        is_empty_reference=False,
        is_undefined=False,
    )


def compute_aggregate_ocr_metrics(results: Sequence[EditDistanceResult]) -> dict[str, Any]:
    """
    Computes aggregate OCR metrics across multiple evaluations, explicitly segregating
    valid non-empty references from empty or undefined reference cases to prevent
    silent bias or misleading claims in aggregated benchmarks.

    Convention:
      - Units are fractional ratios: 0.0 represents 0% error, 1.0 represents 100% error.
      - Error rates > 1.0 indicate insertions exceeding the reference length (ASR/NIST standard).
      - Micro CER: sum(total_edits) / sum(reference_length) over valid non-empty references.
      - Macro CER: unweighted mean of individual valid ratios.
    """
    total_evals = len(results)
    if total_evals == 0:
        return {
            "total_evaluations": 0,
            "valid_evaluations": 0,
            "empty_reference_evaluations": 0,
            "undefined_evaluations": 0,
            "micro_cer": 0.0,
            "macro_cer": 0.0,
            "macro_cer_percent": 0.0,
            "mean_error_rate_valid_only": 0.0,
            "global_mean_error_rate": 0.0,
            "convention": "ratio (0.0=0%, 1.0=100%, >1.0=insertions exceed ref length)",
        }

    valid_results = [r for r in results if not r.is_empty_reference]
    empty_results = [r for r in results if r.is_empty_reference]
    undefined_results = [r for r in results if r.is_undefined]

    total_valid_edits = sum(r.total_edits for r in valid_results)
    total_valid_ref_len = sum(r.reference_length for r in valid_results)
    micro_cer = (
        round(total_valid_edits / total_valid_ref_len, 4)
        if total_valid_ref_len > 0
        else 0.0
    )
    macro_cer = (
        round(sum(r.error_rate for r in valid_results) / len(valid_results), 4)
        if valid_results
        else 0.0
    )
    global_mean = round(sum(r.error_rate for r in results) / total_evals, 4)

    return {
        "total_evaluations": total_evals,
        "valid_evaluations": len(valid_results),
        "empty_reference_evaluations": len(empty_results),
        "undefined_evaluations": len(undefined_results),
        "micro_cer": micro_cer,
        "macro_cer": macro_cer,
        "macro_cer_percent": round(macro_cer * 100, 2),
        "mean_error_rate_valid_only": macro_cer,
        "global_mean_error_rate": global_mean,
        "convention": "ratio (0.0=0%, 1.0=100%, >1.0=insertions exceed ref length)",
    }


# ============================================================================
# 2. Multi-class Routing & Classification Metrics
# ============================================================================

@dataclass(frozen=True)
class ClassMetrics:
    precision: float
    recall: float
    f1: float
    support: int
    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ClassificationReport:
    per_class: dict[str, ClassMetrics]
    accuracy: float
    macro_precision: float
    macro_recall: float
    macro_f1: float
    weighted_precision: float
    weighted_recall: float
    weighted_f1: float
    total_samples: int
    labels: list[str]
    confusion_matrix: dict[str, dict[str, int]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "per_class": {k: v.to_dict() for k, v in self.per_class.items()},
            "accuracy": self.accuracy,
            "macro_precision": self.macro_precision,
            "macro_recall": self.macro_recall,
            "macro_f1": self.macro_f1,
            "weighted_precision": self.weighted_precision,
            "weighted_recall": self.weighted_recall,
            "weighted_f1": self.weighted_f1,
            "total_samples": self.total_samples,
            "labels": self.labels,
            "confusion_matrix": self.confusion_matrix,
        }


def compute_confusion_matrix(
    y_true: Sequence[str],
    y_pred: Sequence[str],
    labels: Sequence[str] | None = None,
    allow_unknown: bool = False,
    unknown_label: str = "__UNKNOWN__",
) -> dict[str, Any]:
    """
    Computes deterministic multi-class confusion matrix.

    Input Validation & Unknown Class Handling:
      - Validates that len(y_true) == len(y_pred).
      - If labels is provided:
          * If allow_unknown is False (default) and any label in y_true or y_pred
            is not in labels, raises ValueError with exact unrecognized labels.
          * If allow_unknown is True, any unlisted label is mapped to unknown_label,
            which is appended to the matrix columns and rows.
      - If labels is None:
          * Dynamically computes sorted union of y_true and y_pred.

    Returns:
      {
        "labels": [...],
        "matrix": {actual_class: {predicted_class: count}},
        "total": int
      }
    """
    if len(y_true) != len(y_pred):
        raise ValueError(f"Length mismatch: len(y_true)={len(y_true)} vs len(y_pred)={len(y_pred)}")

    all_labels: list[str]
    has_unknown = False

    if labels is not None:
        explicit_labels = list(labels)
        unrecognized = (set(y_true) | set(y_pred)) - set(explicit_labels)
        if unrecognized:
            if not allow_unknown:
                raise ValueError(
                    f"Encountered unknown labels not in provided labels: {sorted(unrecognized)}. "
                    f"Set allow_unknown=True to map them to '{unknown_label}'."
                )
            has_unknown = True
            all_labels = explicit_labels + [unknown_label]
        else:
            all_labels = explicit_labels
    else:
        all_labels = sorted(set(y_true).union(set(y_pred)))

    # Initialize matrix
    matrix: dict[str, dict[str, int]] = {
        actual: {predicted: 0 for predicted in all_labels}
        for actual in all_labels
    }

    for act_raw, pred_raw in zip(y_true, y_pred, strict=True):
        actual = act_raw if act_raw in matrix else (unknown_label if has_unknown else act_raw)
        predicted = pred_raw if (actual in matrix and pred_raw in matrix[actual]) else (unknown_label if has_unknown else pred_raw)

        if actual in matrix and predicted in matrix[actual]:
            matrix[actual][predicted] += 1

    return {
        "labels": all_labels,
        "matrix": matrix,
        "total": len(y_true),
    }


def compute_classification_metrics(
    y_true: Sequence[str],
    y_pred: Sequence[str],
    labels: Sequence[str] | None = None,
    zero_division: float = 0.0,
    allow_unknown: bool = False,
    unknown_label: str = "__UNKNOWN__",
) -> ClassificationReport:
    """
    Computes per-class Precision, Recall, F1, and summary macro/weighted metrics.
    Guarantees deterministic behavior and avoids zero-division errors when
    a class is absent in predictions or ground truth.
    """
    if len(y_true) != len(y_pred):
        raise ValueError(f"Length mismatch: len(y_true)={len(y_true)} vs len(y_pred)={len(y_pred)}")

    cm_data = compute_confusion_matrix(
        y_true,
        y_pred,
        labels=labels,
        allow_unknown=allow_unknown,
        unknown_label=unknown_label,
    )
    ordered_labels: list[str] = cm_data["labels"]
    matrix: dict[str, dict[str, int]] = cm_data["matrix"]
    total_samples = len(y_true)

    per_class: dict[str, ClassMetrics] = {}

    for c in ordered_labels:
        tp = matrix.get(c, {}).get(c, 0)
        # FP: sum over all actual classes != c where prediction was c
        fp = sum(matrix.get(other_act, {}).get(c, 0) for other_act in ordered_labels if other_act != c)
        # FN: sum over all predictions != c where actual was c
        fn = sum(matrix.get(c, {}).get(other_pred, 0) for other_pred in ordered_labels if other_pred != c)
        # TN: all actual != c and predicted != c
        tn = sum(
            matrix.get(act, {}).get(pred, 0)
            for act in ordered_labels if act != c
            for pred in ordered_labels if pred != c
        )
        support = tp + fn

        prec = tp / (tp + fp) if (tp + fp) > 0 else zero_division
        rec = tp / (tp + fn) if (tp + fn) > 0 else zero_division
        f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else zero_division

        per_class[c] = ClassMetrics(
            precision=round(prec, 4),
            recall=round(rec, 4),
            f1=round(f1, 4),
            support=support,
            true_positives=tp,
            false_positives=fp,
            false_negatives=fn,
            true_negatives=tn,
        )

    # Accuracy
    total_correct = sum(matrix.get(c, {}).get(c, 0) for c in ordered_labels)
    accuracy = (total_correct / total_samples) if total_samples > 0 else zero_division

    # Macro averages (unweighted average across evaluated classes)
    num_classes = len(ordered_labels)
    if num_classes > 0:
        macro_prec = sum(m.precision for m in per_class.values()) / num_classes
        macro_rec = sum(m.recall for m in per_class.values()) / num_classes
        macro_f1 = sum(m.f1 for m in per_class.values()) / num_classes
    else:
        macro_prec = macro_rec = macro_f1 = zero_division

    # Weighted averages (weighted by support)
    total_support = sum(m.support for m in per_class.values())
    if total_support > 0:
        weighted_prec = sum(m.precision * m.support for m in per_class.values()) / total_support
        weighted_rec = sum(m.recall * m.support for m in per_class.values()) / total_support
        weighted_f1 = sum(m.f1 * m.support for m in per_class.values()) / total_support
    else:
        weighted_prec = weighted_rec = weighted_f1 = zero_division

    return ClassificationReport(
        per_class=per_class,
        accuracy=round(accuracy, 4),
        macro_precision=round(macro_prec, 4),
        macro_recall=round(macro_rec, 4),
        macro_f1=round(macro_f1, 4),
        weighted_precision=round(weighted_prec, 4),
        weighted_recall=round(weighted_rec, 4),
        weighted_f1=round(weighted_f1, 4),
        total_samples=total_samples,
        labels=ordered_labels,
        confusion_matrix=matrix,
    )


# ============================================================================
# 3. Information Retrieval (RAG) Metrics: Recall@k & MRR
# ============================================================================

def calculate_recall_at_k(
    actual_retrieved: Sequence[str],
    relevant_ground_truth: Sequence[str],
    k: int,
) -> float:
    """
    Calculates Recall@k for ranked retrieval.

    Recall@k = |Retrieved[:k] ∩ Relevant| / |Relevant|

    Edge Case Conventions:
      - k must be >= 1.
      - If relevant_ground_truth is empty:
          * If actual_retrieved[:k] is also empty: returns 1.0 (correctly returned 0).
          * If actual_retrieved[:k] has items: returns 0.0 (retrieved irrelevant noise).
      - If relevant_ground_truth has items:
          * Value is bounded in [0.0, 1.0].
    """
    if k < 1:
        raise ValueError(f"k must be >= 1, got k={k}")

    gt_set = set(relevant_ground_truth)
    if not gt_set:
        return 1.0 if len(actual_retrieved[:k]) == 0 else 0.0

    retrieved_top_k = set(actual_retrieved[:k])
    hits = len(retrieved_top_k.intersection(gt_set))
    return round(hits / len(gt_set), 4)


def calculate_mrr(
    actual_retrieved: Sequence[str],
    relevant_ground_truth: Sequence[str],
) -> float:
    """
    Calculates Mean Reciprocal Rank (MRR) for a single query.
    Finds the 1-indexed rank position of the first relevant chunk in actual_retrieved.

    Edge Case Conventions:
      - If relevant_ground_truth is empty: returns 0.0 (no relevant target exists).
      - If no relevant item is found in actual_retrieved: returns 0.0.
      - First item match at index 0 gives rank 1 -> 1.0 / 1 = 1.0.
    """
    gt_set = set(relevant_ground_truth)
    if not gt_set:
        return 0.0

    for rank_idx, item in enumerate(actual_retrieved, start=1):
        if item in gt_set:
            return round(1.0 / rank_idx, 4)

    return 0.0


def compute_mean_recall_at_k(
    queries_retrieved: Sequence[Sequence[str]],
    queries_ground_truth: Sequence[Sequence[str]],
    k: int,
) -> float:
    """Computes mean Recall@k across multiple queries."""
    if len(queries_retrieved) != len(queries_ground_truth):
        raise ValueError("Length mismatch between queries_retrieved and queries_ground_truth")
    if not queries_retrieved:
        return 0.0

    scores = [
        calculate_recall_at_k(act, gt, k)
        for act, gt in zip(queries_retrieved, queries_ground_truth, strict=True)
    ]
    return round(sum(scores) / len(scores), 4)


def compute_mean_mrr(
    queries_retrieved: Sequence[Sequence[str]],
    queries_ground_truth: Sequence[Sequence[str]],
) -> float:
    """Computes Mean Reciprocal Rank (MRR) across multiple queries."""
    if len(queries_retrieved) != len(queries_ground_truth):
        raise ValueError("Length mismatch between queries_retrieved and queries_ground_truth")
    if not queries_retrieved:
        return 0.0

    scores = [
        calculate_mrr(act, gt)
        for act, gt in zip(queries_retrieved, queries_ground_truth, strict=True)
    ]
    return round(sum(scores) / len(scores), 4)


# ============================================================================
# 4. Grounding & Citation Faithfulness Metrics
# ============================================================================

@dataclass(frozen=True)
class GroundingReport:
    """
    Binary classification metrics evaluating whether generated claims are
    factually grounded in context vs. unsupported/fabricated hallucinations.
    """
    accuracy: float
    precision: float
    recall: float
    specificity: float
    f1: float
    hallucination_detection_rate: float
    false_acceptance_rate: float
    true_grounded: int          # TP
    false_grounded: int         # FP (accepted hallucination - high risk)
    true_hallucination: int     # TN (rejected hallucination - successful defense)
    false_rejection: int        # FN (rejected valid claim)
    total_claims: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def calculate_grounding_metrics(
    ground_truth_supported: Sequence[bool | str],
    predicted_supported: Sequence[bool | str],
    positive_label: bool | str = True,
    zero_division: float = 0.0,
) -> GroundingReport:
    """
    Evaluates grounding verification decisions across a series of claims.

    Definitions:
      - Positive Class: "Supported / Grounded"
      - Negative Class: "Unsupported / Hallucinated"
      - TP: Claim is actually supported, and system verified it as supported.
      - TN: Claim is unsupported, and system correctly detected it as unsupported.
      - FP: Claim is unsupported, but system falsely verified it as supported (Type I Error / Fabricated Acceptance).
      - FN: Claim is supported, but system falsely flagged it as unsupported (Type II Error / False Rejection).
      - Hallucination Detection Rate = TN / (TN + FP) = Specificity.
      - False Acceptance Rate = FP / (FP + TN) = 1 - Specificity.

    Scope & Limitations Disclaimer:
      These grounding metrics measure classification agreement against
      human-labelled or ground-truth-annotated claim pairs in benchmark datasets.
      They do NOT establish open-ended semantic faithfulness or verify real-world
      factual correctness of ungrounded external claims.
    """
    if len(ground_truth_supported) != len(predicted_supported):
        raise ValueError(
            f"Length mismatch: len(gt)={len(ground_truth_supported)} vs len(pred)={len(predicted_supported)}"
        )

    def _normalize(val: bool | str) -> bool:
        if isinstance(val, bool):
            return val == positive_label if isinstance(positive_label, bool) else (val and positive_label.lower() in ("true", "supported", "grounded", "1"))
        s = str(val).strip().lower()
        pos_s = str(positive_label).strip().lower()
        if pos_s in ("true", "supported", "grounded", "1"):
            return s in ("true", "supported", "grounded", "1")
        return s == pos_s

    tp = tn = fp = fn = 0

    for gt_raw, pred_raw in zip(ground_truth_supported, predicted_supported, strict=True):
        actual_is_pos = _normalize(gt_raw)
        pred_is_pos = _normalize(pred_raw)

        if actual_is_pos and pred_is_pos:
            tp += 1
        elif not actual_is_pos and not pred_is_pos:
            tn += 1
        elif not actual_is_pos and pred_is_pos:
            fp += 1
        else:  # actual_is_pos and not pred_is_pos
            fn += 1

    total = tp + tn + fp + fn
    accuracy = (tp + tn) / total if total > 0 else zero_division
    prec = tp / (tp + fp) if (tp + fp) > 0 else zero_division
    rec = tp / (tp + fn) if (tp + fn) > 0 else zero_division
    specificity = tn / (tn + fp) if (tn + fp) > 0 else zero_division
    f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else zero_division
    far = fp / (fp + tn) if (fp + tn) > 0 else zero_division

    return GroundingReport(
        accuracy=round(accuracy, 4),
        precision=round(prec, 4),
        recall=round(rec, 4),
        specificity=round(specificity, 4),
        f1=round(f1, 4),
        hallucination_detection_rate=round(specificity, 4),
        false_acceptance_rate=round(far, 4),
        true_grounded=tp,
        false_grounded=fp,
        true_hallucination=tn,
        false_rejection=fn,
        total_claims=total,
    )
