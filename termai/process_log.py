"""Process-level logging for multi-step orchestrated tasks.

Each process entry captures the full lifecycle of a user request:
prompt -> AI plan -> individual step results, including which AI
provider was used, timing, and final status.

Stored in ~/.termai/processes.jsonl alongside the simpler command history.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

CYAN = "\033[1;36m"
GREEN = "\033[1;32m"
YELLOW = "\033[0;33m"
RED = "\033[1;31m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

LOG_DIR = Path.home() / ".termai"
PROCESS_LOG = LOG_DIR / "processes.jsonl"


def log_process(plan) -> None:
    """Append a completed plan to the process log (best-effort)."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **plan.to_dict(),
        }
        with open(PROCESS_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def read_processes(limit: int = 20) -> list[dict]:
    """Return the most recent *limit* process entries (newest last)."""
    if not PROCESS_LOG.exists():
        return []
    with open(PROCESS_LOG) as f:
        lines = f.readlines()
    entries = [json.loads(line) for line in lines if line.strip()]
    return entries[-limit:]


def clear_processes() -> None:
    """Delete the process log file."""
    if PROCESS_LOG.exists():
        PROCESS_LOG.unlink()


def print_processes(limit: int = 20) -> None:
    """Pretty-print recent processes to stdout."""
    entries = read_processes(limit)

    if not entries:
        print(f"  {DIM}No process history found.{RESET}")
        print(f"  {DIM}Multi-step processes are logged in {PROCESS_LOG}{RESET}")
        return

    print(f"\n  {BOLD}Recent processes{RESET} ({len(entries)} entries)\n")

    for entry in reversed(entries):
        ts = entry.get("timestamp", "?")[:19].replace("T", " ")
        instruction = entry.get("instruction", "?")
        ai = entry.get("ai_provider", "?")
        status = entry.get("status", "?")
        steps = entry.get("steps", [])
        duration = entry.get("total_duration_ms")
        pid = entry.get("id", "?")

        status_color = GREEN if status == "completed" else (
            YELLOW if status == "partial" else RED)
        status_icon = "✓" if status == "completed" else (
            "◐" if status == "partial" else "✗")

        dur_str = ""
        if duration is not None:
            dur_str = f" ({duration / 1000:.1f}s)" if duration >= 1000 else f" ({duration}ms)"

        succeeded = sum(1 for s in steps if s.get("status") == "success")
        total = len(steps)

        print(f"  {status_color}{status_icon}{RESET}  {BOLD}{instruction}{RESET}")
        print(f"     {DIM}{ts} • {ai} • {succeeded}/{total} steps{dur_str} • [{pid}]{RESET}")

        for s in steps:
            s_status = s.get("status", "?")
            s_icon = f"{GREEN}✓{RESET}" if s_status == "success" else (
                f"{RED}✗{RESET}" if s_status == "failed" else (
                    f"{YELLOW}⊘{RESET}" if s_status == "skipped" else f"{DIM}?{RESET}"))
            s_dur = ""
            if s.get("duration_ms") is not None:
                ms = s["duration_ms"]
                s_dur = f" ({ms / 1000:.1f}s)" if ms >= 1000 else f" ({ms}ms)"
            desc = f" — {s['description']}" if s.get("description") else ""
            print(f"       {s_icon} {DIM}{s.get('id', '?')}. {s.get('command', '?')}{desc}{s_dur}{RESET}")

        print()
