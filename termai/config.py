"""Configuration management for termai.

Reads settings from (in order of priority):
  1. CLI flags / environment variables
  2. ~/.termai/config.toml (user config)
  3. Built-in defaults

Supported config keys (in [termai] section):
  model       = "Phi-3-mini-4k-instruct.Q4_0.gguf"
  device      = "cpu"          # "cpu", "gpu", "cuda", "amd"
  max_tokens  = 256
  temperature = 0.2
  log_file    = "~/.termai/history.jsonl"
  plugin_dir  = "~/.termai/plugins"
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_DIR = Path.home() / ".termai"
CONFIG_FILE = CONFIG_DIR / "config.toml"


@dataclass
class Config:
    model: str = "Phi-3-mini-4k-instruct.Q4_0.gguf"
    device: str = "cpu"
    max_tokens: int = 256
    temperature: float = 0.2
    log_file: Path = field(default_factory=lambda: CONFIG_DIR / "history.jsonl")
    plugin_dir: Path = field(default_factory=lambda: CONFIG_DIR / "plugins")

    @classmethod
    def load(cls) -> "Config":
        """Load config from file and environment, applying overrides."""
        cfg = cls()

        if CONFIG_FILE.exists():
            cfg._load_toml()

        cfg._apply_env_overrides()
        return cfg

    def _load_toml(self) -> None:
        try:
            import tomllib
        except ModuleNotFoundError:
            try:
                import tomli as tomllib  # type: ignore[no-redef]
            except ModuleNotFoundError:
                return

        try:
            with open(CONFIG_FILE, "rb") as f:
                data = tomllib.load(f)
        except Exception:
            return

        section = data.get("termai", data)

        if "model" in section:
            self.model = str(section["model"])
        if "device" in section:
            self.device = str(section["device"])
        if "max_tokens" in section:
            self.max_tokens = int(section["max_tokens"])
        if "temperature" in section:
            self.temperature = float(section["temperature"])
        if "log_file" in section:
            self.log_file = Path(section["log_file"]).expanduser()
        if "plugin_dir" in section:
            self.plugin_dir = Path(section["plugin_dir"]).expanduser()

    def _apply_env_overrides(self) -> None:
        if v := os.environ.get("TERMAI_MODEL"):
            self.model = v
        if v := os.environ.get("TERMAI_DEVICE"):
            self.device = v
        if v := os.environ.get("TERMAI_MAX_TOKENS"):
            self.max_tokens = int(v)
        if v := os.environ.get("TERMAI_PLUGIN_DIR"):
            self.plugin_dir = Path(v)

    def write_default(self) -> None:
        """Write a default config file if one doesn't exist."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if CONFIG_FILE.exists():
            return
        CONFIG_FILE.write_text(
            '[termai]\n'
            f'model = "{self.model}"\n'
            f'device = "{self.device}"\n'
            f'max_tokens = {self.max_tokens}\n'
            f'temperature = {self.temperature}\n'
        )


_config: Config | None = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config.load()
    return _config
