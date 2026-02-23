"""Command allow-list management.

Three tiers of trust determine whether a command runs without prompting:

1. **Built-in safe commands** — read-only / harmless commands that never
   need confirmation (ls, pwd, whoami, git status, etc.).
2. **User allow list** — commands or prefixes the user has permanently
   approved; persisted in ``~/.termai/allowed.json``.
3. **Session allow list** — commands approved for the current session only;
   lost when the process exits.

The executor calls ``should_auto_execute(cmd)`` before showing a prompt.
If it returns True the command runs immediately.
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path

from termai.config import CONFIG_DIR

ALLOWED_FILE = CONFIG_DIR / "allowed.json"
DISABLED_BUILTINS_FILE = CONFIG_DIR / "disabled_builtins.json"

# Default set of read-only / harmless commands.
# Users can disable individual entries via the settings UI;
# disabled entries are persisted in ``disabled_builtins.json``.
_DEFAULT_SAFE_PREFIXES: set[str] = {
    # filesystem inspection
    "ls", "ll", "la", "exa", "eza", "tree", "find", "locate",
    "stat", "file", "wc", "du", "df",
    # reading
    "cat", "head", "tail", "less", "more", "bat", "batcat",
    # text processing (read-only)
    "grep", "rg", "ripgrep", "ag", "ack", "sed", "awk",
    "sort", "uniq", "cut", "tr", "diff", "comm", "jq", "yq",
    # system info
    "pwd", "whoami", "id", "hostname", "uname", "uptime",
    "date", "cal", "env", "printenv", "echo", "printf",
    "which", "where", "type", "command",
    "top", "htop", "btop", "ps", "pgrep", "lsof", "free",
    "vmstat", "iostat", "nproc", "arch", "sw_vers",
    # network inspection
    "ping", "dig", "nslookup", "host", "traceroute", "mtr",
    "ifconfig", "ip", "ss", "netstat", "curl", "wget", "httpie",
    # git (read-only)
    "git status", "git log", "git diff", "git show", "git branch",
    "git tag", "git remote", "git stash list", "git shortlog",
    "git blame", "git ls-files", "git ls-tree",
    # package info
    "brew list", "brew info", "brew search",
    "pip list", "pip show", "pip freeze",
    "npm list", "npm ls", "npm info", "npm outdated",
    "cargo --version", "rustc --version", "go version",
    "node --version", "python --version", "java -version",
    # docker (read-only)
    "docker ps", "docker images", "docker stats",
    "docker logs", "docker inspect", "docker version",
    # misc
    "man", "tldr", "history",
}

# Session-scoped allow list (not persisted)
_session_allowed: set[str] = set()


def _get_active_safe_prefixes() -> set[str]:
    """Active safe prefixes = defaults minus user-disabled ones."""
    return _DEFAULT_SAFE_PREFIXES - _load_disabled_builtins()


def should_auto_execute(command: str) -> bool:
    """Return True if the command is safe to run without confirmation."""
    cmd_stripped = command.strip()

    if _is_builtin_safe(cmd_stripped):
        return True

    if _matches_allow_list(cmd_stripped, _session_allowed):
        return True

    if _matches_allow_list(cmd_stripped, _load_user_allowed()):
        return True

    return False


def add_to_session(command: str) -> None:
    """Allow a command (or its prefix) for the rest of this session."""
    key = _normalize(command)
    _session_allowed.add(key)


def add_to_permanent(command: str) -> None:
    """Persist a command (or its prefix) to the user allow list."""
    key = _normalize(command)
    allowed = _load_user_allowed()
    allowed.add(key)
    _save_user_allowed(allowed)


def get_permanent_list() -> set[str]:
    return _load_user_allowed()


def get_session_list() -> set[str]:
    return set(_session_allowed)


def remove_from_permanent(command: str) -> bool:
    key = _normalize(command)
    allowed = _load_user_allowed()
    if key in allowed:
        allowed.discard(key)
        _save_user_allowed(allowed)
        return True
    return False


def get_safe_commands() -> dict[str, bool]:
    """Return all default safe prefixes with their enabled state."""
    disabled = _load_disabled_builtins()
    return {cmd: cmd not in disabled for cmd in sorted(_DEFAULT_SAFE_PREFIXES)}


def disable_safe_command(command: str) -> None:
    """Disable a built-in safe command (it will require confirmation)."""
    disabled = _load_disabled_builtins()
    disabled.add(command)
    _save_disabled_builtins(disabled)


def enable_safe_command(command: str) -> None:
    """Re-enable a previously disabled built-in safe command."""
    disabled = _load_disabled_builtins()
    disabled.discard(command)
    _save_disabled_builtins(disabled)


# -- Internals ----------------------------------------------------------------

def _normalize(command: str) -> str:
    """Extract the meaningful prefix of a command for matching.

    For simple commands we store the full command.
    For commands with arguments, we store the binary + first subcommand
    (e.g. ``git commit`` from ``git commit -m "msg"``).
    """
    parts = shlex.split(command.strip())
    if not parts:
        return command.strip()
    # Keep up to 2 tokens (e.g. "git commit", "docker build")
    return " ".join(parts[:2])


def _is_builtin_safe(command: str) -> bool:
    """Check if the command matches any active built-in safe prefix."""
    cmd_lower = command.lower()
    for prefix in _get_active_safe_prefixes():
        if cmd_lower == prefix or cmd_lower.startswith(prefix + " "):
            return True
    return False


def _matches_allow_list(command: str, allowed: set[str]) -> bool:
    """Check if the command matches any entry in an allow list."""
    cmd_lower = command.lower().strip()
    for entry in allowed:
        entry_lower = entry.lower()
        if cmd_lower == entry_lower or cmd_lower.startswith(entry_lower + " "):
            return True
    return False


def _load_user_allowed() -> set[str]:
    if not ALLOWED_FILE.exists():
        return set()
    try:
        data = json.loads(ALLOWED_FILE.read_text())
        return set(data) if isinstance(data, list) else set()
    except (json.JSONDecodeError, OSError):
        return set()


def _save_user_allowed(allowed: set[str]) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        ALLOWED_FILE.write_text(json.dumps(sorted(allowed), indent=2) + "\n")
    except OSError:
        pass


def _load_disabled_builtins() -> set[str]:
    if not DISABLED_BUILTINS_FILE.exists():
        return set()
    try:
        data = json.loads(DISABLED_BUILTINS_FILE.read_text())
        return set(data) if isinstance(data, list) else set()
    except (json.JSONDecodeError, OSError):
        return set()


def _save_disabled_builtins(disabled: set[str]) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        DISABLED_BUILTINS_FILE.write_text(json.dumps(sorted(disabled), indent=2) + "\n")
    except OSError:
        pass
