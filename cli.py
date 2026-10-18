#!/usr/bin/env python3
"""
cli.py — Sovereign On-Premise AI Workbench Interactive CLI
==========================================================
Attribution: Adapted from sathwik-anumandla/sovereign-agent (SIH PS 26117).
Hardened for enterprise production with:
1. Strict RBAC policy equivalence (same role-gated tools as the API).
2. Workspace-contained file staging (external files are quarantined into session workspace).
3. Structured execution trace (Request -> Router -> Selected Tool -> Auth Result -> Tool Result -> Final Answer).
4. Sanitized error messages (redacts secrets, tokens, and absolute host paths).
5. Raw <think> traces disabled by default; enabled only with --show-thinking.

Usage:
  python cli.py "Calculate the derivative of x**3 * sin(x)"
  python cli.py --file sample_data.csv "Summarize this dataset"
  python cli.py --role viewer "Run code in sandbox"  # Will be blocked by RBAC!
  python cli.py --interactive
"""

from __future__ import annotations

import argparse
import asyncio
import re
import shutil
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


def sanitize_message(text: str) -> str:
    """Sanitize errors and logs to prevent leaking tokens, passwords, or host filesystem paths."""
    # Redact potential JWT or Bearer tokens
    text = re.sub(r"Bearer\s+[a-zA-Z0-9_\-\.]+", "Bearer [REDACTED]", text, flags=re.IGNORECASE)
    text = re.sub(r'jwt_secret_key["\']?\s*[:=]\s*["\']?[^"\'\s]+', "jwt_secret_key=[REDACTED]", text)
    text = re.sub(r'password["\']?\s*[:=]\s*["\']?[^"\'\s]+', "password=[REDACTED]", text)

    # Redact absolute user home directory paths
    home_dir = str(Path.home())
    if home_dir in text:
        text = text.replace(home_dir, "~")

    return text


def stage_file_into_session(source_file: str, session_id: str) -> Path:
    """Safely stages a user-provided file into the session workspace uploads directory.

    Guarantees the agent interacts only with workspace-contained copies, preventing
    arbitrary host filesystem exploration.
    """
    from app.config import get_settings
    from app.tools.interface import validate_workspace_path

    p = Path(source_file).resolve()
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(f"Source file not found: {source_file}")

    file_size = p.stat().st_size
    max_size = get_settings().max_upload_size_bytes
    if file_size > max_size:
        raise ValueError(f"File size ({file_size} bytes) exceeds maximum upload limit ({max_size} bytes).")

    # Destination strictly inside workspace/<session_id>/uploads/<filename>
    rel_dest = f"uploads/{p.name}"
    target_path = validate_workspace_path(rel_dest, session_id, create_parents=True)
    shutil.copy2(p, target_path)
    return target_path


async def run_single_prompt(
    prompt: str,
    file_path: str | None = None,
    session_id: str | None = None,
    user_role: str = "developer",
    show_thinking: bool = False,
) -> None:
    """Execute a single prompt through the Sovereign Workbench AgentService."""
    from app.agent.service import AgentService
    from app.agent.state import AgentRunRequest
    from app.identity.models import User
    from app.routing.schemas import FileMetadata

    if not check_ollama_running():
        print(f"\n{YELLOW}[WARNING] Local Ollama server is not running on 127.0.0.1:11434!{RESET}")
        print("Please ensure Ollama is started: 'ollama serve'\n")

    session_id = session_id or f"cli_{uuid.uuid4().hex[:8]}"

    file_metadata: list[FileMetadata] = []
    if file_path:
        try:
            staged_path = stage_file_into_session(file_path, session_id)
            ext = staged_path.suffix.lower().lstrip(".")
            file_metadata.append(
                FileMetadata(
                    filename=staged_path.name,
                    extension=ext,
                    filepath=str(staged_path),
                )
            )
        except Exception as e:
            print(f"{RED}[ERROR] File staging failed: {sanitize_message(str(e))}{RESET}")
            return

    print(f"\n{CYAN}{BOLD}======================================================================{RESET}")
    print(f"{CYAN}{BOLD}        SOVEREIGN WORKBENCH — CONTROLLED EXECUTION TRACE{RESET}")
    print(f"{CYAN}{BOLD}======================================================================{RESET}")
    print(f"{BOLD}[1/5] Request       :{RESET} {prompt}")
    print(f"      Session ID    : {session_id} | Role: {BOLD}{user_role}{RESET}")
    if file_metadata:
        print(f"      Staged File   : {file_metadata[0].filename} (quarantined in session workspace)")
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

    thinking_chunks: list[str] = []
    response_chunks: list[str] = []
    tool_dispatches = 0

    try:
        async for event in service.stream(req, user):
            event_type = event.get("event")
            data: dict[str, Any] = event.get("data", {})

            if event_type == "route":
                role = data.get("role", "general")
                model = data.get("model", "default")
                method = data.get("method", "waterfall")
                conf = float(data.get("confidence", 1.0))
                print(f"{BOLD}[2/5] Route Decision:{RESET} Persona: {BOLD}{role}{RESET} (Model: {model}) | Method: {method} (conf={conf:.2f})")

            elif event_type == "tool_call":
                tool_dispatches += 1
                tool_name = data.get("tool", "unknown")
                tool_args = data.get("args", {})
                print(f"{YELLOW}[3/5] Tool Selected :{RESET} {BOLD}{tool_name}{RESET} with parameters:")
                for k, v in tool_args.items():
                    print(f"      • {k}: {v}")

            elif event_type == "tool_result":
                status = data.get("status", "unknown")
                raw_out = str(data.get("output") or data.get("summary") or data.get("error") or "")
                out_snippet = sanitize_message(raw_out)[:250]
                status_color = GREEN if status == "success" else RED
                print(f"{status_color}[4/5] Tool Execution:{RESET} Status: {BOLD}{status}{RESET} -> {out_snippet}")

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
                    full_thinking = sanitize_message("".join(thinking_chunks).strip())
                    if full_thinking:
                        print(f"\n{DIM}{BOLD}--- Operational Reasoning Diagnostics (Developer Mode) ---{RESET}")
                        print(f"{DIM}{full_thinking}{RESET}")
                        print(f"{DIM}------------------------------------------------------------{RESET}\n")

                answer_text = final_resp or "".join(response_chunks).strip()
                print(f"\n{BOLD}{GREEN}[5/5] Final Answer  :{RESET}\n")
                print(sanitize_message(answer_text))
                print(f"\n{CYAN}----------------------------------------------------------------------{RESET}")
                print(f"{DIM}Workflow complete: {iterations} iterations, {tool_dispatches} tool executions.{RESET}")
                if artifacts:
                    print(f"{BOLD}Validated Deliverables:{RESET}")
                    for art in artifacts:
                        print(f"  • {art}")
                print(f"{CYAN}======================================================================{RESET}\n")
    except Exception as exc:
        print(f"\n{RED}[FATAL ERROR] Agent workflow execution failed: {sanitize_message(str(exc))}{RESET}")


async def run_interactive_repl(user_role: str = "developer", show_thinking: bool = False) -> None:
    """Run an interactive multi-turn REPL chat loop in the console."""
    session_id = f"repl_{uuid.uuid4().hex[:8]}"

    print(f"\n{CYAN}{BOLD}======================================================================{RESET}")
    print(f"{CYAN}{BOLD}  SOVEREIGN AGENTIC AI WORKBENCH — INTERACTIVE TERMINAL SHELL{RESET}")
    print(f"{CYAN}{BOLD}======================================================================{RESET}")
    print(f"Session ID : {session_id} | Role: {user_role}")
    print("Commands:")
    print("  exit / quit         : Exit the REPL")
    print("  file <path> <prompt>: Stage file into workspace and run prompt")
    print("  help                : Show this help message")
    print(f"{CYAN}----------------------------------------------------------------------{RESET}\n")

    while True:
        try:
            user_input = input(f"{BOLD}{GREEN}sovereign [{user_role}]>{RESET} ").strip()
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
    parser.add_argument("-f", "--file", help="Path to file to safely stage into workspace")
    parser.add_argument("-i", "--interactive", action="store_true", help="Start interactive REPL chat session")
    parser.add_argument(
        "--role",
        default="developer",
        choices=["admin", "developer", "analyst", "operator", "viewer"],
        help="User RBAC role (enforces identical tool permission gating as the API)",
    )
    parser.add_argument(
        "--show-thinking",
        action="store_true",
        help="Enable internal model <think> reasoning diagnostics (disabled by default for confidentiality)",
    )

    args = parser.parse_args()

    if args.interactive or (args.prompt is None and not args.file):
        asyncio.run(run_interactive_repl(user_role=args.role, show_thinking=args.show_thinking))
    else:
        prompt_text = args.prompt or "Please inspect the attached file and summarize key findings."
        asyncio.run(
            run_single_prompt(
                prompt=prompt_text,
                file_path=args.file,
                user_role=args.role,
                show_thinking=args.show_thinking,
            )
        )


if __name__ == "__main__":
    main()
