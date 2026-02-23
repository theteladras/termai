"""Model catalog and interactive model selector.

Provides a curated list of known-good models with metadata (size, RAM
requirements, quality tier) and an interactive terminal menu for picking
and downloading a model on first use or via ``termai --setup``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from termai.config import CONFIG_DIR, CONFIG_FILE

BOLD = "\033[1m"
CYAN = "\033[1;36m"
GREEN = "\033[1;32m"
YELLOW = "\033[0;33m"
DIM = "\033[2m"
RESET = "\033[0m"

MODEL_DIR = Path(os.environ.get("TERMAI_MODEL_DIR", Path.home() / ".cache" / "gpt4all"))


@dataclass(frozen=True)
class ModelInfo:
    name: str
    filename: str
    size_gb: float
    params: str
    min_ram: str
    quality: str
    description: str


CATALOG: list[ModelInfo] = [
    ModelInfo(
        name="Phi-3 Mini",
        filename="Phi-3-mini-4k-instruct.Q4_0.gguf",
        size_gb=2.2,
        params="3.8B",
        min_ram="8 GB",
        quality="Good",
        description="Best balance of speed and quality for laptops",
    ),
    ModelInfo(
        name="Orca Mini 3B",
        filename="orca-mini-3b-gguf2-q4_0.gguf",
        size_gb=2.0,
        params="3B",
        min_ram="8 GB",
        quality="Basic",
        description="Smallest and fastest — works on any machine",
    ),
    ModelInfo(
        name="Mistral 7B Instruct",
        filename="Nous-Hermes-2-Mistral-7B-DPO.Q4_0.gguf",
        size_gb=4.1,
        params="7B",
        min_ram="8 GB",
        quality="Better",
        description="Higher quality, good for complex commands",
    ),
    ModelInfo(
        name="LLaMA 3 8B Instruct",
        filename="Meta-Llama-3-8B-Instruct.Q4_0.gguf",
        size_gb=4.7,
        params="8B",
        min_ram="16 GB",
        quality="Best",
        description="Top quality, needs more RAM",
    ),
]


def print_catalog() -> None:
    """Print the model catalog as a formatted table."""
    print(f"\n{BOLD}  Available models:{RESET}\n")
    print(f"  {'#':<4} {'Name':<24} {'Size':<10} {'Params':<8} {'RAM':<8} {'Quality':<8}")
    print(f"  {'─' * 4} {'─' * 24} {'─' * 10} {'─' * 8} {'─' * 8} {'─' * 8}")

    for i, m in enumerate(CATALOG, 1):
        installed = _is_installed(m.filename)
        tag = f" {GREEN}✓{RESET}" if installed else ""
        print(
            f"  {i:<4} {m.name:<24} {m.size_gb:.1f} GB{'':<4} {m.params:<8} {m.min_ram:<8} {m.quality:<8}{tag}"
        )
        print(f"       {DIM}{m.description}{RESET}")

    print(f"\n  {DIM}✓ = already downloaded{RESET}\n")


def interactive_setup() -> str | None:
    """Run the interactive model selector. Returns the chosen filename or None."""
    print(f"\n{CYAN}{'═' * 54}{RESET}")
    print(f"{CYAN}  termai — model setup{RESET}")
    print(f"{CYAN}{'═' * 54}{RESET}")

    print_catalog()

    print(f"  {DIM}Models are downloaded once (~2-5 GB) and run locally.{RESET}")
    print(f"  {DIM}Press Enter for the default [1], or 0 to skip.{RESET}\n")

    try:
        choice = input(f"  {BOLD}Select a model [1-{len(CATALOG)}, 0 to skip]: {RESET}").strip()
    except (KeyboardInterrupt, EOFError):
        print(f"\n{DIM}[termai] Setup cancelled.{RESET}")
        return None

    if not choice:
        choice = "1"

    try:
        idx = int(choice)
    except ValueError:
        print(f"{YELLOW}[termai] Invalid selection.{RESET}")
        return None

    if idx == 0:
        print(f"{DIM}[termai] Skipped model download. Using rule-based fallback.{RESET}")
        return None

    if idx < 1 or idx > len(CATALOG):
        print(f"{YELLOW}[termai] Invalid selection (pick 1-{len(CATALOG)}).{RESET}")
        return None

    model = CATALOG[idx - 1]

    if _is_installed(model.filename):
        print(f"\n{GREEN}[termai] {model.name} is already downloaded!{RESET}")
        _save_model_choice(model.filename)
        return model.filename

    print(f"\n{CYAN}[termai] Downloading {model.name} ({model.size_gb:.1f} GB)...{RESET}")
    print(f"{DIM}[termai] Destination: {MODEL_DIR}{RESET}")
    print(f"{DIM}[termai] This may take a few minutes. Press Ctrl-C to cancel.{RESET}\n")

    try:
        from gpt4all import GPT4All  # type: ignore[import-untyped]

        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        GPT4All(model.filename, model_path=str(MODEL_DIR), allow_download=True)
        print(f"\n{GREEN}[termai] {model.name} is ready!{RESET}")
        _save_model_choice(model.filename)
        return model.filename

    except KeyboardInterrupt:
        print(f"\n{YELLOW}[termai] Download cancelled.{RESET}")
        return None
    except Exception as e:
        print(f"\n\033[1;31m[termai] Download failed: {e}\033[0m")
        return None


def _is_installed(filename: str) -> bool:
    return (MODEL_DIR / filename).exists()


def _save_model_choice(filename: str) -> None:
    """Persist the selected model to the config file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if CONFIG_FILE.exists():
        content = CONFIG_FILE.read_text()
        lines = content.splitlines()
        new_lines = []
        found = False
        for line in lines:
            if line.strip().startswith("model"):
                new_lines.append(f'model = "{filename}"')
                found = True
            else:
                new_lines.append(line)
        if not found:
            if "[termai]" not in content:
                new_lines.insert(0, "[termai]")
            # Insert after the [termai] header
            for i, line in enumerate(new_lines):
                if line.strip() == "[termai]":
                    new_lines.insert(i + 1, f'model = "{filename}"')
                    break
        CONFIG_FILE.write_text("\n".join(new_lines) + "\n")
    else:
        CONFIG_FILE.write_text(
            "[termai]\n"
            f'model = "{filename}"\n'
            'device = "cpu"\n'
            "max_tokens = 256\n"
            "temperature = 0.2\n"
        )

    print(f"{DIM}[termai] Saved model choice to {CONFIG_FILE}{RESET}")
