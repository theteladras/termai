"""Uninstall termai — remove binaries, config, and optionally models."""

from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path

CYAN = "\033[1;36m"
GREEN = "\033[1;32m"
RED = "\033[1;31m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"

CONFIG_DIR = Path.home() / ".termai"
MODEL_DIR = Path(os.environ.get("TERMAI_MODEL_DIR", Path.home() / ".cache" / "gpt4all"))

INSTALL_DIRS_UNIX = [
    Path("/usr/local/bin"),
    Path.home() / ".local" / "bin",
    Path.home() / "bin",
]


def _remove_file(path: Path, label: str) -> bool:
    if path.exists():
        try:
            path.unlink()
            print(f"  {GREEN}✓{RESET} Removed {label}: {DIM}{path}{RESET}")
            return True
        except OSError as e:
            print(f"  {RED}✗{RESET} Could not remove {label}: {e}")
    return False


def _remove_dir(path: Path, label: str) -> bool:
    if path.exists():
        try:
            shutil.rmtree(path)
            print(f"  {GREEN}✓{RESET} Removed {label}: {DIM}{path}{RESET}")
            return True
        except OSError as e:
            print(f"  {RED}✗{RESET} Could not remove {label}: {e}")
    return False


def _find_binaries() -> list[Path]:
    found = []
    if platform.system() == "Windows":
        win_dir = Path.home() / "AppData" / "Local" / "Programs" / "termai"
        for name in ("termai.exe", "tai.exe"):
            p = win_dir / name
            if p.exists():
                found.append(p)
    else:
        for d in INSTALL_DIRS_UNIX:
            for name in ("termai", "tai"):
                p = d / name
                if p.exists() or p.is_symlink():
                    found.append(p)
    return found


def _list_models() -> list[Path]:
    if not MODEL_DIR.exists():
        return []
    return [f for f in MODEL_DIR.iterdir() if f.suffix == ".gguf"]


def run_uninstall() -> None:
    print(f"\n  {BOLD}termai uninstaller{RESET}\n")

    binaries = _find_binaries()
    models = _list_models()
    has_config = CONFIG_DIR.exists()

    if not binaries and not has_config and not models:
        print(f"  {DIM}Nothing to uninstall — termai does not appear to be installed.{RESET}\n")
        return

    print(f"  The following will be removed:\n")

    if binaries:
        print(f"  {BOLD}Binaries:{RESET}")
        for b in binaries:
            print(f"    {b}")

    if has_config:
        print(f"\n  {BOLD}Configuration:{RESET}")
        print(f"    {CONFIG_DIR}/")

    if models:
        total_mb = sum(f.stat().st_size for f in models) / 1e6
        print(f"\n  {BOLD}Downloaded models ({total_mb:.0f} MB):{RESET}")
        for m in models:
            size_mb = m.stat().st_size / 1e6
            print(f"    {m.name} ({size_mb:.0f} MB)")

    print()
    answer = input(f"  {CYAN}Proceed with uninstall? [y/N]{RESET} ").strip().lower()
    if answer != "y":
        print(f"\n  {DIM}Cancelled.{RESET}\n")
        return

    print()

    for b in binaries:
        if b.is_symlink():
            _remove_file(b, "symlink")
        else:
            _remove_file(b, "binary")

    if has_config:
        _remove_dir(CONFIG_DIR, "config directory")

    if models:
        remove_models = input(f"\n  {CYAN}Also remove downloaded AI models? ({sum(f.stat().st_size for f in models) / 1e6:.0f} MB) [y/N]{RESET} ").strip().lower()
        if remove_models == "y":
            for m in models:
                _remove_file(m, "model")

    print(f"\n  {GREEN}{BOLD}termai has been uninstalled.{RESET}\n")
