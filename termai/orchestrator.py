"""AI-powered task orchestrator for multi-step command execution.

When a user instruction requires multiple shell commands, the orchestrator:
1. Uses AI to decompose the task into atomic steps with dependencies
2. Resolves the dependency graph into execution waves
3. Runs independent steps in parallel within each wave
4. Provides real-time progress feedback
5. Logs the full process for auditing
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from termai.safety import check_command
from termai.allowlist import should_auto_execute, add_to_session, add_to_permanent
from termai.logger import log_command

if TYPE_CHECKING:
    from termai.context import SessionContext

CYAN = "\033[1;36m"
GREEN = "\033[1;32m"
YELLOW = "\033[0;33m"
RED = "\033[1;31m"
BOLD = "\033[1m"
DIM = "\033[2m"
MAGENTA = "\033[1;35m"
RESET = "\033[0m"

_print_lock = threading.Lock()


# -- Data structures ----------------------------------------------------------

@dataclass
class Step:
    id: int
    command: str
    description: str
    depends_on: list[int] = field(default_factory=list)
    status: str = "pending"
    exit_code: int | None = None
    duration_ms: int | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "command": self.command,
            "description": self.description,
            "depends_on": self.depends_on,
            "status": self.status,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
        }


@dataclass
class Plan:
    instruction: str
    steps: list[Step] = field(default_factory=list)
    ai_provider: str = ""
    process_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: str = "pending"
    total_duration_ms: int | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.process_id,
            "instruction": self.instruction,
            "ai_provider": self.ai_provider,
            "steps": [s.to_dict() for s in self.steps],
            "status": self.status,
            "total_duration_ms": self.total_duration_ms,
        }


# -- Multi-step detection -----------------------------------------------------

_MULTISTEP_MARKERS = re.compile(
    r"\b(?:and\s+then|then\s+\w|first\s+\w|after\s+that|next\s+\w"
    r"|finally\s+\w|also\s+\w|plus\s+\w|additionally"
    r"|set\s*up\b|deploy\b|migrate\b|scaffold\b|bootstrap\b"
    r"|create.*and.*install|install.*and.*configure)\b",
    re.IGNORECASE,
)

_MULTI_ACTION_VERBS = frozenset({
    "create", "make", "set", "setup", "install", "configure", "build",
    "deploy", "push", "commit", "add", "remove", "delete", "update",
    "copy", "move", "rename", "download", "upload", "start", "stop",
    "init", "initialize", "run", "execute", "open", "close",
})


def is_multistep(instruction: str) -> bool:
    """Heuristic: does this instruction likely need multiple commands?"""
    if _MULTISTEP_MARKERS.search(instruction):
        return True

    words = instruction.lower().split()
    verb_count = sum(1 for w in words if w in _MULTI_ACTION_VERBS)
    if verb_count >= 2:
        return True

    if instruction.count(",") >= 2 and len(words) > 8:
        return True

    return False


# -- Plan generation ----------------------------------------------------------

PLAN_SYSTEM_PROMPT = """\
You are termai, a terminal AI that creates execution plans.
Given the user's instruction and system context, produce a JSON execution plan.

Rules:
1. Break the task into the smallest reasonable atomic shell commands
2. Each step = ONE shell command (pipelines/chains within a step are OK)
3. Identify which steps depend on prior steps completing first
4. Steps that CAN run independently SHOULD have no unnecessary dependencies
5. Each command must be self-contained (include cd if it must run in a specific directory)
6. Use commands appropriate for the user's OS and shell
7. Output ONLY valid JSON — no explanation, no markdown fences

Format:
{"steps":[{"id":1,"cmd":"...","desc":"...","needs":[]},\
{"id":2,"cmd":"...","desc":"...","needs":[1]}]}

"needs" = array of step IDs that must complete first. Empty [] = no deps."""


def generate_plan(instruction: str, ctx: "SessionContext") -> Plan | None:
    """Use AI to decompose an instruction into a multi-step plan."""
    plan = Plan(instruction=instruction)
    system = PLAN_SYSTEM_PROMPT + "\n\n--- System Context ---\n" + ctx.summary() + "\n--- End Context ---"
    user_prompt = f"Instruction: {instruction}"

    from termai.generator import _force_mode
    from termai.remote import get_remote_provider

    remote = get_remote_provider()
    if remote and remote.is_available() and _force_mode != "local":
        print(f"  {CYAN}[orchestrator]{RESET} {DIM}Creating execution plan (remote)...{RESET}")
        try:
            raw = remote.generate(system, user_prompt, max_tokens=1024)
            steps = _parse_plan_json(raw)
            if steps:
                plan.steps = steps
                plan.ai_provider = f"remote/{type(remote).__name__}"
                return plan
        except Exception as e:
            print(f"  {YELLOW}[orchestrator]{RESET} {DIM}Remote planning failed: {e}{RESET}")

    if _force_mode == "remote":
        return None

    from termai.model import LocalModel
    model = LocalModel()
    if model.is_available:
        print(f"  {CYAN}[orchestrator]{RESET} {DIM}Creating execution plan (local)...{RESET}")
        raw = model.generate(system, user_prompt, max_tokens=1024)
        if raw:
            steps = _parse_plan_json(raw)
            if steps:
                plan.steps = steps
                plan.ai_provider = f"local/{model.model_name}"
                return plan
            commands = _extract_commands_from_text(raw)
            if commands:
                plan.steps = [
                    Step(id=i + 1, command=cmd, description="",
                         depends_on=list(range(1, i + 1)))
                    for i, cmd in enumerate(commands)
                ]
                plan.ai_provider = f"local/{model.model_name}"
                return plan

    return None


def _parse_plan_json(raw: str) -> list[Step] | None:
    """Try to parse a JSON plan from AI output."""
    text = raw.strip()
    fence = re.compile(r"```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL)
    m = fence.search(text)
    if m:
        text = m.group(1).strip()

    start = text.find("{")
    end = text.rfind("}") + 1
    if start < 0 or end <= start:
        return None

    try:
        data = json.loads(text[start:end])
    except json.JSONDecodeError:
        return None

    steps_data = data.get("steps", [])
    if not steps_data:
        return None

    steps: list[Step] = []
    for s in steps_data:
        step = Step(
            id=s.get("id", len(steps) + 1),
            command=s.get("cmd") or s.get("command", ""),
            description=s.get("desc") or s.get("description", ""),
            depends_on=s.get("needs") or s.get("depends_on", []),
        )
        if step.command:
            steps.append(step)

    return steps if steps else None


_CMD_LINE_RE = re.compile(r"^\d+[.)]\s*(.+)$", re.MULTILINE)
_FENCE_RE = re.compile(r"```(?:bash|sh|zsh)?\s*\n(.*?)\n```", re.DOTALL)


def _extract_commands_from_text(raw: str) -> list[str]:
    """Fallback: extract commands from non-JSON AI output."""
    matches = _FENCE_RE.findall(raw)
    if matches:
        commands: list[str] = []
        for block in matches:
            for line in block.strip().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    commands.append(line)
        if commands:
            return commands

    matches = _CMD_LINE_RE.findall(raw)
    if matches:
        return [m.strip() for m in matches if m.strip()]

    return []


# -- Dependency resolution ----------------------------------------------------

def resolve_waves(steps: list[Step]) -> list[list[Step]]:
    """Group steps into execution waves by dependency order.

    Steps within a wave can run in parallel. Waves run sequentially.
    """
    if not steps:
        return []

    completed: set[int] = set()
    waves: list[list[Step]] = []
    remaining = list(steps)

    for _ in range(len(steps) + 1):
        if not remaining:
            break
        wave = [s for s in remaining
                if all(d in completed for d in s.depends_on)]
        if not wave:
            for s in remaining:
                waves.append([s])
            break
        waves.append(wave)
        for s in wave:
            completed.add(s.id)
        remaining = [s for s in remaining if s.id not in completed]

    return waves


# -- Plan display -------------------------------------------------------------

def display_plan(plan: Plan) -> None:
    """Pretty-print the execution plan to the terminal."""
    waves = resolve_waves(plan.steps)
    n_steps = len(plan.steps)
    n_waves = len(waves)
    ai = plan.ai_provider or "unknown"

    print()
    print(f"  {MAGENTA}╭─ Execution Plan {'─' * 33}{RESET}")
    print(f"  {MAGENTA}│{RESET}  {BOLD}\"{plan.instruction}\"{RESET}")
    print(f"  {MAGENTA}│{RESET}  {DIM}{n_steps} step{'s' if n_steps != 1 else ''}"
          f" • {n_waves} wave{'s' if n_waves != 1 else ''}"
          f" • {ai}{RESET}")
    print(f"  {MAGENTA}├{'─' * 52}{RESET}")

    for wi, wave in enumerate(waves, 1):
        parallel = len(wave) > 1
        label = f"Wave {wi}" + (" (parallel)" if parallel else "")
        print(f"  {MAGENTA}│{RESET}  {BOLD}{label}{RESET}")
        for step in wave:
            deps = ""
            if step.depends_on:
                deps = f" {DIM}(after: {', '.join(str(d) for d in step.depends_on)}){RESET}"
            print(f"  {MAGENTA}│{RESET}    {DIM}{step.id}.{RESET} {step.command}")
            if step.description:
                print(f"  {MAGENTA}│{RESET}       {DIM}{step.description}{deps}{RESET}")
    print(f"  {MAGENTA}╰{'─' * 52}{RESET}")


# -- Plan execution -----------------------------------------------------------

def execute_plan(
    plan: Plan,
    ctx: "SessionContext",
    *,
    dry_run: bool = False,
    auto_yes: bool = False,
) -> Plan:
    """Execute a plan wave-by-wave with feedback and logging."""
    display_plan(plan)

    if dry_run:
        print(f"\n  {CYAN}(dry-run mode — plan will NOT be executed){RESET}")
        plan.status = "dry_run"
        return plan

    if not auto_yes:
        try:
            answer = input(f"\n  {BOLD}Execute plan?{RESET} [y/N] ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print(f"\n  {DIM}Cancelled.{RESET}")
            plan.status = "cancelled"
            return plan
        if answer not in ("y", "yes"):
            print(f"  {DIM}Cancelled.{RESET}")
            plan.status = "cancelled"
            return plan

    waves = resolve_waves(plan.steps)
    failed_ids: set[int] = set()
    start_time = time.monotonic()

    for wi, wave in enumerate(waves, 1):
        parallel = len(wave) > 1
        label = f"Wave {wi}/{len(waves)}" + (" (parallel)" if parallel else "")
        print(f"\n  {BOLD}▸ {label}{RESET}")

        runnable: list[Step] = []
        for step in wave:
            if any(d in failed_ids for d in step.depends_on):
                step.status = "skipped"
                print(f"    {YELLOW}⊘{RESET} {DIM}{step.id}. {step.command}"
                      f" (skipped — dependency failed){RESET}")
            else:
                runnable.append(step)

        if not runnable:
            continue

        if len(runnable) == 1:
            _execute_step(runnable[0], ctx, auto_yes=auto_yes)
            if runnable[0].status == "failed":
                failed_ids.add(runnable[0].id)
        else:
            _execute_wave_parallel(runnable, ctx, auto_yes=auto_yes,
                                   failed_ids=failed_ids)

    elapsed = int((time.monotonic() - start_time) * 1000)
    plan.total_duration_ms = elapsed

    succeeded = sum(1 for s in plan.steps if s.status == "success")
    failed = sum(1 for s in plan.steps if s.status == "failed")
    skipped = sum(1 for s in plan.steps if s.status == "skipped")
    total = len(plan.steps)

    if failed == 0 and skipped == 0:
        plan.status = "completed"
    elif succeeded == 0:
        plan.status = "failed"
    else:
        plan.status = "partial"

    elapsed_s = elapsed / 1000
    print(f"\n  {'═' * 52}")
    color = GREEN if plan.status == "completed" else (
        YELLOW if plan.status == "partial" else RED)
    print(f"  {color}Plan {plan.status}: {succeeded}/{total} steps succeeded"
          f" ({elapsed_s:.1f}s){RESET}")
    if skipped:
        print(f"  {DIM}{skipped} step{'s' if skipped > 1 else ''}"
              f" skipped (dependency failed){RESET}")
    print(f"  {'═' * 52}")

    from termai.process_log import log_process
    log_process(plan)

    return plan


def _execute_wave_parallel(
    steps: list[Step],
    ctx: "SessionContext",
    *,
    auto_yes: bool,
    failed_ids: set[int],
) -> None:
    """Execute a wave of independent steps, parallelizing safe ones."""
    needs_prompt: list[Step] = []
    safe_batch: list[Step] = []

    for step in steps:
        warnings = check_command(step.command)
        if warnings or (not auto_yes and not should_auto_execute(step.command)):
            needs_prompt.append(step)
        else:
            safe_batch.append(step)

    for step in needs_prompt:
        _execute_step(step, ctx, auto_yes=auto_yes)
        if step.status == "failed":
            failed_ids.add(step.id)

    if not safe_batch:
        return

    with ThreadPoolExecutor(max_workers=min(len(safe_batch), 4)) as pool:
        futures = {}
        for step in safe_batch:
            step.status = "running"
            f = pool.submit(_execute_step_bg, step, ctx)
            futures[f] = step

        for future in as_completed(futures):
            step = futures[future]
            try:
                future.result()
            except Exception:
                step.status = "failed"
            if step.status == "failed":
                failed_ids.add(step.id)


def _format_duration(ms: int) -> str:
    if ms < 1000:
        return f"{ms}ms"
    return f"{ms / 1000:.1f}s"


def _execute_step(
    step: Step,
    ctx: "SessionContext",
    *,
    auto_yes: bool = False,
) -> None:
    """Execute a step interactively (main thread)."""
    step.status = "running"
    t0 = time.monotonic()

    warnings = check_command(step.command)
    if warnings and not auto_yes:
        from termai.executor import preview_and_execute
        result = preview_and_execute(
            step.command, ctx, auto_yes=False, instruction=step.description)
        step.duration_ms = int((time.monotonic() - t0) * 1000)
        if result is True:
            step.status = "success"
            step.exit_code = 0
        elif result is False:
            step.status = "failed"
        else:
            step.status = "skipped"
        return

    try:
        result = subprocess.run(
            step.command, shell=True, cwd=ctx.cwd,
            stdout=sys.stdout, stderr=sys.stderr,
        )
        step.exit_code = result.returncode
        step.status = "success" if result.returncode == 0 else "failed"
    except Exception as e:
        step.status = "failed"
        print(f"    {RED}✗ Error: {e}{RESET}")

    step.duration_ms = int((time.monotonic() - t0) * 1000)
    dur = _format_duration(step.duration_ms)
    icon = f"{GREEN}✓{RESET}" if step.status == "success" else f"{RED}✗{RESET}"
    print(f"    {icon} {DIM}{step.id}. {step.command} ({dur}){RESET}")

    ctx.record(step.command)
    ctx.refresh_cwd()
    log_command(step.command, instruction=step.description,
                success=step.status == "success")


def _execute_step_bg(step: Step, ctx: "SessionContext") -> None:
    """Execute a step in a background thread (for parallel waves)."""
    t0 = time.monotonic()
    try:
        result = subprocess.run(
            step.command, shell=True, cwd=ctx.cwd,
            capture_output=True, text=True,
        )
        step.exit_code = result.returncode
        step.status = "success" if result.returncode == 0 else "failed"
        with _print_lock:
            if result.stdout:
                print(result.stdout, end="")
            if result.stderr:
                print(result.stderr, end="", file=sys.stderr)
    except Exception as e:
        step.status = "failed"
        with _print_lock:
            print(f"    {RED}✗ {step.command}: {e}{RESET}")

    step.duration_ms = int((time.monotonic() - t0) * 1000)
    dur = _format_duration(step.duration_ms)
    icon = f"{GREEN}✓{RESET}" if step.status == "success" else f"{RED}✗{RESET}"
    with _print_lock:
        print(f"    {icon} {DIM}{step.id}. {step.command} ({dur}){RESET}")

    log_command(step.command, instruction=step.description,
                success=step.status == "success")
