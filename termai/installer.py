"""Full installation wizard for termai.

Handles everything in one step:
  1. Installs the binary to a directory on PATH
  2. Creates the 'tai' symlink alias
  3. Runs the interactive model selector
  4. Creates the config file

Invoked via ``termai --install`` or ``./termai --install``.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from termai.config import CONFIG_DIR, CONFIG_FILE

BOLD = "\033[1m"
CYAN = "\033[1;36m"
GREEN = "\033[1;32m"
YELLOW = "\033[0;33m"
RED = "\033[1;31m"
DIM = "\033[2m"
RESET = "\033[0m"

INSTALL_DIRS_UNIX = [
    Path("/usr/local/bin"),
    Path.home() / ".local" / "bin",
    Path.home() / "bin",
]

INSTALL_DIRS_WINDOWS = [
    Path.home() / "AppData" / "Local" / "Programs" / "termai",
]


def run_install_wizard() -> None:
    """Run the full installation wizard."""
    print(f"\n{CYAN}{'═' * 54}{RESET}")
    print(f"{CYAN}  termai — installation wizard{RESET}")
    print(f"{CYAN}{'═' * 54}{RESET}\n")

    # Step 1: Install binary
    _step_header(1, "Install binary")
    binary_installed = _install_binary()

    # Step 2: Pick and download a model
    _step_header(2, "Choose an AI model")
    from termai.models import interactive_setup
    interactive_setup()

    # Step 3: Config file
    _step_header(3, "Configuration")
    _ensure_config()

    # Done
    print(f"\n{GREEN}{'═' * 54}{RESET}")
    print(f"{GREEN}  Installation complete!{RESET}")
    print(f"{GREEN}{'═' * 54}{RESET}\n")

    if binary_installed:
        print(f"  {BOLD}Get started:{RESET}")
        print(f"    termai \"your instruction\"     generate a command")
        print(f"    termai -y \"your instruction\"   execute immediately")
        print(f"    termai --chat                  interactive mode")
        print(f"    tai \"your instruction\"         short alias")
    else:
        exe = sys.executable if getattr(sys, "frozen", False) else "termai"
        print(f"  {BOLD}Get started:{RESET}")
        print(f"    {exe} \"your instruction\"")

    print(f"\n  {DIM}Run 'termai --setup' anytime to change the AI model.{RESET}")
    print(f"  {DIM}Run 'termai --install' anytime to re-run this wizard.{RESET}\n")


def _step_header(num: int, title: str) -> None:
    print(f"\n  {CYAN}Step {num}: {title}{RESET}")
    print(f"  {DIM}{'─' * 48}{RESET}")


def _install_binary() -> bool:
    """Install the termai binary to a directory on PATH."""
    is_frozen = getattr(sys, "frozen", False)

    if not is_frozen:
        # Running from pip install — binary is already on PATH
        which = shutil.which("termai")
        if which:
            print(f"  {GREEN}✓{RESET} termai is installed via pip at {DIM}{which}{RESET}")
            tai = shutil.which("tai")
            if tai:
                print(f"  {GREEN}✓{RESET} tai alias available at {DIM}{tai}{RESET}")
            return True
        else:
            print(f"  {YELLOW}termai is not on PATH.{RESET}")
            print(f"  {DIM}Run: pip install -e . (from the project directory){RESET}")
            return False

    # Running as a standalone executable (PyInstaller)
    current_exe = Path(sys.executable)
    print(f"  {DIM}Current binary: {current_exe}{RESET}")

    if platform.system() == "Windows":
        return _install_windows(current_exe)
    else:
        return _install_unix(current_exe)


def _install_unix(current_exe: Path) -> bool:
    """Install binary + symlink on macOS/Linux."""
    # Find a writable directory on PATH, or pick a default
    install_dir = None
    for d in INSTALL_DIRS_UNIX:
        if d.exists() and os.access(d, os.W_OK):
            install_dir = d
            break

    if install_dir is None:
        # Try /usr/local/bin with sudo
        install_dir = INSTALL_DIRS_UNIX[0]

    dest = install_dir / "termai"
    tai_dest = install_dir / "tai"

    if dest.exists() and dest.resolve() == current_exe.resolve():
        print(f"  {GREEN}✓{RESET} Already installed at {dest}")
        if not tai_dest.exists():
            _symlink(dest, tai_dest)
        return True

    needs_sudo = not os.access(install_dir, os.W_OK)

    print(f"  Installing to {BOLD}{install_dir}{RESET}")
    if needs_sudo:
        print(f"  {DIM}(requires sudo — you may be prompted for your password){RESET}")

    try:
        answer = input(f"\n  Proceed? [Y/n] ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print(f"\n  {DIM}Skipped.{RESET}")
        return False

    if answer in ("n", "no"):
        print(f"  {DIM}Skipped binary installation.{RESET}")
        return False

    try:
        install_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        pass

    if needs_sudo:
        subprocess.run(["sudo", "cp", str(current_exe), str(dest)], check=True)
        subprocess.run(["sudo", "chmod", "+x", str(dest)], check=True)
        subprocess.run(["sudo", "ln", "-sf", str(dest), str(tai_dest)], check=True)
    else:
        shutil.copy2(current_exe, dest)
        dest.chmod(0o755)
        _symlink(dest, tai_dest)

    print(f"  {GREEN}✓{RESET} Installed {BOLD}termai{RESET} to {dest}")
    print(f"  {GREEN}✓{RESET} Created {BOLD}tai{RESET} alias at {tai_dest}")

    # Check if install_dir is on PATH
    path_dirs = os.environ.get("PATH", "").split(":")
    if str(install_dir) not in path_dirs:
        shell = os.environ.get("SHELL", "")
        rc = "~/.zshrc" if "zsh" in shell else "~/.bashrc"
        print(f"\n  {YELLOW}Note:{RESET} {install_dir} is not in your PATH.")
        print(f"  Add this to {rc}:")
        print(f"    export PATH=\"{install_dir}:$PATH\"")

    return True


def _install_windows(current_exe: Path) -> bool:
    """Install binary on Windows."""
    install_dir = INSTALL_DIRS_WINDOWS[0]
    dest = install_dir / "termai.exe"
    tai_dest = install_dir / "tai.exe"

    print(f"  Installing to {BOLD}{install_dir}{RESET}")

    try:
        answer = input(f"\n  Proceed? [Y/n] ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print(f"\n  {DIM}Skipped.{RESET}")
        return False

    if answer in ("n", "no"):
        print(f"  {DIM}Skipped binary installation.{RESET}")
        return False

    try:
        install_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(current_exe, dest)
        shutil.copy2(current_exe, tai_dest)
        print(f"  {GREEN}✓{RESET} Installed to {dest}")
        print(f"  {GREEN}✓{RESET} Created tai.exe at {tai_dest}")

        # Add to user PATH if not already there
        path_dirs = os.environ.get("PATH", "").split(";")
        if str(install_dir) not in path_dirs:
            print(f"\n  {YELLOW}Note:{RESET} Add {install_dir} to your system PATH:")
            print(f'  [System Settings > Environment Variables > PATH > Add "{install_dir}"]')

        return True
    except Exception as e:
        print(f"  {RED}Failed: {e}{RESET}")
        return False


def _symlink(source: Path, link: Path) -> None:
    """Create a symlink, removing existing one if needed."""
    try:
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to(source)
    except PermissionError:
        subprocess.run(["sudo", "ln", "-sf", str(source), str(link)], check=True)


def _ensure_config() -> None:
    """Create the config directory and default config if missing."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if CONFIG_FILE.exists():
        print(f"  {GREEN}✓{RESET} Config file exists at {DIM}{CONFIG_FILE}{RESET}")
    else:
        from termai.config import Config
        cfg = Config()
        cfg.write_default()
        print(f"  {GREEN}✓{RESET} Created config at {DIM}{CONFIG_FILE}{RESET}")

    plugins_dir = CONFIG_DIR / "plugins"
    plugins_dir.mkdir(exist_ok=True)
    print(f"  {GREEN}✓{RESET} Plugin directory ready at {DIM}{plugins_dir}{RESET}")
