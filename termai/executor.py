"""Command preview and execution.

Every generated command goes through preview_and_execute(), which shows
the user what will run, checks for destructive patterns, asks for explicit
confirmation, then executes via subprocess and logs the result.

Harmless commands and user-approved commands skip the prompt entirely.

When multiple independent commands are generated, they can be executed
in parallel using preview_and_execute_batch().
"""

from __future__ import annotations

import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING

from termai.safety import check_command, format_warnings
from termai.allowlist import should_auto_execute, add_to_session, add_to_permanent
from termai.logger import log_command
from termai.plugins import get_registry

if TYPE_CHECKING:
    from termai.context import SessionContext

CYAN = "\033[1;36m"
GREEN = "\033[1;32m"
YELLOW = "\033[0;33m"
RED = "\033[1;31m"
BOLD = "\033[1m"
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

    # Auto-execute safe / allowed commands (unless they have safety warnings)
    if not warnings and (auto_yes or should_auto_execute(command)):
        print(f"  {DIM}(auto-approved){RESET}")
        registry = get_registry()
        command = registry.run_pre_hooks(command, ctx)
        return run_command(command, ctx, instruction=instruction)

    # Critical warnings always require typing "execute"
    if any(w.severity == "critical" for w in warnings):
        print(f"\n  {RED}This command is critically dangerous.{RESET}")
        prompt = f"  {RED}Type 'execute' to confirm:{RESET} "
        try:
            answer = input(prompt).strip().lower()
        except (KeyboardInterrupt, EOFError):
            print(f"\n  {DIM}Cancelled.{RESET}")
            return None
        if answer != "execute":
            print(f"  {DIM}Cancelled.{RESET}")
            return None
    else:
        answer = _prompt_with_options(command, has_warnings=bool(warnings))
        if answer is None:
            return None

    registry = get_registry()
    command = registry.run_pre_hooks(command, ctx)
    return run_command(command, ctx, instruction=instruction)


def _prompt_with_options(command: str, *, has_warnings: bool) -> str | None:
    """Show execution options and return the user's choice, or None to cancel.

    Options:
      y  — execute once
      a  — always allow this command (permanent)
      s  — allow for this session
      n  — cancel (default)
    """
    print()
    warn_tag = f" {YELLOW}(has warnings){RESET}" if has_warnings else ""
    print(f"  {BOLD}y{RESET} execute        "
          f"{BOLD}a{RESET} always allow   "
          f"{BOLD}s{RESET} session allow   "
          f"{BOLD}n{RESET} cancel{warn_tag}")

    try:
        answer = input(f"\n  {BOLD}Run?{RESET} [y/a/s/N] ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print(f"\n  {DIM}Cancelled.{RESET}")
        return None

    if answer in ("y", "yes"):
        return "y"
    elif answer == "a":
        add_to_permanent(command)
        print(f"  {GREEN}✓{RESET} Added to permanent allow list")
        return "a"
    elif answer == "s":
        add_to_session(command)
        print(f"  {GREEN}✓{RESET} Allowed for this session")
        return "s"
    else:
        print(f"  {DIM}Cancelled.{RESET}")
        return None


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


# -- Parallel execution -------------------------------------------------------

_DEPENDENCY_MARKERS = re.compile(
    r"\$\(|`.*`"        # command substitution
    r"|\|\s*\w"          # pipe to another command
    r"|&&|;\s*\w"        # chained commands
    r"|>\s|>>"           # output redirection
    r"|\$\w"             # variable references
)


def group_independent(commands: list[str]) -> list[list[str]]:
    """Group commands into batches of independent commands.

    Commands within a batch can run in parallel. Batches must run
    sequentially because later batches may depend on earlier ones.

    Heuristic: a command is independent if it doesn't contain
    variable references, pipes, command substitution, or redirects
    that could create data dependencies with other commands.
    """
    if len(commands) <= 1:
        return [commands] if commands else []

    independent: list[str] = []
    sequential: list[str] = []

    files_touched: set[str] = set()

    for cmd in commands:
        has_deps = bool(_DEPENDENCY_MARKERS.search(cmd))

        words = cmd.split()
        writes_file = any(
            w in ("mv", "cp", "rm", "touch", "mkdir", "rmdir", ">", ">>", "tee")
            for w in words[:3]
        )

        if has_deps or writes_file:
            sequential.append(cmd)
        else:
            independent.append(cmd)

    batches: list[list[str]] = []
    if independent:
        batches.append(independent)
    for cmd in sequential:
        batches.append([cmd])

    return batches


def preview_and_execute_batch(
    commands: list[str],
    ctx: "SessionContext",
    *,
    dry_run: bool = False,
    auto_yes: bool = False,
    instruction: str = "",
) -> list[bool | None]:
    """Execute a list of commands, running independent ones in parallel.

    Returns a list of results (True/False/None) for each command.
    """
    if len(commands) <= 1:
        return [
            preview_and_execute(
                commands[0], ctx,
                dry_run=dry_run, auto_yes=auto_yes, instruction=instruction,
            )
        ] if commands else []

    batches = group_independent(commands)
    results: list[bool | None] = []

    for batch in batches:
        if len(batch) == 1:
            r = preview_and_execute(
                batch[0], ctx,
                dry_run=dry_run, auto_yes=auto_yes, instruction=instruction,
            )
            results.append(r)
        else:
            print(f"\n  {DIM}Running {len(batch)} independent commands in parallel…{RESET}")
            batch_results = _run_parallel(batch, ctx, dry_run=dry_run, auto_yes=auto_yes, instruction=instruction)
            results.extend(batch_results)

    return results


def _run_parallel(
    commands: list[str],
    ctx: "SessionContext",
    *,
    dry_run: bool = False,
    auto_yes: bool = False,
    instruction: str = "",
) -> list[bool | None]:
    """Run a batch of independent commands in parallel after preview."""
    approved: list[str] = []
    results: list[bool | None] = [None] * len(commands)

    for i, cmd in enumerate(commands):
        warnings = check_command(cmd)
        if warnings:
            r = preview_and_execute(cmd, ctx, dry_run=dry_run, auto_yes=auto_yes, instruction=instruction)
            results[i] = r
        elif dry_run:
            preview_and_execute(cmd, ctx, dry_run=True, instruction=instruction)
        elif auto_yes or should_auto_execute(cmd):
            approved.append((i, cmd))
        else:
            r = preview_and_execute(cmd, ctx, auto_yes=auto_yes, instruction=instruction)
            results[i] = r

    if not approved:
        return results

    with ThreadPoolExecutor(max_workers=min(len(approved), 4)) as pool:
        futures = {}
        for idx, cmd in approved:
            print(f"  {DIM}⟶ {cmd}{RESET}")
            f = pool.submit(_exec_single, cmd, ctx, instruction)
            futures[f] = idx

        for future in as_completed(futures):
            idx = futures[future]
            results[idx] = future.result()

    return results


def _exec_single(command: str, ctx: "SessionContext", instruction: str) -> bool:
    """Execute a single command (used by parallel runner)."""
    try:
        result = subprocess.run(
            command, shell=True, cwd=ctx.cwd,
            capture_output=True, text=True,
        )
        success = result.returncode == 0
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)

        status = f"{GREEN}✓{RESET}" if success else f"{RED}✗{RESET}"
        print(f"  {status} {DIM}{command}{RESET}")

        log_command(command, instruction=instruction, success=success)
        return success
    except Exception as e:
        print(f"  {RED}✗ {command}: {e}{RESET}")
        log_command(command, instruction=instruction, success=False)
        return False
