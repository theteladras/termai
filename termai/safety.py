"""Safety checks for generated commands.

Detects potentially destructive operations (file deletion, disk writes,
system control, permission changes, etc.) and returns human-readable
warnings so the user can make an informed decision.

Uses regex patterns for precise matching — avoids false positives like
flagging `rm -rf /tmp/cache` as "will destroy your system".
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Each rule: (compiled regex, severity, reason).
# Patterns are matched against the full command string (case-insensitive).
# Use word boundaries (\b) and anchoring to avoid false positives.
_RULES: list[tuple[re.Pattern, str, str]] = [
    # ── File / directory deletion ──────────────────────────────────────
    (re.compile(r"\brm\s+(-\w*f\w*\s+)*-\w*r\w*\s+/\s*$|"
                r"\brm\s+(-\w*r\w*\s+)*-\w*f\w*\s+/\s*$", re.I),
     "critical", "Recursive delete from root — will destroy your system"),
    (re.compile(r"\brm\s+.*-r.*-f|\brm\s+.*-f.*-r|\brm\s+-rf\b", re.I),
     "high", "Recursive forced delete"),
    (re.compile(r"\brm\s+.*-r\b", re.I),
     "high", "Recursive delete"),
    (re.compile(r"\brm\s", re.I),
     "medium", "File deletion"),
    (re.compile(r"\brmdir\b", re.I),
     "medium", "Directory removal"),
    (re.compile(r"\bfind\b.*-delete\b", re.I),
     "high", "Bulk file deletion via find"),
    (re.compile(r"\bfind\b.*-exec\s+rm\b", re.I),
     "high", "Bulk file deletion via find -exec"),
    (re.compile(r"\bxargs\s+rm\b", re.I),
     "high", "Piped mass file deletion"),

    # ── Disk / filesystem ──────────────────────────────────────────────
    (re.compile(r"\bmkfs\b", re.I),
     "critical", "Filesystem format — will erase a disk"),
    (re.compile(r"\bdd\s", re.I),
     "critical", "Low-level disk write"),
    (re.compile(r">\s*/dev/sd|>\s*/dev/nvm|>\s*/dev/disk", re.I),
     "critical", "Direct write to block device"),
    (re.compile(r"\bfdisk\b", re.I),
     "critical", "Disk partitioning"),
    (re.compile(r"\bparted\b", re.I),
     "critical", "Disk partitioning"),
    (re.compile(r"\bwipefs\b", re.I),
     "critical", "Wiping filesystem signatures"),
    (re.compile(r"\bdiskutil\s+(erase|partitionDisk|eraseDisk)\b", re.I),
     "critical", "macOS disk operation — data loss"),
    (re.compile(r"cat\s+/dev/(urandom|zero)\s*>", re.I),
     "critical", "Overwriting with random/zero data"),

    # ── Permissions / ownership ────────────────────────────────────────
    (re.compile(r"\bchmod\s+-R\s+0?777\b", re.I),
     "high", "Recursive world-writable permissions"),
    (re.compile(r"\bchmod\s+0?777\b", re.I),
     "medium", "World-writable permissions"),
    (re.compile(r"\bchmod\s+(-R\s+)?0?000\b", re.I),
     "high", "Removing all file permissions"),
    (re.compile(r"\bchown\s+-R\b", re.I),
     "medium", "Recursive ownership change"),

    # ── System control ─────────────────────────────────────────────────
    (re.compile(r"\bshutdown\b", re.I),
     "high", "System shutdown"),
    (re.compile(r"\breboot\b", re.I),
     "high", "System reboot"),
    (re.compile(r"\bpoweroff\b", re.I),
     "high", "System poweroff"),
    (re.compile(r"\binit\s+0\b", re.I),
     "high", "System halt"),
    (re.compile(r"\bhalt\b", re.I),
     "high", "System halt"),
    (re.compile(r"\bsystemctl\s+(stop|disable|mask)\b", re.I),
     "medium", "Stopping/disabling a system service"),
    (re.compile(r"\blaunchctl\s+(unload|remove)\b", re.I),
     "medium", "Removing a macOS service"),

    # ── Process management ─────────────────────────────────────────────
    (re.compile(r"\bkill\s+-9\b", re.I),
     "medium", "Force-killing a process"),
    (re.compile(r"\bkillall\b", re.I),
     "medium", "Killing processes by name"),
    (re.compile(r"\bpkill\b", re.I),
     "medium", "Killing processes by pattern"),

    # ── Privilege escalation ───────────────────────────────────────────
    (re.compile(r"\bsudo\b", re.I),
     "medium", "Running with elevated privileges (sudo)"),

    # ── Dangerous moves / overwrites ───────────────────────────────────
    (re.compile(r"\bmv\s+/\s", re.I),
     "high", "Moving from root filesystem"),
    (re.compile(r">\s*/etc/", re.I),
     "high", "Overwriting system config"),
    (re.compile(r"\btruncate\b", re.I),
     "medium", "Truncating a file"),
    (re.compile(r"\bshred\b", re.I),
     "high", "Securely erasing a file (unrecoverable)"),

    # ── Remote script execution ────────────────────────────────────────
    (re.compile(r"\bcurl\b.*\|\s*(ba)?sh\b", re.I),
     "high", "Piping remote script to shell"),
    (re.compile(r"\bwget\b.*\|\s*(ba)?sh\b", re.I),
     "high", "Piping remote script to shell"),
    (re.compile(r"\bcurl\b.*\|\s*sudo\b", re.I),
     "critical", "Piping remote script to sudo"),
    (re.compile(r"\bwget\b.*\|\s*sudo\b", re.I),
     "critical", "Piping remote script to sudo"),

    # ── Git destructive operations ─────────────────────────────────────
    (re.compile(r"\bgit\s+push\s+.*--force\b|\bgit\s+push\s+-f\b", re.I),
     "high", "Force-pushing — can destroy remote history"),
    (re.compile(r"\bgit\s+reset\s+--hard\b", re.I),
     "high", "Hard reset — discards uncommitted changes"),
    (re.compile(r"\bgit\s+clean\s+.*-f", re.I),
     "medium", "Removing untracked files"),

    # ── Cron / scheduled tasks ─────────────────────────────────────────
    (re.compile(r"\bcrontab\s+-r\b", re.I),
     "high", "Deleting all cron jobs"),

    # ── Firewall / network ─────────────────────────────────────────────
    (re.compile(r"\biptables\s+-F\b", re.I),
     "high", "Flushing all firewall rules"),
    (re.compile(r"\bufw\s+disable\b", re.I),
     "high", "Disabling firewall"),

    # ── Docker cleanup ─────────────────────────────────────────────────
    (re.compile(r"\bdocker\s+system\s+prune\b", re.I),
     "medium", "Removing unused Docker data"),
    (re.compile(r"\bdocker\s+rm\b", re.I),
     "medium", "Removing Docker containers"),
    (re.compile(r"\bdocker\s+rmi\b", re.I),
     "medium", "Removing Docker images"),

    # ── Sync with deletion ─────────────────────────────────────────────
    (re.compile(r"\brsync\b.*--delete\b", re.I),
     "medium", "Syncing with file deletion at destination"),

    # ── Environment sabotage ───────────────────────────────────────────
    (re.compile(r"\bexport\s+PATH\s*=\s*$|\bexport\s+PATH\s*=\s*['\"]?\s*['\"]?\s*$", re.I),
     "high", "Clearing PATH — will break the shell"),
    (re.compile(r"\bunset\s+PATH\b", re.I),
     "high", "Unsetting PATH — will break the shell"),

    # ── Fork bomb ──────────────────────────────────────────────────────
    (re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:"),
     "critical", "Fork bomb"),

    # ── Windows (cross-platform builds) ────────────────────────────────
    (re.compile(r"\bformat\s+[a-z]:", re.I),
     "critical", "Disk format (Windows)"),
    (re.compile(r"\bdel\s+/s\b", re.I),
     "high", "Recursive file deletion (Windows)"),
    (re.compile(r"\brd\s+/s\b", re.I),
     "high", "Recursive directory removal (Windows)"),
]


@dataclass(frozen=True)
class SafetyWarning:
    severity: str   # "medium", "high", or "critical"
    reason: str


def check_command(command: str) -> list[SafetyWarning]:
    """Return a list of safety warnings for the given command.

    An empty list means no known dangerous patterns were detected.
    """
    cmd = command.strip()
    warnings: list[SafetyWarning] = []
    seen_reasons: set[str] = set()

    for pattern, severity, reason in _RULES:
        if pattern.search(cmd) and reason not in seen_reasons:
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
