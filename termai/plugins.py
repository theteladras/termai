"""Plugin system for termai.

Plugins are Python modules placed in ~/.termai/plugins/ (or the directory
specified by TERMAI_PLUGIN_DIR).  Each plugin must define a `register()`
function that receives a PluginRegistry and can add:

  - **slash commands** for interactive chat mode
  - **pre-execution hooks** that run before a command is executed
  - **post-execution hooks** that run after a command is executed

Example plugin (~/.termai/plugins/hello.py):

    def register(registry):
        @registry.slash_command("/hello")
        def hello_cmd(args, ctx):
            print("Hello from a plugin!")
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from termai.context import SessionContext

SlashHandler = Callable[[str, "SessionContext"], None]
Hook = Callable[[str, "SessionContext"], str | None]

PLUGIN_DIR = Path(os.environ.get("TERMAI_PLUGIN_DIR", Path.home() / ".termai" / "plugins"))


class PluginRegistry:
    """Central registry that plugins interact with to extend termai."""

    def __init__(self) -> None:
        self._slash_commands: dict[str, SlashHandler] = {}
        self._pre_hooks: list[Hook] = []
        self._post_hooks: list[Hook] = []

    # -- decorators for plugin authors ----------------------------------------

    def slash_command(self, name: str) -> Callable[[SlashHandler], SlashHandler]:
        """Register a slash command handler for interactive chat."""
        def decorator(fn: SlashHandler) -> SlashHandler:
            self._slash_commands[name] = fn
            return fn
        return decorator

    def pre_execute(self, fn: Hook) -> Hook:
        """Register a hook that runs before command execution.

        The hook receives (command, ctx) and may return a modified command
        string or None to keep the original.
        """
        self._pre_hooks.append(fn)
        return fn

    def post_execute(self, fn: Hook) -> Hook:
        """Register a hook that runs after command execution."""
        self._post_hooks.append(fn)
        return fn

    # -- internal API ---------------------------------------------------------

    def get_slash_commands(self) -> dict[str, SlashHandler]:
        return dict(self._slash_commands)

    def run_pre_hooks(self, command: str, ctx: "SessionContext") -> str:
        for hook in self._pre_hooks:
            result = hook(command, ctx)
            if result is not None:
                command = result
        return command

    def run_post_hooks(self, command: str, ctx: "SessionContext") -> None:
        for hook in self._post_hooks:
            hook(command, ctx)


_registry: PluginRegistry | None = None


def get_registry() -> PluginRegistry:
    """Return the global plugin registry, loading plugins on first call."""
    global _registry
    if _registry is None:
        _registry = PluginRegistry()
        _load_plugins(_registry)
    return _registry


def _load_plugins(registry: PluginRegistry) -> None:
    """Discover and load plugin modules from the plugin directory."""
    if not PLUGIN_DIR.is_dir():
        return

    for path in sorted(PLUGIN_DIR.glob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"termai_plugin_{path.stem}", path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)

            register_fn = getattr(module, "register", None)
            if callable(register_fn):
                register_fn(registry)

        except Exception as e:
            print(f"\033[0;33m[termai] Failed to load plugin {path.name}: {e}\033[0m")
