"""Anthropic provider — uses Claude via the Anthropic SDK with prompt caching enabled."""

import os

import anthropic

from .base import LLMProvider


class AnthropicProvider(LLMProvider):
    """Calls Claude models. Caches the system prompt to cut repeated-call costs by ~90%."""

    def __init__(self) -> None:
        self._model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        self._client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    def complete(self, system: str, user: str) -> str:
        """Send a request to the Anthropic Messages API with ephemeral system-prompt caching."""
        response = self._client.messages.create(
            model=self._model,
            max_tokens=300,
            system=[
                {
                    "type": "text",
                    "text": system,
                    # ephemeral cache: Anthropic holds this prompt block for up to 5 min,
                    # saving ~90% of input tokens on every repeated classifier call
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text

    def model_name(self) -> str:
        return self._model

    def provider_name(self) -> str:
        return "anthropic"
