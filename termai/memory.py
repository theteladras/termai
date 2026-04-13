"""Few-shot learning from command history.

Mines the global history for successful instruction→command pairs and
finds similar past interactions to include as examples in the AI prompt.
This teaches the local model patterns from its own past successes,
making it progressively smarter without additional training.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from termai.logger import LOG_FILE

_STOP_WORDS = frozenset({
    "a", "an", "the", "in", "on", "at", "to", "for", "of", "is", "it",
    "my", "me", "i", "do", "and", "or", "if", "with", "from", "that",
    "this", "all", "are", "be", "has", "have", "was", "were", "what",
    "how", "can", "could", "please", "just",
})


def _tokenize(text: str) -> set[str]:
    """Extract meaningful words from an instruction."""
    words = set(re.findall(r"[a-z0-9]+", text.lower()))
    return words - _STOP_WORDS


def _similarity(a: set[str], b: set[str]) -> float:
    """Jaccard similarity between two word sets."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def find_similar_examples(
    instruction: str,
    *,
    max_examples: int = 5,
    min_similarity: float = 0.3,
) -> list[dict[str, str]]:
    """Find past successful commands for similar instructions.

    Returns a list of {"instruction": ..., "command": ...} dicts,
    sorted by similarity (most similar first).
    """
    if not LOG_FILE.exists():
        return []

    target_tokens = _tokenize(instruction)
    if not target_tokens:
        return []

    candidates: list[tuple[float, str, str]] = []
    seen_commands: set[str] = set()

    try:
        for line in LOG_FILE.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if not entry.get("success"):
                continue
            past_instruction = entry.get("instruction", "")
            past_command = entry.get("command", "")
            if not past_instruction or not past_command:
                continue

            if past_instruction.lower().strip() == instruction.lower().strip():
                continue

            if past_command in seen_commands:
                continue

            past_tokens = _tokenize(past_instruction)
            sim = _similarity(target_tokens, past_tokens)

            if sim >= min_similarity:
                candidates.append((sim, past_instruction, past_command))
                seen_commands.add(past_command)
    except OSError:
        return []

    candidates.sort(key=lambda x: x[0], reverse=True)

    return [
        {"instruction": inst, "command": cmd}
        for _, inst, cmd in candidates[:max_examples]
    ]


def format_examples_for_prompt(examples: list[dict[str, str]]) -> str:
    """Format similar examples as few-shot context for the AI prompt."""
    if not examples:
        return ""

    lines = ["Similar commands you've successfully run before:"]
    for ex in examples:
        lines.append(f"  \"{ex['instruction']}\" → {ex['command']}")
    lines.append("Use these as reference patterns when generating the command.")
    return "\n".join(lines)
