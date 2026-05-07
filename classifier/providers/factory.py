"""Instantiates the active LLM provider from the LLM_PROVIDER environment variable."""

import os

from .base import LLMProvider


def get_provider() -> LLMProvider:
    """Return the provider configured by LLM_PROVIDER env var (default: ollama)."""
    name = os.getenv("LLM_PROVIDER", "ollama").lower()
    if name == "ollama":
        from .ollama import OllamaProvider
        return OllamaProvider()
    if name == "anthropic":
        from .anthropic import AnthropicProvider
        return AnthropicProvider()
    if name == "openai":
        from .openai import OpenAIProvider
        return OpenAIProvider()
    raise ValueError(
        f"Unknown LLM_PROVIDER={name!r}. Choose ollama, anthropic, or openai."
    )
