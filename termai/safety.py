"""Safety checks for generated commands.

Detects potentially destructive operations (file deletion, disk writes,
system control, permission changes, etc.) and returns human-readable
warnings so the user can make an informed decision.
"""

from __future__ import annotations

from dataclasses import dataclass

# Each rule maps a pattern (matched case-insensitively against the full
# command string) to a severity level and a short reason shown to the user.
_RULES: list[tuple[str, str, str]] = [
    # pattern, severity, reason
    ("rm -rf /",    "critical", "Recursive delete from root — will destroy your system"),
    ("rm -rf",      "high",     "Recursive forced delete"),
    ("rm -r",       "high",     "Recursive delete"),
    ("rm ",         "medium",   "File deletion"),
    ("rmdir",       "medium",   "Directory removal"),
    ("mkfs",        "critical", "Filesystem format — will erase a disk"),
    ("dd ",         "critical", "Low-level disk write"),
    ("> /dev/sd",   "critical", "Direct write to block device"),
    ("> /dev/nvm",  "critical", "Direct write to block device"),
    ("chmod -R 777","high",     "Recursive world-writable permissions"),
    ("chmod 777",   "medium",   "World-writable permissions"),
    ("chown -R",    "medium",   "Recursive ownership change"),
    (":(){ :|:& };:","critical","Fork bomb"),
    ("shutdown",    "high",     "System shutdown"),
    ("reboot",      "high",     "System reboot"),
    ("init 0",      "high",     "System halt"),
    ("halt",        "high",     "System halt"),
    ("systemctl stop","medium", "Stopping a system service"),
    ("kill -9",     "medium",   "Force-killing a process"),
    ("killall",     "medium",   "Killing processes by name"),
    ("mv /",        "high",     "Moving from root filesystem"),
    ("curl | sh",   "high",     "Piping remote script to shell"),
    ("curl | bash", "high",     "Piping remote script to shell"),
    ("wget -O - |", "high",     "Piping remote script to shell"),
    ("> /etc/",     "high",     "Overwriting system config"),
    ("truncate",    "medium",   "Truncating a file"),
    ("shred",       "high",     "Securely erasing a file (unrecoverable)"),
]


@dataclass(frozen=True)
class SafetyWarning:
    severity: str   # "medium", "high", or "critical"
    reason: str


def check_command(command: str) -> list[SafetyWarning]:
    """Return a list of safety warnings for the given command.

    An empty list means no known dangerous patterns were detected.
    """
    cmd_lower = command.lower().strip()
    warnings: list[SafetyWarning] = []
    seen_reasons: set[str] = set()

    for pattern, severity, reason in _RULES:
        if pattern in cmd_lower and reason not in seen_reasons:
            warnings.append(SafetyWarning(severity=severity, reason=reason))
            seen_reasons.add(reason)

    return warnings


def is_destructive(command: str) -> bool:
    """Convenience check — True if *any* warning is found."""
    return bool(check_command(command))


def format_warnings(warnings: list[SafetyWarning]) -> str:
    """Render warnings as a colored, human-readable block."""
    severity_colors = {
        "critical": "\033[1;31m",  # bold red
        "high":     "\033[0;31m",  # red
        "medium":   "\033[0;33m",  # yellow
    }
    reset = "\033[0m"

    lines = ["  \033[1;31m⚠  Safety warnings:\033[0m"]
    for w in warnings:
        color = severity_colors.get(w.severity, "")
        tag = w.severity.upper()
        lines.append(f"     {color}[{tag}]{reset} {w.reason}")
    return "\n".join(lines)
