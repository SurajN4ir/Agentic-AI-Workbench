"""
scripts/run_held_out_routing_eval.py
====================================
Evaluates the Sovereign On-Premise TaskRouter against an independent,
frozen held-out challenge dataset of 35 prompts across 7 categories:
  - rag
  - code
  - math
  - spreadsheet
  - document
  - ocr
  - general

Reports overall accuracy, per-class precision/recall/F1, confusion matrix,
and individual failure case breakdowns in completely separate reports.
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Ensure workspace root is in sys.path
_WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

from app.routing.schemas import FileMetadata, RouteDecision
from app.routing.service import get_task_router
from eval.quantitative_metrics import (
    compute_classification_metrics,
    compute_confusion_matrix,
)

logger = logging.getLogger("sovereign.eval.held_out_routing")

DEFAULT_DATASET = Path("eval/dataset/held_out_routing_challenge.json")
DEFAULT_OUTPUT_JSON = Path("eval/reports/held_out_routing_report.json")
DEFAULT_OUTPUT_MD = Path("eval/reports/held_out_routing_report.md")


def map_router_decision_to_eval_category(decision: RouteDecision) -> str:
    """Explicit mapping from TaskRouter output to evaluation category."""
    tools = decision.target_tools or []
    if "rag_search" in tools:
        return "rag"
    if "doc_gen" in tools:
        return "document"
    if "spreadsheet" in tools:
        return "spreadsheet"
    if "math_eval" in tools:
        return "math"
    if "code_sandbox" in tools or decision.role == "coding":
        return "code"
    if decision.role in ("ocr", "vision") or "ocr_extract" in tools:
        return "ocr"
    return "general"


def run_held_out_routing_evaluation(
    dataset_path: Path = DEFAULT_DATASET,
    output_json: Path = DEFAULT_OUTPUT_JSON,
    output_md: Path = DEFAULT_OUTPUT_MD,
) -> dict[str, Any]:
    """Runs production router over frozen held-out challenge dataset."""
    if not dataset_path.exists():
        raise FileNotFoundError(f"Held-out dataset not found: {dataset_path}")

    with open(dataset_path, encoding="utf-8") as f:
        data = json.load(f)

    categories: list[str] = data.get(
        "categories",
        ["rag", "code", "math", "spreadsheet", "document", "ocr", "general"],
    )
    test_cases: list[dict[str, Any]] = data.get("test_cases", [])

    router = get_task_router()

    y_true: list[str] = []
    y_pred: list[str] = []
    case_results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for tc in test_cases:
        tc_id = tc["id"]
        prompt = tc["prompt"]
        expected = tc["expected_category"]
        raw_meta = tc.get("file_metadata")
        meta_list = [FileMetadata(**m) for m in raw_meta] if raw_meta else None

        t0 = time.perf_counter()
        decision = router.route(prompt, file_metadata=meta_list)
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)

        predicted = map_router_decision_to_eval_category(decision)
        is_correct = (predicted == expected)

        y_true.append(expected)
        y_pred.append(predicted)

        record = {
            "id": tc_id,
            "prompt": prompt,
            "domain": tc.get("domain", "unknown"),
            "expected_category": expected,
            "predicted_category": predicted,
            "is_correct": is_correct,
            "has_file_attachment": bool(meta_list),
            "router_role": decision.role,
            "router_method": decision.method,
            "router_confidence": decision.confidence,
            "target_tools": decision.target_tools or [],
            "reasoning": decision.reasoning,
            "latency_ms": latency_ms,
        }
        case_results.append(record)

        if not is_correct:
            failures.append({
                "id": tc_id,
                "prompt": prompt,
                "expected": expected,
                "predicted": predicted,
                "method": decision.method,
                "reasoning": decision.reasoning,
                "note": tc.get("note", ""),
            })

    cm = compute_confusion_matrix(y_true, y_pred, labels=categories, allow_unknown=True)
    report = compute_classification_metrics(y_true, y_pred, labels=categories, allow_unknown=True)

    summary_report: dict[str, Any] = {
        "benchmark": "held_out_routing_challenge_v1",
        "timestamp": datetime.now(UTC).isoformat(),
        "total_cases": len(case_results),
        "total_correct": sum(1 for c in case_results if c["is_correct"]),
        "overall_accuracy": report.accuracy,
        "macro_precision": report.macro_precision,
        "macro_recall": report.macro_recall,
        "macro_f1": report.macro_f1,
        "weighted_f1": report.weighted_f1,
        "confusion_matrix": cm,
        "per_class_metrics": {k: v.to_dict() for k, v in report.per_class.items()},
        "failures_count": len(failures),
        "failures": failures,
        "cases": case_results,
    }

    # Save JSON
    output_json.parent.mkdir(parents=True, exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(summary_report, f, indent=2)

    # Save Markdown
    output_md.parent.mkdir(parents=True, exist_ok=True)
    md_text = render_markdown(summary_report, categories)
    output_md.write_text(md_text, encoding="utf-8")

    return summary_report


def render_markdown(report: dict[str, Any], categories: list[str]) -> str:
    """Renders comprehensive GitHub-style markdown report."""
    lines: list[str] = [
        "# Held-Out Routing Challenge Report — Sovereign AI Workbench",
        "",
        f"**Date:** `{report['timestamp']}`  ",
        f"**Benchmark:** `{report['benchmark']}` (Frozen Challenge Dataset)  ",
        f"**Cases Evaluated:** `{report['total_cases']}` | **Overall Accuracy:** `{report['overall_accuracy']:.4f}` ({report['total_correct']}/{report['total_cases']})  ",
        f"**Macro F1:** `{report['macro_f1']:.4f}` | **Weighted F1:** `{report['weighted_f1']:.4f}`  ",
        "",
        "---",
        "",
        "## Per-Class Classification Performance",
        "",
        "| Category | Precision | Recall | F1 Score | Support (Count) | True Positives | False Positives | False Negatives |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]

    per_class = report.get("per_class_metrics", {})
    for cat in categories:
        m = per_class.get(cat, {})
        lines.append(
            f"| `{cat}` | `{m.get('precision', 0.0):.4f}` | `{m.get('recall', 0.0):.4f}` | `{m.get('f1', 0.0):.4f}` | "
            f"{m.get('support', 0)} | {m.get('true_positives', 0)} | {m.get('false_positives', 0)} | {m.get('false_negatives', 0)} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## Confusion Matrix (7x7)",
        "",
    ])

    cm = report.get("confusion_matrix", {})
    matrix = cm.get("matrix", {})
    labels = cm.get("labels", categories)

    header = "| Actual \\ Predicted | " + " | ".join(f"`{lbl}`" for lbl in labels) + " |"
    sep = "| :--- | " + " | ".join(":---:" for _ in labels) + " |"
    lines.extend([header, sep])

    for act in labels:
        row = [str(matrix.get(act, {}).get(pred, 0)) for pred in labels]
        lines.append(f"| `{act}` | " + " | ".join(row) + " |")

    lines.extend([
        "",
        "---",
        "",
        f"## Failures & Misclassifications ({report['failures_count']} total)",
        "",
    ])

    if not report["failures"]:
        lines.append("No failures! All 35 held-out challenge prompts routed correctly.")
    else:
        lines.append("| Case ID | Prompt | Expected | Predicted | Routing Method | Note / Reason |")
        lines.append("| :--- | :--- | :---: | :---: | :--- | :--- |")
        for f in report["failures"]:
            p_clean = f["prompt"].replace("|", "\\|")
            lines.append(
                f"| `{f['id']}` | \"{p_clean}\" | `{f['expected']}` | `{f['predicted']}` | `{f['method']}` | {f.get('note', '')} |"
            )

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run TaskRouter over frozen held-out challenge dataset.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET, help="Path to held-out challenge dataset JSON.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_JSON, help="Path for JSON output report.")
    parser.add_argument("--summary", type=Path, default=DEFAULT_OUTPUT_MD, help="Path for Markdown summary output.")

    args = parser.parse_args()

    print("[*] Running Sovereign TaskRouter on held-out challenge dataset...")
    report = run_held_out_routing_evaluation(
        dataset_path=args.dataset,
        output_json=args.output,
        output_md=args.summary,
    )
    print(f"[+] Evaluation finished: {report['total_correct']}/{report['total_cases']} correct ({report['overall_accuracy'] * 100:.2f}% accuracy)")
    print(f"[+] Failures count: {report['failures_count']}")
    print(f"[+] JSON report saved: {args.output}")
    print(f"[+] Markdown summary saved: {args.summary}")


if __name__ == "__main__":
    main()
