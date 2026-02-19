"""Command generation from natural language instructions.

Uses a local LLM to convert user intent into shell commands.  Falls back
to a simple keyword-based mapper when the model is unavailable so the
tool stays functional even without AI.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from termai.model import LocalModel

if TYPE_CHECKING:
    from termai.context import SessionContext

_model: LocalModel | None = None


def _get_model() -> LocalModel:
    global _model
    if _model is None:
        _model = LocalModel()
    return _model


def generate_command(instruction: str, ctx: "SessionContext") -> str | None:
    """Convert a natural language instruction into a shell command."""
    model = _get_model()

    if model.is_available:
        return _generate_with_llm(instruction, ctx, model)

    return _generate_fallback(instruction, ctx)


def _generate_with_llm(
    instruction: str,
    ctx: "SessionContext",
    model: LocalModel,
) -> str | None:
    """Use the local LLM to produce a shell command."""
    system_prompt = ctx.as_system_prompt()
    user_prompt = f"Instruction: {instruction}"

    raw = model.generate(system_prompt, user_prompt, max_tokens=256)
    if not raw:
        print("[termai] Model returned empty response — falling back.")
        return _generate_fallback(instruction, ctx)

    command = _clean_model_output(raw)
    return command or _generate_fallback(instruction, ctx)


def _clean_model_output(raw: str) -> str:
    """Strip markdown fences, leading $, and excess whitespace."""
    text = raw.strip()

    fence_pattern = re.compile(r"^```(?:bash|sh|zsh)?\s*\n?(.*?)\n?```$", re.DOTALL)
    m = fence_pattern.match(text)
    if m:
        text = m.group(1).strip()

    if text.startswith("$ "):
        text = text[2:]

    lines = [ln for ln in text.splitlines() if not ln.startswith("#")]
    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# Rule-based fallback (no AI required)
# ---------------------------------------------------------------------------

_FALLBACK_MAP: list[tuple[list[str], str]] = [
    (["list", "files"],            "ls -la"),
    (["list", "directory"],        "ls -la"),
    (["disk", "usage"],            "df -h"),
    (["disk", "space"],            "du -sh *"),
    (["memory", "usage"],          "free -h" if __import__("platform").system() == "Linux" else "vm_stat"),
    (["current", "directory"],     "pwd"),
    (["network", "interfaces"],    "ifconfig" if __import__("platform").system() == "Darwin" else "ip addr"),
    (["running", "processes"],     "ps aux"),
    (["system", "info"],           "uname -a"),
    (["find", "python", "files"],  'find . -name "*.py" -type f'),
    (["find", "log", "files"],     'find . -name "*.log" -type f'),
    (["count", "lines"],           "wc -l"),
    (["git", "status"],            "git status"),
    (["git", "log"],               "git log --oneline -10"),
    (["docker", "containers"],     "docker ps -a"),
    (["docker", "images"],         "docker images"),
]


def _generate_fallback(instruction: str, ctx: "SessionContext") -> str:
    """Keyword-matching fallback when no AI model is loaded."""
    words = instruction.lower().split()
    best_match = ""
    best_score = 0

    for keywords, cmd in _FALLBACK_MAP:
        score = sum(1 for kw in keywords if kw in words)
        if score > best_score:
            best_score = score
            best_match = cmd

    if best_match:
        print("[termai] (using rule-based fallback)")
        return best_match

    print("[termai] Could not generate a command. Try rephrasing or install a local model.")
    return None  # type: ignore[return-value]
