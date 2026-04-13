"""Per-terminal session persistence.

Each terminal window gets its own interaction history so that sequential
commands can reference prior context (e.g. "create a dir" followed by
"put files in it").  The terminal is identified by its TTY device path,
which stays stable across multiple termai invocations in the same window.

History is stored as JSONL files under ~/.termai/sessions/.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

SESSION_DIR = Path.home() / ".termai" / "sessions"
MAX_HISTORY = 20
STALE_HOURS = 24


@dataclass
class Interaction:
    instruction: str
    command: str
    success: bool | None = None
    timestamp: float = field(default_factory=time.time)


def _get_terminal_id() -> str:
    """Return a stable identifier for the current terminal.

    Uses the TTY device path on Unix (e.g. /dev/ttys003).
    Falls back to parent PID if TTY is not available (e.g. piped input).
    """
    try:
        tty = os.ttyname(sys.stdin.fileno())
        return hashlib.sha256(tty.encode()).hexdigest()[:16]
    except (OSError, AttributeError):
        pass

    ppid = os.getppid()
    return hashlib.sha256(f"ppid-{ppid}".encode()).hexdigest()[:16]


def _session_file() -> Path:
    return SESSION_DIR / f"{_get_terminal_id()}.jsonl"


def load_history(limit: int = MAX_HISTORY) -> list[Interaction]:
    """Load recent interactions for the current terminal."""
    path = _session_file()
    if not path.exists():
        return []

    entries: list[Interaction] = []
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                entries.append(Interaction(
                    instruction=data["instruction"],
                    command=data["command"],
                    success=data.get("success"),
                    timestamp=data.get("timestamp", 0),
                ))
            except (json.JSONDecodeError, KeyError):
                continue
    except OSError:
        return []

    return entries[-limit:]


def save_interaction(instruction: str, command: str, success: bool | None = None) -> None:
    """Append an interaction to the current terminal's history."""
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "instruction": instruction,
        "command": command,
        "success": success,
        "timestamp": time.time(),
    }
    try:
        with open(_session_file(), "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass

    _trim_file()


def _trim_file() -> None:
    """Keep only the most recent MAX_HISTORY entries."""
    path = _session_file()
    try:
        lines = path.read_text().splitlines()
        if len(lines) > MAX_HISTORY * 2:
            path.write_text("\n".join(lines[-MAX_HISTORY:]) + "\n")
    except OSError:
        pass


def cleanup_stale_sessions() -> None:
    """Remove session files older than STALE_HOURS."""
    if not SESSION_DIR.exists():
        return
    cutoff = time.time() - (STALE_HOURS * 3600)
    try:
        for f in SESSION_DIR.iterdir():
            if f.suffix == ".jsonl" and f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
    except OSError:
        pass


def find_cached_command(instruction: str) -> str | None:
    """Look up a previously successful command for a similar instruction.

    Returns the cached command if found, or None. Only returns results
    that succeeded and are from the same terminal session.
    """
    lower = instruction.lower().strip()
    if not lower:
        return None

    history = load_history()
    for ix in reversed(history):
        if ix.success and ix.instruction.lower().strip() == lower:
            return ix.command

    return None


def format_history_for_prompt(interactions: list[Interaction], current_instruction: str = "") -> str:
    """Format recent interactions as context for the AI prompt.

    Deduplicates repeated entries for the same instruction and excludes
    the current instruction to avoid the AI copying a prior (possibly
    wrong) result.
    """
    if not interactions:
        return ""

    current_lower = current_instruction.lower().strip()
    seen: set[str] = set()
    unique: list[Interaction] = []

    for ix in interactions:
        if current_lower and ix.instruction.lower().strip() == current_lower:
            continue
        key = ix.instruction.lower().strip()
        if key in seen:
            continue
        seen.add(key)
        unique.append(ix)

    if not unique:
        return ""

    lines = ["Recent interactions in this terminal:"]
    for ix in unique[-10:]:
        status = "✓" if ix.success else ("✗" if ix.success is False else "?")
        lines.append(f"  [{status}] \"{ix.instruction}\" → {ix.command}")
    return "\n".join(lines)
