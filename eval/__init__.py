"""
eval/__init__.py
================
Sovereign AI Evaluation & Benchmarking Package.
"""

from eval.metrics import evaluate_case
from eval.runner import EvaluationRunner
from eval.schemas import BenchmarkCase, CaseEvaluationResult, EvaluationReport

__all__ = [
    "BenchmarkCase",
    "CaseEvaluationResult",
    "EvaluationReport",
    "EvaluationRunner",
    "evaluate_case",
]
