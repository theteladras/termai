"""Remote AI provider integration (OpenAI, Claude).

Provides a unified interface for remote LLM providers. Each provider
wraps the official SDK and handles errors, timeouts, and rate limits
gracefully. Providers are lazily imported — users who never configure
a remote key won't need the SDK installed.
"""

from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from termai.config import Config

CYAN = "\033[1;36m"
DIM = "\033[2m"
YELLOW = "\033[0;33m"
RED = "\033[1;31m"
RESET = "\033[0m"

OPENAI_MODELS = [
    {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "description": "Fast and affordable"},
    {"id": "gpt-4o", "name": "GPT-4o", "description": "Most capable"},
    {"id": "gpt-4.1-mini", "name": "GPT-4.1 Mini", "description": "Latest mini model"},
    {"id": "gpt-4.1", "name": "GPT-4.1", "description": "Latest flagship"},
]

CLAUDE_MODELS = [
    {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4", "description": "Balanced speed and quality"},
    {"id": "claude-haiku-3-5-20241022", "name": "Claude 3.5 Haiku", "description": "Fast and affordable"},
    {"id": "claude-opus-4-20250514", "name": "Claude Opus 4", "description": "Most capable"},
]


class RemoteProvider(ABC):
    """Base class for remote AI providers."""

    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str, *, max_tokens: int = 512) -> str:
        """Single-turn command generation."""

    @abstractmethod
    def chat_generate(self, system_prompt: str, messages: list[dict[str, str]], *, max_tokens: int = 512) -> str:
        """Multi-turn chat completion."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is configured and reachable."""

    @abstractmethod
    def test_connection(self) -> tuple[bool, str]:
        """Test the API connection. Returns (success, message)."""


class OpenAIProvider(RemoteProvider):
    def __init__(self, api_key: str, model: str = "gpt-4o-mini", timeout: int = 30):
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self._api_key, timeout=self._timeout)
            except ImportError:
                print(f"{YELLOW}[termai] openai package not installed. Run: pip install openai{RESET}")
                raise
        return self._client

    def generate(self, system_prompt: str, user_prompt: str, *, max_tokens: int = 512) -> str:
        client = self._get_client()
        resp = client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
            temperature=0.2,
        )
        return resp.choices[0].message.content.strip()

    def chat_generate(self, system_prompt: str, messages: list[dict[str, str]], *, max_tokens: int = 512) -> str:
        client = self._get_client()
        api_messages = [{"role": "system", "content": system_prompt}]
        api_messages.extend(messages)
        resp = client.chat.completions.create(
            model=self._model,
            messages=api_messages,
            max_tokens=max_tokens,
            temperature=0.3,
        )
        return resp.choices[0].message.content.strip()

    def is_available(self) -> bool:
        return bool(self._api_key)

    def test_connection(self) -> tuple[bool, str]:
        try:
            client = self._get_client()
            resp = client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": "Say 'ok'"}],
                max_tokens=5,
            )
            return True, f"Connected to OpenAI ({self._model})"
        except Exception as e:
            return False, str(e)


class ClaudeProvider(RemoteProvider):
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514", timeout: int = 30):
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from anthropic import Anthropic
                self._client = Anthropic(api_key=self._api_key, timeout=self._timeout)
            except ImportError:
                print(f"{YELLOW}[termai] anthropic package not installed. Run: pip install anthropic{RESET}")
                raise
        return self._client

    def generate(self, system_prompt: str, user_prompt: str, *, max_tokens: int = 512) -> str:
        client = self._get_client()
        resp = client.messages.create(
            model=self._model,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            max_tokens=max_tokens,
        )
        return resp.content[0].text.strip()

    def chat_generate(self, system_prompt: str, messages: list[dict[str, str]], *, max_tokens: int = 512) -> str:
        client = self._get_client()
        resp = client.messages.create(
            model=self._model,
            system=system_prompt,
            messages=messages,
            max_tokens=max_tokens,
        )
        return resp.content[0].text.strip()

    def is_available(self) -> bool:
        return bool(self._api_key)

    def test_connection(self) -> tuple[bool, str]:
        try:
            client = self._get_client()
            resp = client.messages.create(
                model=self._model,
                messages=[{"role": "user", "content": "Say 'ok'"}],
                max_tokens=5,
            )
            return True, f"Connected to Claude ({self._model})"
        except Exception as e:
            return False, str(e)


_remote: RemoteProvider | None = None
_remote_loaded = False


def get_remote_provider() -> RemoteProvider | None:
    """Return the configured remote provider, or None if not set up."""
    global _remote, _remote_loaded
    if _remote_loaded:
        return _remote
    _remote_loaded = True

    from termai.config import get_config
    cfg = get_config()

    if not cfg.remote_provider:
        return None

    try:
        if cfg.remote_provider == "openai" and cfg.openai_api_key:
            _remote = OpenAIProvider(
                api_key=cfg.openai_api_key,
                model=cfg.remote_model or "gpt-4o-mini",
                timeout=cfg.remote_timeout,
            )
        elif cfg.remote_provider == "claude" and cfg.claude_api_key:
            _remote = ClaudeProvider(
                api_key=cfg.claude_api_key,
                model=cfg.remote_model or "claude-sonnet-4-20250514",
                timeout=cfg.remote_timeout,
            )
    except ImportError:
        _remote = None

    return _remote


def reset_remote_provider() -> None:
    """Force re-initialization of the remote provider (after config change)."""
    global _remote, _remote_loaded
    _remote = None
    _remote_loaded = False
