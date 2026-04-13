"""Command generation from natural language instructions.

Uses a local LLM to convert user intent into shell commands.  Falls back
to a simple keyword-based mapper when the model is unavailable so the
tool stays functional even without AI.

When a remote AI provider (OpenAI/Claude) is configured, the local model
generates first, then a complexity classifier decides whether to delegate
to the remote provider for higher-quality results.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from termai.model import LocalModel

if TYPE_CHECKING:
    from termai.context import SessionContext

CYAN = "\033[1;36m"
DIM = "\033[2m"
YELLOW = "\033[0;33m"
RESET = "\033[0m"

_GREETING_RE = re.compile(
    r"^(hi|hello|hey|sup|yo|good morning|good evening|good afternoon"
    r"|thanks|thank you|bye|goodbye)\s*[.!?]?\s*$",
    re.IGNORECASE,
)

_CLASSIFY_SYSTEM = (
    "You are an intent classifier for a terminal command-line assistant called termai. "
    "Users type text that is EITHER:\n"
    "- COMMAND: anything that can be answered by running a shell command. This includes "
    "questions phrased naturally like 'what is my location' (pwd), 'who am i' (whoami), "
    "'what time is it' (date), 'how much disk space' (df), 'what is my ip' (curl), "
    "'do i have a tmp dir' (ls), 'what files are here' (ls). "
    "If it CAN be answered by running a terminal command, it is COMMAND.\n"
    "- CHAT: greetings, philosophical questions, concept explanations, chitchat — "
    "things that have NO possible shell command answer. Examples: 'what is the meaning "
    "of life', 'why is the sky blue', 'explain python decorators', 'who are you', "
    "'how are you'.\n"
    "Reply with exactly one word: COMMAND or CHAT. Nothing else."
)


def _classify_intent(instruction: str, model: LocalModel) -> str:
    """Classify input as 'command' or 'chat' using AI-first approach.

    Layer 1 — regex (instant, zero cost):
      Only obvious standalone greetings are caught without AI.
    Layer 2 — local AI (primary classifier):
      Everything else is sent to the local model for classification.
      The AI understands terminal context and can distinguish
      'who am i' (whoami) from 'who are you' (chat).
    Fallback:
      If no model is available, default to 'command' so the user
      isn't blocked.
    """
    text = instruction.strip()

    if _GREETING_RE.search(text):
        return "chat"

    if model.is_available:
        raw = model.generate(_CLASSIFY_SYSTEM, f"Input: {text}", max_tokens=10)
        token = raw.strip().upper()
        if "CHAT" in token:
            return "chat"
        return "command"

    return "command"

_model: LocalModel | None = None
_force_mode: str | None = None  # "remote", "local", or None (auto)


def set_force_mode(mode: str | None) -> None:
    """Override delegation: 'remote', 'local', or None for auto."""
    global _force_mode
    _force_mode = mode


def _get_model() -> LocalModel:
    global _model
    if _model is None:
        _model = LocalModel()
    return _model


def generate_command(instruction: str, ctx: "SessionContext") -> str | None:
    """Convert a natural language instruction into a shell command.

    Flow:
    0. Check session cache for a previously successful command
    1. Detect conversational input and redirect to --chat
    2. Try local generation (LLM or keyword fallback)
    3. If remote AI is configured, classify complexity
    4. Delegate to remote if complex; fall back to local on remote failure
    """
    from termai.session import find_cached_command
    cached = find_cached_command(instruction)
    if cached:
        print(f"  {DIM}(cached){RESET}")
        return cached

    model = _get_model()

    intent = _classify_intent(instruction, model)
    if intent == "chat":
        print(f"\n  {CYAN}[termai]{RESET} That looks like a question, not a command request.")
        print(f"  {DIM}Use {CYAN}termai --chat{RESET}{DIM} for conversations and questions.{RESET}\n")
        return None

    from_fallback = False

    if _force_mode == "remote":
        return _generate_with_remote(instruction, ctx, local_result=None)

    if model.is_available and _force_mode != "local":
        local_result = _generate_with_llm(instruction, ctx, model)
    elif model.is_available:
        return _generate_with_llm(instruction, ctx, model)
    else:
        local_result = _generate_fallback(instruction, ctx)
        from_fallback = True

    if _force_mode == "local":
        return local_result

    from termai.remote import get_remote_provider
    remote = get_remote_provider()
    if remote and remote.is_available():
        from termai.classifier import classify
        decision = classify(instruction, local_result, from_fallback=from_fallback)
        if decision == "remote":
            remote_result = _generate_with_remote(instruction, ctx, local_result=local_result)
            if remote_result is not None:
                return remote_result

    return local_result


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


def _generate_with_remote(
    instruction: str,
    ctx: "SessionContext",
    *,
    local_result: str | None,
) -> str | None:
    """Delegate command generation to the remote AI provider."""
    from termai.remote import get_remote_provider
    remote = get_remote_provider()
    if not remote:
        return None

    print(f"  {CYAN}[remote]{RESET} {DIM}Processing with remote AI...{RESET}")

    system_prompt = ctx.as_system_prompt()
    user_prompt = f"Instruction: {instruction}"

    try:
        raw = remote.generate(system_prompt, user_prompt, max_tokens=512)
        if not raw:
            print(f"  {YELLOW}[remote]{RESET} {DIM}Empty response — using local result{RESET}")
            return local_result
        command = _clean_model_output(raw)
        if command:
            print(f"  {CYAN}[remote]{RESET} {DIM}Command generated by remote AI{RESET}")
            return command
        return local_result
    except Exception as e:
        print(f"  {YELLOW}[remote]{RESET} {DIM}Remote AI failed: {e} — using local result{RESET}")
        return local_result


_ENDOFTEXT_RE = re.compile(r"<\|endoftext\|>.*", re.DOTALL)
_FENCE_RE = re.compile(r"```(?:bash|sh|zsh|shell)?\s*\n?(.*?)\n?```", re.DOTALL)
_JUNK_MARKERS = re.compile(
    r"^(Answer:|Note:|Explanation:|Warning:|---"
    r"|[A-D]\.\s|#\s|//\s|\*\s|- [A-Z])",
)


def _clean_model_output(raw: str) -> str:
    """Extract only the shell command from model output.

    Handles common failure modes of small local LLMs:
    - Markdown code fences
    - Leading $ prompts
    - <|endoftext|> tokens followed by hallucinated text
    - Explanatory prose mixed in with the command
    - Multi-paragraph responses where only line 1 is the command
    """
    text = raw.strip()

    text = _ENDOFTEXT_RE.sub("", text).strip()

    m = _FENCE_RE.search(text)
    if m:
        text = m.group(1).strip()

    if text.startswith("$ "):
        text = text[2:]

    clean_lines: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            if clean_lines:
                break
            continue
        if _JUNK_MARKERS.match(line):
            break
        if line.startswith("#") and not line.startswith("#!"):
            continue
        clean_lines.append(line)

    result = "\n".join(clean_lines).strip()

    if not result or len(result) > 500:
        first_line = text.splitlines()[0].strip() if text else ""
        if first_line.startswith("$ "):
            first_line = first_line[2:]
        return first_line

    return result


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
    (["git", "history"],           "git log --oneline -10"),
    (["docker", "containers"],     "docker ps -a"),
    (["docker", "images"],         "docker images"),
    (["command", "history"],       "cat ~/.zsh_history | tail -30" if __import__("os").environ.get("SHELL", "").endswith("zsh") else "cat ~/.bash_history | tail -30"),
    (["history"],                  "cat ~/.zsh_history | tail -30" if __import__("os").environ.get("SHELL", "").endswith("zsh") else "cat ~/.bash_history | tail -30"),
    (["whoami"],                   "whoami"),
    (["uptime"],                   "uptime"),
    (["date"],                     "date"),
    (["hostname"],                 "hostname"),
    (["cpu", "info"],              "sysctl -n machdep.cpu.brand_string" if __import__("platform").system() == "Darwin" else "lscpu"),
    (["open", "ports"],            "lsof -i -P -n | grep LISTEN"),
    (["environment", "variables"], "env"),
    (["path"],                     "echo $PATH | tr ':' '\\n'"),
]


def _generate_fallback(instruction: str, ctx: "SessionContext") -> str:
    """Keyword-matching fallback when no AI model is loaded."""
    words = instruction.lower().split()
    best_match = ""
    best_score = 0.0

    for keywords, cmd in _FALLBACK_MAP:
        hits = sum(1 for kw in keywords if kw in words)
        if hits == 0:
            continue
        # Prefer rules where ALL keywords match (ratio == 1.0),
        # breaking ties by absolute number of matched keywords.
        ratio = hits / len(keywords)
        score = ratio + hits * 0.01
        if score > best_score:
            best_score = score
            best_match = cmd

    if best_match:
        print("[termai] (using rule-based fallback)")
        return best_match

    print("[termai] Could not generate a command. Try rephrasing or install a local model.")
    return None  # type: ignore[return-value]
