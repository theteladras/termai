"""Session context management.

Tracks cwd, environment, command history, user preferences, and system
details across a single termai session.  This context is fed into every
AI prompt so the model can generate accurate, platform-specific commands.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


def _detect_distro() -> str:
    """Best-effort Linux distro detection; empty string on other OSes."""
    try:
        import distro  # type: ignore[import-untyped]
        return distro.name(pretty=True)
    except Exception:
        pass
    release = Path("/etc/os-release")
    if release.exists():
        for line in release.read_text().splitlines():
            if line.startswith("PRETTY_NAME="):
                return line.split("=", 1)[1].strip('"')
    return ""


def _detect_package_manager() -> str:
    """Return the name of the first package manager found on PATH."""
    for pm in ("brew", "apt", "dnf", "yum", "pacman", "zypper", "apk", "nix"):
        if shutil.which(pm):
            return pm
    return "unknown"


def _git_branch() -> str:
    """Return the current git branch, or empty string if not in a repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""


@dataclass
class SessionContext:
    """Rich snapshot of the user's current terminal environment."""

    cwd: str = field(default_factory=os.getcwd)
    shell: str = field(default_factory=lambda: os.environ.get("SHELL", "unknown"))
    os_name: str = field(default_factory=platform.system)
    os_version: str = field(default_factory=platform.release)
    arch: str = field(default_factory=platform.machine)
    distro: str = field(default_factory=_detect_distro)
    package_manager: str = field(default_factory=_detect_package_manager)
    username: str = field(default_factory=lambda: os.environ.get("USER", "unknown"))
    home: str = field(default_factory=lambda: str(Path.home()))
    git_branch: str = field(default_factory=_git_branch)
    history: list[str] = field(default_factory=list)
    env_snapshot: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Capture a curated subset of environment variables (avoids leaking secrets).
        safe_keys = {
            "PATH", "LANG", "LC_ALL", "TERM", "EDITOR", "VISUAL",
            "VIRTUAL_ENV", "CONDA_DEFAULT_ENV", "DOCKER_HOST",
            "GOPATH", "CARGO_HOME", "NODE_PATH",
        }
        self.env_snapshot = {
            k: v for k, v in os.environ.items() if k in safe_keys
        }

    # -- mutation helpers -----------------------------------------------------

    def record(self, command: str) -> None:
        """Append a command to the session history."""
        self.history.append(command)

    def refresh_cwd(self) -> None:
        """Re-read the current working directory (useful after cd)."""
        self.cwd = os.getcwd()
        self.git_branch = _git_branch()

    # -- prompt generation ----------------------------------------------------

    def summary(self) -> str:
        """One-paragraph context string for inclusion in the AI prompt."""
        parts = [
            f"OS: {self.os_name} {self.os_version} ({self.arch})",
            f"Shell: {self.shell}",
            f"CWD: {self.cwd}",
            f"User: {self.username}",
            f"Package manager: {self.package_manager}",
        ]
        if self.distro:
            parts.append(f"Distro: {self.distro}")
        if self.git_branch:
            parts.append(f"Git branch: {self.git_branch}")
        if self.env_snapshot.get("VIRTUAL_ENV"):
            parts.append(f"Python venv: {self.env_snapshot['VIRTUAL_ENV']}")
        if self.env_snapshot.get("CONDA_DEFAULT_ENV"):
            parts.append(f"Conda env: {self.env_snapshot['CONDA_DEFAULT_ENV']}")

        recent = self.history[-5:] if self.history else ["(none)"]
        parts.append(f"Recent commands: {'; '.join(recent)}")
        return "\n".join(parts)

    def as_system_prompt(self) -> str:
        """Full system prompt fed to the LLM before each generation."""
        return (
            "You are termai, a local AI terminal assistant. "
            "Given the user's natural language instruction and the system context below, "
            "generate a single shell command (or a short pipeline) that accomplishes the task.\n"
            "\n"
            "Rules:\n"
            "1. Output ONLY the command — no explanation, no markdown fences.\n"
            "2. Use commands available on the user's OS and shell.\n"
            "3. Prefer safe, non-destructive approaches when possible.\n"
            "4. If the task is ambiguous, pick the most common interpretation.\n"
            "5. Never fabricate flags or options — use only real ones.\n"
            "\n"
            "--- System Context ---\n"
            f"{self.summary()}\n"
            "--- End Context ---"
        )
