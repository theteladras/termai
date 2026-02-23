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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="termai",
        description="Local AI-powered terminal assistant",
    )
    parser.add_argument(
        "instruction",
        nargs="?",
        help="Natural language instruction to convert into a shell command",
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
        help="Launch the graphical installation wizard",
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
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


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
    args = parser.parse_args()

    if args.gui:
        from termai.gui import run_gui_wizard
        run_gui_wizard()
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

    if args.history is not None:
        print_history(limit=args.history)
        return

    if args.model:
        os.environ["TERMAI_MODEL"] = args.model
    if args.device:
        os.environ["TERMAI_DEVICE"] = args.device

    ctx = SessionContext()

    if args.chat:
        interactive_chat(ctx)
        return

    if not args.instruction:
        parser.print_help()
        sys.exit(1)

    command = generate_command(args.instruction, ctx)
    if command:
        preview_and_execute(
            command,
            ctx,
            dry_run=args.dry_run,
            auto_yes=args.yes,
            instruction=args.instruction,
        )


if __name__ == "__main__":
    main()
