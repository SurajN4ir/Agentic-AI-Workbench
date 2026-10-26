# Held-Out Routing Challenge Report — Sovereign AI Workbench

**Date:** `2026-10-24T18:55:59.305812+00:00`<br>
**Benchmark:** `held_out_routing_challenge_v1` (Frozen Challenge Dataset)<br>
**Cases Evaluated:** `35` | **Overall Accuracy:** `1.0000` (35/35)<br>
**Macro F1:** `1.0000` | **Weighted F1:** `1.0000`<br>

---

## Per-Class Classification Performance

| Category | Precision | Recall | F1 Score | Support (Count) | True Positives | False Positives | False Negatives |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `rag` | `1.0000` | `1.0000` | `1.0000` | 5 | 5 | 0 | 0 |
| `code` | `1.0000` | `1.0000` | `1.0000` | 5 | 5 | 0 | 0 |
| `math` | `1.0000` | `1.0000` | `1.0000` | 5 | 5 | 0 | 0 |
| `spreadsheet` | `1.0000` | `1.0000` | `1.0000` | 5 | 5 | 0 | 0 |
| `document` | `1.0000` | `1.0000` | `1.0000` | 5 | 5 | 0 | 0 |
| `ocr` | `1.0000` | `1.0000` | `1.0000` | 5 | 5 | 0 | 0 |
| `general` | `1.0000` | `1.0000` | `1.0000` | 5 | 5 | 0 | 0 |

---

## Confusion Matrix (7x7)

| Actual \ Predicted | `rag` | `code` | `math` | `spreadsheet` | `document` | `ocr` | `general` |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `rag` | 5 | 0 | 0 | 0 | 0 | 0 | 0 |
| `code` | 0 | 5 | 0 | 0 | 0 | 0 | 0 |
| `math` | 0 | 0 | 5 | 0 | 0 | 0 | 0 |
| `spreadsheet` | 0 | 0 | 0 | 5 | 0 | 0 | 0 |
| `document` | 0 | 0 | 0 | 0 | 5 | 0 | 0 |
| `ocr` | 0 | 0 | 0 | 0 | 0 | 5 | 0 |
| `general` | 0 | 0 | 0 | 0 | 0 | 0 | 5 |

---

## Failures & Misclassifications (0 total)

No failures! All 35 held-out challenge prompts routed correctly.