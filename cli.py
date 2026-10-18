#!/usr/bin/env python3
"""
cli.py — Sovereign On-Premise AI Workbench Interactive CLI
==========================================================
Adapted from sovereign-agent reference architecture (SIH PS 26117).
Provides an interactive command-line interface for running single prompts,
analyzing attached files, or hosting an interactive multi-turn REPL session.

Usage:
  python cli.py "Calculate the derivative of x**3 * sin(x)"
  python cli.py --file workspace/sensor_data.csv "Summarize this spreadsheet"
  python cli.py --interactive
  python cli.py --thinking
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# Color formatting for terminal
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def check_ollama_running() -> bool:
    """Check if the local Ollama daemon is reachable on 127.0.0.1:11434."""
    import urllib.request

    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:  # noqa: S310
            return bool(resp.status == 200)
    except Exception:
        return False


async def run_single_prompt(
    prompt: str,
    file_path: str | None = None,
    session_id: str | None = None,
    user_role: str = "developer",
    show_thinking: bool = True,
) -> None:
    """Execute a single prompt through the Sovereign Workbench AgentService."""
    from app.agent.service import AgentService
    from app.agent.state import AgentRunRequest
    from app.identity.models import User
    from app.routing.schemas import FileMetadata

    if not check_ollama_running():
        print(f"\n{YELLOW}[WARNING] Local Ollama server is not running on 127.0.0.1:11434!{RESET}")
        print("Please ensure Ollama is started in another terminal: 'ollama serve'\n")

    session_id = session_id or f"cli_{uuid.uuid4().hex[:8]}"

    file_metadata: list[FileMetadata] = []
    if file_path:
        p = Path(file_path)
        if not p.exists():
            print(f"{RED}[ERROR] Attached file not found: {file_path}{RESET}")
            return
        ext = p.suffix.lower().lstrip(".")
        file_metadata.append(
            FileMetadata(
                filename=p.name,
                extension=ext,
                filepath=str(p.resolve()),
            )
        )

    print(f"\n{CYAN}{BOLD}======================================================================{RESET}")
    print(f"{CYAN}{BOLD}        SOVEREIGN WORKBENCH INTERACTIVE AGENT CLI{RESET}")
    print(f"{CYAN}{BOLD}======================================================================{RESET}")
    print(f"{BOLD}Session ID  :{RESET} {session_id}")
    print(f"{BOLD}User Role   :{RESET} {user_role}")
    print(f"{BOLD}Prompt      :{RESET} {prompt}")
    if file_metadata:
        print(f"{BOLD}Attached    :{RESET} {file_metadata[0].filename}")
    print(f"{CYAN}----------------------------------------------------------------------{RESET}")

    service = AgentService()
    user = User(
        id=uuid.uuid4(),
        username="cli_operator",
        email="operator@sovereign.local",
        role=user_role,
        is_active=True,
    )

    req = AgentRunRequest(
        prompt=prompt,
        session_id=session_id,
        file_metadata=file_metadata,
        max_iterations=8,
    )

    print(f"{DIM}[Agent] Routing and analyzing task...{RESET}")

    thinking_chunks: list[str] = []
    response_chunks: list[str] = []

    async for event in service.stream(req, user):
        event_type = event.get("event")
        data: dict[str, Any] = event.get("data", {})

        if event_type == "route":
            role = data.get("role", "general")
            model = data.get("model", "default")
            method = data.get("method", "waterfall")
            conf = float(data.get("confidence", 1.0))
            print(f"{GREEN}[Router]{RESET} Role: {BOLD}{role}{RESET} | Model: {model} | Method: {method} (conf={conf:.2f})")

        elif event_type == "tool_call":
            tool_name = data.get("tool", "unknown")
            tool_args = data.get("args", {})
            print(f"{YELLOW}[Tool Dispatch]{RESET} {BOLD}{tool_name}{RESET} -> args: {tool_args}")

        elif event_type == "tool_result":
            status = data.get("status", "unknown")
            output_prev = str(data.get("output") or data.get("summary") or "")[:200]
            print(f"{GREEN}[Tool Output]{RESET} Status: {status} | Result: {output_prev}")

        elif event_type == "thinking":
            token = str(data.get("token", ""))
            thinking_chunks.append(token)

        elif event_type == "token":
            token = str(data.get("token", ""))
            response_chunks.append(token)

        elif event_type == "done":
            final_resp = str(data.get("response", ""))
            artifacts = data.get("artifacts", [])
            iterations = data.get("iterations", 0)

            if show_thinking and thinking_chunks:
                full_thinking = "".join(thinking_chunks).strip()
                if full_thinking:
                    print(f"\n{DIM}{BOLD}--- Reasoning Trace ---{RESET}")
                    print(f"{DIM}{full_thinking}{RESET}")
                    print(f"{DIM}-----------------------{RESET}\n")

            print(f"\n{BOLD}{GREEN}=== Workbench Response ==={RESET}\n")
            print(final_resp or "".join(response_chunks).strip())
            print(f"\n{CYAN}----------------------------------------------------------------------{RESET}")
            print(f"{DIM}Completed in {iterations} iterations.{RESET}")
            if artifacts:
                print(f"{BOLD}Generated Deliverables:{RESET}")
                for art in artifacts:
                    print(f"  • {art}")
            print(f"{CYAN}======================================================================{RESET}\n")


async def run_interactive_repl(user_role: str = "developer", show_thinking: bool = True) -> None:
    """Run an interactive multi-turn REPL chat loop in the console."""
    session_id = f"repl_{uuid.uuid4().hex[:8]}"

    print(f"\n{CYAN}{BOLD}======================================================================{RESET}")
    print(f"{CYAN}{BOLD}  SOVEREIGN AGENTIC AI WORKBENCH — INTERACTIVE TERMINAL SHELL{RESET}")
    print(f"{CYAN}{BOLD}======================================================================{RESET}")
    print(f"Session ID: {session_id} | Role: {user_role}")
    print("Commands:")
    print("  exit / quit         : Exit the REPL")
    print("  file <path> <prompt>: Attach a file and run prompt")
    print("  help                : Show this help message")
    print(f"{CYAN}----------------------------------------------------------------------{RESET}\n")

    while True:
        try:
            user_input = input(f"{BOLD}{GREEN}sovereign>{RESET} ").strip()
            if not user_input:
                continue

            if user_input.lower() in ("exit", "quit", "q"):
                print("\nExiting Sovereign Workbench. Goodbye!")
                break

            if user_input.lower() == "help":
                print("Type any prompt to run, or attach a file using: file <path> <prompt>")
                continue

            file_arg = None
            prompt_arg = user_input
            if user_input.startswith("file "):
                parts = user_input[5:].split(" ", 1)
                file_arg = parts[0]
                prompt_arg = parts[1] if len(parts) > 1 else "Analyze this attached file."

            await run_single_prompt(
                prompt=prompt_arg,
                file_path=file_arg,
                session_id=session_id,
                user_role=user_role,
                show_thinking=show_thinking,
            )
        except (KeyboardInterrupt, EOFError):
            print("\nSession interrupted. Exiting.")
            break


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sovereign On-Premise AI Workbench Interactive CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("prompt", nargs="?", default=None, help="Prompt text to execute")
    parser.add_argument("-f", "--file", help="Path to attached file (CSV, XLSX, PDF, DOCX, TXT)")
    parser.add_argument("-i", "--interactive", action="store_true", help="Start interactive REPL chat session")
    parser.add_argument(
        "--role",
        default="developer",
        choices=["admin", "developer", "analyst", "user"],
        help="User RBAC role",
    )
    parser.add_argument("--no-thinking", action="store_true", help="Hide internal <think> reasoning traces")

    args = parser.parse_args()

    show_thinking = not args.no_thinking

    if args.interactive or (args.prompt is None and not args.file):
        asyncio.run(run_interactive_repl(user_role=args.role, show_thinking=show_thinking))
    else:
        prompt_text = args.prompt or "Please inspect the attached file and summarize key findings."
        asyncio.run(
            run_single_prompt(
                prompt=prompt_text,
                file_path=args.file,
                user_role=args.role,
                show_thinking=show_thinking,
            )
        )


if __name__ == "__main__":
    main()
