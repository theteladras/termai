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


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.init_config:
        from termai.config import Config
        cfg = Config()
        cfg.write_default()
        print(f"[termai] Config written to ~/.termai/config.toml")
        return

    if args.history is not None:
        print_history(limit=args.history)
        return

    # Propagate CLI model/device overrides via env vars so that Config picks
    # them up before the model is loaded.
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
            instruction=args.instruction,
        )


if __name__ == "__main__":
    main()
