#!/usr/bin/env python3
"""Build standalone executables for termai using PyInstaller.

Usage:
    python build.py                    # standard build (~15-30 MB)
    python build.py --bundle-model     # fat build with bundled model (~2+ GB)

The output binary lands in dist/termai (or dist/termai.exe on Windows).
Each OS must be built on its native platform — no cross-compilation.
"""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
ENTRY = ROOT / "termai" / "cli.py"

BUNDLE_MODEL = "orca-mini-3b-gguf2-q4_0.gguf"
MODEL_DIR = Path.home() / ".cache" / "gpt4all"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build termai standalone executable")
    parser.add_argument(
        "--bundle-model",
        action="store_true",
        help=f"Include {BUNDLE_MODEL} in the executable for offline use",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove build and dist directories before building",
    )
    args = parser.parse_args()

    _check_pyinstaller()

    if args.clean:
        print("[build] Cleaning previous build artifacts...")
        shutil.rmtree(DIST, ignore_errors=True)
        shutil.rmtree(BUILD, ignore_errors=True)
        for spec in ROOT.glob("*.spec"):
            spec.unlink()

    exe_name = "termai.exe" if platform.system() == "Windows" else "termai"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", exe_name.removesuffix(".exe"),
        "--strip",
        "--collect-all", "gpt4all",
        "--exclude-module", "tkinter",
        "--exclude-module", "test",
        "--exclude-module", "unittest",
        "--exclude-module", "xmlrpc",
        "--exclude-module", "pydoc",
        "--exclude-module", "doctest",
        "--exclude-module", "lib2to3",
        "--noconfirm",
    ]

    for pkg in ("openai", "anthropic", "httpx", "httpcore", "anyio",
                "pydantic", "pydantic_core", "jiter", "sniffio", "h11",
                "distro", "docstring_parser", "annotated_types",
                "typing_inspection", "typing_extensions"):
        try:
            __import__(pkg)
            cmd.extend(["--hidden-import", pkg])
        except ImportError:
            pass

    if args.bundle_model:
        model_path = MODEL_DIR / BUNDLE_MODEL
        if not model_path.exists():
            print(f"[build] Model not found at {model_path}")
            print(f"[build] Download it first:  termai --setup")
            sys.exit(1)

        cmd.extend([
            "--add-data", f"{model_path}{_sep()}bundled_model",
        ])
        print(f"[build] Bundling model: {BUNDLE_MODEL} ({model_path.stat().st_size / 1e9:.1f} GB)")

    cmd.append(str(ENTRY))

    print(f"[build] Building {exe_name} for {platform.system()} ({platform.machine()})...")
    print(f"[build] Command: {' '.join(cmd)}\n")

    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print(f"\n[build] Build failed (exit code {result.returncode})")
        sys.exit(result.returncode)

    output = DIST / exe_name
    if output.exists():
        size_mb = output.stat().st_size / 1e6
        print(f"\n[build] Success! Executable: {output}")
        print(f"[build] Size: {size_mb:.1f} MB")
        print(f"[build] Run it:  {output}")
    else:
        print(f"\n[build] Warning: expected output at {output} not found")


def _check_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("[build] PyInstaller not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])


def _sep() -> str:
    """Return the PyInstaller --add-data separator for the current OS."""
    return ";" if platform.system() == "Windows" else ":"


if __name__ == "__main__":
    main()
