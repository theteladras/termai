"""Command preview and execution.

Every generated command goes through preview_and_execute(), which shows
the user what will run, checks for destructive patterns, asks for explicit
confirmation, then executes via subprocess and logs the result.
"""

from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING

from termai.safety import check_command, format_warnings
from termai.logger import log_command
from termai.plugins import get_registry

if TYPE_CHECKING:
    from termai.context import SessionContext

CYAN = "\033[1;36m"
GREEN = "\033[1;32m"
RED = "\033[1;31m"
DIM = "\033[2m"
RESET = "\033[0m"


def preview_and_execute(
    command: str,
    ctx: "SessionContext",
    *,
    dry_run: bool = False,
    auto_yes: bool = False,
    instruction: str = "",
) -> bool | None:
    """Show a command preview, run safety checks, and optionally execute.

    Returns True if the command executed successfully, False on failure,
    or None if execution was skipped (dry-run / cancelled).
    """
    warnings = check_command(command)

    print()
    border_color = RED if warnings else CYAN
    print(f"  {border_color}┌─ Command Preview ─────────────────────{RESET}")
    for line in command.splitlines():
        print(f"  {border_color}│{RESET}  {line}")
    print(f"  {border_color}└───────────────────────────────────────{RESET}")

    if warnings:
        print()
        print(format_warnings(warnings))

    if dry_run:
        print(f"\n  {CYAN}(dry-run mode — command will NOT be executed){RESET}")
        return None

    # -y / --yes: skip confirmation, but still block critical commands
    if auto_yes:
        if any(w.severity == "critical" for w in warnings):
            print(f"\n  {RED}--yes cannot override critical safety warnings.{RESET}")
            prompt = f"  {RED}Type the full word 'execute' to confirm:{RESET} "
            answer = input(prompt).strip().lower()
            if answer != "execute":
                print("[termai] Command cancelled.")
                return None
        # non-critical: proceed directly
    else:
        print()
        if any(w.severity == "critical" for w in warnings):
            prompt = f"  {RED}Type the full word 'execute' to confirm:{RESET} "
            answer = input(prompt).strip().lower()
            if answer != "execute":
                print("[termai] Command cancelled.")
                return None
        else:
            prompt_suffix = " (dangerous!) " if warnings else " "
            answer = input(f"Execute this command?{prompt_suffix}[y/N] ").strip().lower()
            if answer not in ("y", "yes"):
                print("[termai] Command cancelled.")
                return None

    registry = get_registry()
    command = registry.run_pre_hooks(command, ctx)
    return run_command(command, ctx, instruction=instruction)


def run_command(
    command: str,
    ctx: "SessionContext",
    *,
    instruction: str = "",
    timeout: int | None = None,
) -> bool:
    """Execute a shell command via subprocess and log the result.

    Streams stdout/stderr to the terminal in real time.
    Returns True on success (exit code 0).
    """
    print(f"\n  {DIM}Running…{RESET}\n")

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=ctx.cwd,
            timeout=timeout,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        success = result.returncode == 0

        if success:
            print(f"\n  {GREEN}✓ Command completed (exit code 0){RESET}")
        else:
            print(f"\n  {RED}✗ Command failed (exit code {result.returncode}){RESET}")

    except subprocess.TimeoutExpired:
        print(f"\n  {RED}✗ Command timed out{RESET}")
        success = False
    except Exception as e:
        print(f"\n  {RED}✗ Execution error: {e}{RESET}")
        success = False

    ctx.record(command)
    ctx.refresh_cwd()
    log_command(command, instruction=instruction, success=success)

    registry = get_registry()
    registry.run_post_hooks(command, ctx)

    return success
