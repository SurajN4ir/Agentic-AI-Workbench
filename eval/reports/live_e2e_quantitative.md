# Quantitative Evaluation Report — Sovereign Agentic AI Workbench

**Date:** `2026-10-25T05:11:11.458181+00:00`<br>
**Execution Mode:** `live` (Live Inference: `True`)<br>
**Python:** `3.11.15` | **Platform:** `win32`<br>
**Ollama Reachable:** `True`<br>

---

## Executive Summary

| Evaluation Suite | Primary Metric | Score | Cases Evaluated | Status |
| :--- | :--- | :--- | :--- | :--- |
| **OCR Pipeline** | Macro CER / Micro CER (ratio) | `0.0791` / `0.0442` | 4 | Completed |
| **Waterfall Routing** | - | - | 0 | Skipped |
| **RAG Retrieval** | - | - | 0 | Skipped |
| **Grounding & Citations** | - | - | 0 | Skipped |
| **Deterministic Tools** | - | - | 0 | Skipped |

---

## Detailed Breakdown by Subsystem

### 1. OCR Extraction (CER / WER / Keyword Recall)

| Fixture | Engine | CER | WER | Keyword Recall | Latency (ms) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `clean_specification_plate.png` | `ollama_vision:qwen3.5:4b` | `0.0336` | `0.2778` | `1.00` | 18620.5 |
| `ambiguous_serial_tag.png` | `ollama_vision:qwen3.5:4b` | `0.2444` | `1.0000` | `0.00` | 1913.5 |
| `table_pump_telemetry.png` | `ollama_vision:qwen3.5:4b` | `0.0000` | `0.0000` | `1.00` | 2837.4 |
| `scanned_turbine_inspection.pdf` | `ollama_vision:qwen3.5:4b` | `0.0383` | `0.1000` | `0.88` | 8594.5 |

- **Valid References Count:** 4 of 4
- **Empty Reference Cases:** 0
- **Undefined Evaluated Cases:** 0
- **Micro CER (NIST standard sum(E)/sum(N)):** `0.0442`
- **Macro CER (mean of valid ratios):** `0.0791` (7.91%)

> [!NOTE]
> **Metric Convention:** CER and WER are standard fractional ratios (`0.0` = 0% error, `1.0` = 100% error). Ratios `> 1.0` indicate insertions exceeding reference length. Micro CER weights total edits across all valid references per NIST standard, preventing short verbose outputs from disproportionately skewing corpus accuracy. Empty references are strictly segregated.

### 2. Waterfall Routing Confusion Matrix


### 3. RAG Retrieval Metrics

- **Recall@1:** `0.0000`
- **Recall@3:** `0.0000`
- **Recall@5:** `0.0000`
- **Mean Reciprocal Rank (MRR):** `0.0000`

### 4. Grounding & Citation Faithfulness
