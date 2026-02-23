"""Local LLM wrapper.

Provides a unified interface for generating text via a local model
(GPT4All / LLaMA / Mistral).  Handles model download, loading, and
graceful fallback when no model is available.

Reads defaults from the global Config.
"""

from __future__ import annotations

import os
from pathlib import Path

from termai.config import get_config

MODEL_DIR = Path(os.environ.get("TERMAI_MODEL_DIR", Path.home() / ".cache" / "gpt4all"))


class LocalModel:
    """Lazy-loading wrapper around a GPT4All model."""

    def __init__(
        self,
        model_name: str | None = None,
        device: str | None = None,
    ) -> None:
        cfg = get_config()
        self._model_name = model_name or cfg.model
        self._device = device or cfg.device
        self._max_tokens = cfg.max_tokens
        self._temperature = cfg.temperature
        self._model = None
        self._available = True

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            from gpt4all import GPT4All  # type: ignore[import-untyped]

            MODEL_DIR.mkdir(parents=True, exist_ok=True)

            model_file = MODEL_DIR / self._model_name
            if not model_file.exists():
                self._available = False
                print(
                    f"\033[0;33m[termai] No local model found.\033[0m\n"
                    "[termai] Using rule-based fallback (works offline, no download).\n"
                    "[termai] To pick and download an AI model, run:\n"
                    "[termai]   termai --setup\n"
                )
                return

            self._model = GPT4All(
                self._model_name,
                model_path=str(MODEL_DIR),
                device=self._device,
                allow_download=False,
            )
        except Exception as e:
            self._available = False
            print(
                f"\033[0;33m[termai] Could not load model '{self._model_name}': {e}\033[0m\n"
                "[termai] Falling back to rule-based command generation.\n"
            )

    @property
    def is_available(self) -> bool:
        if self._model is None and self._available:
            self._load()
        return self._available

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_tokens: int | None = None,
    ) -> str:
        """Generate a completion given a system prompt and user prompt."""
        self._load()
        if self._model is None:
            return ""

        tokens = max_tokens or self._max_tokens
        with self._model.chat_session(system_prompt=system_prompt):
            response: str = self._model.generate(
                user_prompt,
                max_tokens=tokens,
                temp=self._temperature,
                top_k=40,
                top_p=0.9,
                repeat_penalty=1.1,
            )
        return response.strip()

    def chat_generate(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        *,
        max_tokens: int | None = None,
    ) -> str:
        """Multi-turn chat completion.

        *messages* is a list of {"role": "user"|"assistant", "content": "..."} dicts.
        """
        self._load()
        if self._model is None:
            return ""

        tokens = max_tokens or min(self._max_tokens * 2, 1024)
        with self._model.chat_session(system_prompt=system_prompt):
            response = ""
            for msg in messages:
                if msg["role"] == "user":
                    response = self._model.generate(
                        msg["content"],
                        max_tokens=tokens,
                        temp=self._temperature + 0.2,
                        top_k=40,
                        top_p=0.9,
                        repeat_penalty=1.1,
                    )
        return response.strip()


def download_model(model_name: str | None = None) -> None:
    """Download a model. Delegates to the interactive setup in termai.models."""
    from termai.models import interactive_setup
    interactive_setup()
