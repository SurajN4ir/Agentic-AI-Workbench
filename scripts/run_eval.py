"""
scripts/run_eval.py
===================
CLI tool to execute the Sovereign AI Workbench evaluation benchmark suite.
Usage:
  python scripts/run_eval.py
  python scripts/run_eval.py --category symbolic_math
  python scripts/run_eval.py --output report.md
"""

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import AsyncSessionLocal
from app.identity.models import User
from eval.runner import EvaluationRunner


async def main() -> None:
    parser = argparse.ArgumentParser(description="Sovereign AI Workbench Industrial Evaluation Suite")
    parser.add_argument("--category", type=str, default=None, help="Filter by benchmark category")
    parser.add_argument("--output", type=str, default="eval_report.md", help="Path to write Markdown report")
    args = parser.parse_args()

    print("=================================================================")
    print(" SOVEREIGN AGENTIC AI WORKBENCH — INDUSTRIAL BENCHMARK SUITE")
    print("=================================================================")

    # Create synthetic admin user for evaluation runs
    admin_user = User(
        id=uuid.uuid4(),
        username="eval_runner",
        role="admin",
        is_active=True,
        password_hash="",
    )

    runner = EvaluationRunner()
    print(f"Loaded {len(runner.cases)} benchmark scenarios from {runner.dataset_path.name}")
    if args.category:
        print(f"Applying category filter: '{args.category}'")

    print("\nExecuting evaluation loop...")
    async with AsyncSessionLocal() as db:
        report = await runner.run_evaluation(user=admin_user, db=db, category_filter=args.category)

    md_report = runner.format_markdown_report(report)

    output_path = Path(args.output)
    output_path.write_text(md_report, encoding="utf-8")
    print(f"\n[+] Evaluation completed in {report.total_cases} scenarios.")
    print(f"[+] Overall Accuracy: {report.accuracy_percentage:.1f}%")
    print(f"[+] Security Violations: {report.security_violations}")
    print(f"[+] Markdown report saved to: {output_path.resolve()}\n")

    print(md_report)

    if report.security_violations > 0:
        print("[-] FAILED: Security invariant violated!")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
