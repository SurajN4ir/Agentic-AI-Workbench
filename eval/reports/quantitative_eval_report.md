# Quantitative Evaluation Report — Sovereign Agentic AI Workbench

**Date:** `2026-10-25T05:05:41.698106+00:00`<br>
**Execution Mode:** `live` (Live Inference: `False`)<br>
**Python:** `3.11.15` | **Platform:** `win32`<br>
**Ollama Reachable:** `False`<br>

---

## Executive Summary

| Evaluation Suite | Primary Metric | Score | Cases Evaluated | Status |
| :--- | :--- | :--- | :--- | :--- |
| **OCR Pipeline** | - | - | 4 attempted | unavailable |
| **Waterfall Routing** | Overall Accuracy | `1.0000` | 7 | Completed |
| **RAG Retrieval** | Mean MRR | `0.4000` | 5 | Completed |
| **Grounding & Citations** | Hallucination Detection Rate | `1.0000` | 7 | Completed |
| **Deterministic Tools** | Numerical Accuracy | `1.0000` | 3 | Completed |

---

## Detailed Breakdown by Subsystem

### 1. OCR Extraction (CER / WER / Keyword Recall)

> [!WARNING]
> No OCR engine was available for one or more live cases; unavailable outputs are excluded from accuracy metrics.

| Fixture | Engine | CER | WER | Keyword Recall | Latency (ms) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `clean_specification_plate.png` | `ocr_unavailable` | `N/A` | `N/A` | `N/A` | 226.0 |
| `ambiguous_serial_tag.png` | `ocr_unavailable` | `N/A` | `N/A` | `N/A` | 31.5 |
| `table_pump_telemetry.png` | `ocr_unavailable` | `N/A` | `N/A` | `N/A` | 33.9 |
| `scanned_turbine_inspection.pdf` | `ocr_unavailable` | `N/A` | `N/A` | `N/A` | 107.3 |

- **Valid References Count:** 0 of 0
- **Empty Reference Cases:** 0
- **Undefined Evaluated Cases:** 0
- **Micro CER (NIST standard sum(E)/sum(N)):** `0.0000`
- **Macro CER (mean of valid ratios):** `0.0000` (0.00%)

> [!NOTE]
> **Metric Convention:** CER and WER are standard fractional ratios (`0.0` = 0% error, `1.0` = 100% error). Ratios `> 1.0` indicate insertions exceeding reference length. Micro CER weights total edits across all valid references per NIST standard, preventing short verbose outputs from disproportionately skewing corpus accuracy. Empty references are strictly segregated.

### 2. Waterfall Routing Confusion Matrix

| Actual \ Predicted | `rag` | `code` | `math` | `spreadsheet` | `document` | `general` |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `rag` | 2 | 0 | 0 | 0 | 0 | 0 |
| `code` | 0 | 1 | 0 | 0 | 0 | 0 |
| `math` | 0 | 0 | 1 | 0 | 0 | 0 |
| `spreadsheet` | 0 | 0 | 0 | 1 | 0 | 0 |
| `document` | 0 | 0 | 0 | 0 | 1 | 0 |
| `general` | 0 | 0 | 0 | 0 | 0 | 1 |

### 3. RAG Retrieval Metrics

- **Recall@1:** `0.0000`
- **Recall@3:** `0.8000`
- **Recall@5:** `0.8000`
- **Mean Reciprocal Rank (MRR):** `0.4000`

### 4. Grounding & Citation Faithfulness

- **Overall Accuracy:** `0.5714`
- **Precision:** `0.0000`
- **Recall (Grounded Sensitivity):** `0.0000`
- **Hallucination Detection Rate (Specificity):** `1.0000`
- **False Acceptance Rate:** `0.0000`
- **True Grounded:** 0, **True Hallucination:** 4
- **False Grounded (High Risk Acceptance):** 0, **False Rejections:** 3

> [!NOTE]
> Grounding metrics measure classification agreement against human-labelled assertions. They do not claim general open-ended semantic omniscience.