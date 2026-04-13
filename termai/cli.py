"""Command-line interface for termai."""

import argparse
import os
import sys

from termai import __version__
from termai.generator import generate_command
from termai.context import SessionContext
from termai.chat import interactive_chat
from termai.executor import preview_and_execute
from termai.logger import print_history
from termai.orchestrator import is_multistep, generate_plan, execute_plan
from termai.process_log import print_processes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="termai",
        description="Local AI-powered terminal assistant",
        usage="%(prog)s [options] <instruction ...>",
    )
    parser.add_argument(
        "--chat",
        action="store_true",
        help="Start interactive chat mode",
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Skip confirmation and execute immediately",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the generated command without executing",
    )
    parser.add_argument(
        "--history",
        nargs="?",
        const=20,
        type=int,
        metavar="N",
        help="Show recent command history (default: last 20)",
    )
    parser.add_argument(
        "--model",
        metavar="NAME",
        help="Override the LLM model name (e.g. 'Mistral-7B-Instruct-v0.1.Q4_0.gguf')",
    )
    parser.add_argument(
        "--device",
        choices=["cpu", "gpu", "cuda", "amd", "intel"],
        help="Device to run the model on (default: cpu)",
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="Full installation wizard (terminal) — install binary, pick a model, configure",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Launch the graphical setup wizard",
    )
    parser.add_argument(
        "--settings",
        action="store_true",
        help="Open the settings dashboard (model, allow list, config)",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Interactive model selector — pick and download a local AI model",
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="Show available AI models with sizes and quality info",
    )
    parser.add_argument(
        "--init-config",
        action="store_true",
        help="Write a default config file to ~/.termai/config.toml",
    )
    parser.add_argument(
        "--processes",
        nargs="?",
        const=20,
        type=int,
        metavar="N",
        help="Show recent multi-step process history (default: last 20)",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove termai binaries, config, and optionally downloaded models",
    )
    parser.add_argument(
        "--remote",
        action="store_true",
        help="Force remote AI for this run (requires configured API key)",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Force local-only AI for this run (ignore remote config)",
    )
    parser.add_argument(
        "--provider",
        choices=["openai", "claude"],
        help="Override the remote AI provider for this run",
    )
    parser.add_argument(
        "--info",
        action="store_true",
        help="Show current AI model and configuration status",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


CYAN = "\033[1;36m"
GREEN = "\033[1;32m"
YELLOW = "\033[0;33m"
RED = "\033[1;31m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def _print_info() -> None:
    """Show current AI model and configuration status."""
    from termai.config import get_config, CONFIG_FILE
    from termai.model import LocalModel, MODEL_DIR
    from termai.remote import get_remote_provider

    cfg = get_config()

    print(f"\n  {BOLD}termai v{__version__}{RESET}")
    print(f"  {'─' * 40}")

    # Local model
    print(f"\n  {BOLD}Local AI{RESET}")
    model_path = MODEL_DIR / cfg.model
    if model_path.exists():
        size_mb = model_path.stat().st_size / (1024 * 1024)
        print(f"  {GREEN}●{RESET} {cfg.model}")
        print(f"    {DIM}Size: {size_mb:.0f} MB | Device: {cfg.device} | Tokens: {cfg.max_tokens}{RESET}")
    else:
        print(f"  {RED}●{RESET} {cfg.model} {DIM}(not installed){RESET}")
        print(f"    {DIM}Run: termai --setup{RESET}")

    # Remote AI
    print(f"\n  {BOLD}Remote AI{RESET}")
    remote = get_remote_provider()
    if remote and remote.is_available():
        provider_name = cfg.remote_provider.capitalize()
        model_name = cfg.remote_model or "(default)"
        key_hint = "configured"
        print(f"  {GREEN}●{RESET} {provider_name}: {model_name}")
        print(f"    {DIM}API key: {key_hint} | Timeout: {cfg.remote_timeout}s{RESET}")
    else:
        print(f"  {DIM}●{RESET} Not configured")
        print(f"    {DIM}Run: termai --settings{RESET}")

    # Config file
    print(f"\n  {BOLD}Config{RESET}")
    if CONFIG_FILE.exists():
        print(f"  {DIM}{CONFIG_FILE}{RESET}")
    else:
        print(f"  {DIM}No config file (using defaults){RESET}")

    print()


_COMMON_SHORT_WORDS = {
    "a", "i", "an", "as", "at", "be", "by", "do", "go", "if", "in", "is",
    "it", "me", "my", "no", "of", "on", "or", "so", "to", "up", "us", "we",
}


def _check_truncation(instruction: str) -> str:
    """Detect if the instruction was likely truncated by a shell line wrap.

    If the last word looks like a partial word (1-2 chars, not a common
    short word), prompt the user to complete or re-enter it.
    """
    words = instruction.split()
    if not words:
        return instruction

    last = words[-1].lower()
    if len(last) <= 2 and last not in _COMMON_SHORT_WORDS and len(words) >= 4:
        print(f"\n  {YELLOW}[termai]{RESET} Your instruction might be cut off "
              f"(ends with \"{words[-1]}\").")
        print(f"  {DIM}This can happen when the terminal wraps a long line.{RESET}")
        try:
            rest = input(f"  {BOLD}Continue typing (or Enter to use as-is):{RESET} ").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n  {DIM}Cancelled.{RESET}")
            sys.exit(0)
        if rest:
            instruction = f"{instruction}{rest}"
            print(f"  {DIM}Full instruction: {instruction}{RESET}")
    return instruction


def _should_auto_gui() -> bool:
    """Return True if we're a frozen exe launched with no args."""
    if not getattr(sys, "frozen", False):
        return False
    return len(sys.argv) <= 1


def main() -> None:
    if _should_auto_gui():
        from termai.gui import run_gui_wizard
        run_gui_wizard()
        return

    parser = build_parser()
    args, remaining = parser.parse_known_args()

    unknown_flags = [r for r in remaining if r.startswith("--")]
    if unknown_flags:
        parser.error(f"unrecognized arguments: {' '.join(unknown_flags)}")

    instruction = " ".join(remaining).strip() or None

    if args.gui:
        from termai.gui import run_gui_wizard
        run_gui_wizard(mode="wizard")
        return

    if args.settings:
        from termai.gui import run_gui_wizard
        run_gui_wizard(mode="settings")
        return

    if args.install:
        from termai.installer import run_install_wizard
        run_install_wizard()
        return

    if args.setup:
        from termai.models import interactive_setup
        interactive_setup()
        return

    if args.list_models:
        from termai.models import print_catalog
        print_catalog()
        return

    if args.init_config:
        from termai.config import Config
        cfg = Config()
        cfg.write_default()
        print("[termai] Config written to ~/.termai/config.toml")
        return

    if args.uninstall:
        from termai.uninstaller import run_uninstall
        run_uninstall()
        return

    if args.info:
        _print_info()
        return

    if args.history is not None:
        print_history(limit=args.history)
        return

    if args.processes is not None:
        print_processes(limit=args.processes)
        return

    if args.model:
        os.environ["TERMAI_MODEL"] = args.model
    if args.device:
        os.environ["TERMAI_DEVICE"] = args.device
    if args.provider:
        os.environ["TERMAI_REMOTE_PROVIDER"] = args.provider

    from termai.generator import set_force_mode
    if args.remote:
        set_force_mode("remote")
    elif args.local:
        set_force_mode("local")

    from termai.session import cleanup_stale_sessions
    cleanup_stale_sessions()

    ctx = SessionContext()

    if args.chat:
        interactive_chat(ctx)
        return

    if not instruction:
        parser.print_help()
        sys.exit(1)

    instruction = _check_truncation(instruction)

    ctx.set_current_instruction(instruction)

    if is_multistep(instruction):
        plan = generate_plan(instruction, ctx)
        if plan and len(plan.steps) > 1:
            execute_plan(plan, ctx,
                         dry_run=args.dry_run, auto_yes=args.yes)
            return

    command = generate_command(instruction, ctx)
    if command:
        preview_and_execute(
            command,
            ctx,
            dry_run=args.dry_run,
            auto_yes=args.yes,
            instruction=instruction,
        )


if __name__ == "__main__":
    main()
