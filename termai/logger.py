"""Command logging for auditing and learning context.

Stores every executed command as a JSON-lines entry in ~/.termai/history.jsonl.
Each entry records the timestamp, original instruction, generated command,
working directory, and success status.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

CYAN = "\033[1;36m"
GREEN = "\033[1;32m"
RED = "\033[1;31m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"

LOG_DIR = Path.home() / ".termai"
LOG_FILE = LOG_DIR / "history.jsonl"


def _ensure_log_dir() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def log_command(
    command: str,
    instruction: str = "",
    success: bool | None = None,
) -> None:
    """Append a command entry to the history log (best-effort)."""
    try:
        _ensure_log_dir()
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "instruction": instruction,
            "command": command,
            "cwd": os.getcwd(),
            "success": success,
        }
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def read_history(limit: int = 20) -> list[dict]:
    """Return the most recent *limit* log entries."""
    if not LOG_FILE.exists():
        return []
    with open(LOG_FILE) as f:
        lines = f.readlines()
    entries = [json.loads(line) for line in lines if line.strip()]
    return entries[-limit:]


def print_history(limit: int = 20) -> None:
    """Pretty-print the recent command history to stdout."""
    entries = read_history(limit)

    if not entries:
        print(f"  {DIM}No command history found.{RESET}")
        print(f"  {DIM}History is stored in {LOG_FILE}{RESET}")
        return

    print(f"\n  {BOLD}Recent command history{RESET} ({len(entries)} entries)\n")

    for i, entry in enumerate(entries, 1):
        ts = entry.get("timestamp", "?")[:19].replace("T", " ")
        cmd = entry.get("command", "?")
        instruction = entry.get("instruction", "")
        success = entry.get("success")
        cwd = entry.get("cwd", "")

        status = f"{GREEN}✓{RESET}" if success else f"{RED}✗{RESET}" if success is False else f"{DIM}?{RESET}"

        print(f"  {DIM}{i:3d}.{RESET} {status}  {cmd}")
        if instruction:
            print(f"       {DIM}Instruction: {instruction}{RESET}")
        print(f"       {DIM}{ts}  {cwd}{RESET}")
        print()
