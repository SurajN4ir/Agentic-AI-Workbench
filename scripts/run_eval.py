"""
scripts/run_eval.py
===================
CLI tool to execute the Sovereign AI Workbench evaluation benchmark suite.
Supports live Ollama on-prem models as well as deterministic mock provider for CI/benchmarking.

Usage:
  python scripts/run_eval.py
  python scripts/run_eval.py --mock
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
from eval.mock_provider import MockBenchmarkProvider
from eval.runner import EvaluationRunner

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def main() -> None:
    parser = argparse.ArgumentParser(description="Sovereign AI Workbench Industrial Evaluation Suite")
    parser.add_argument("--category", type=str, default=None, help="Filter by benchmark category")
    parser.add_argument("--mock", action="store_true", help="Use deterministic mock provider for fast offline benchmarking")
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

    provider = MockBenchmarkProvider() if args.mock else None
    runner = EvaluationRunner(provider=provider)
    print(f"Loaded {len(runner.cases)} benchmark scenarios from {runner.dataset_path.name}")
    if args.mock:
        print("Using deterministic MockBenchmarkProvider")
    else:
        print("Using on-premise Ollama provider")

    if args.category:
        print(f"Applying category filter: '{args.category}'")

    print("\nExecuting evaluation loop...")
    db_session = None
    try:
        async with AsyncSessionLocal() as session:
            # Quick check if database is reachable
            from sqlalchemy import text
            await session.execute(text("SELECT 1"))
            db_session = session
            report = await runner.run_evaluation(user=admin_user, db=db_session, category_filter=args.category)
    except Exception as exc:
        print(f"[!] Database connection unavailable ({exc}). Proceeding in decoupled evaluation mode...")
        report = await runner.run_evaluation(user=admin_user, db=None, category_filter=args.category)

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
