"""Ollama provider — runs local models via Ollama's OpenAI-compatible REST endpoint."""

import os

from openai import OpenAI

from .base import LLMProvider


class OllamaProvider(LLMProvider):
    """Calls a locally running Ollama instance. No API key or network cost required."""

    def __init__(self) -> None:
        # Ollama exposes an OpenAI-compatible /v1 endpoint, so we reuse the OpenAI SDK
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434") + "/v1"
        self._model = os.getenv("OLLAMA_MODEL", "llama3.2")
        self._client = OpenAI(base_url=base_url, api_key="ollama")  # api_key ignored by Ollama

    def complete(self, system: str, user: str) -> str:
        """Call the local Ollama chat endpoint and return the response text."""
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=300,
            temperature=0.0,
        )
        return response.choices[0].message.content or ""

    def model_name(self) -> str:
        return self._model

    def provider_name(self) -> str:
        return "ollama"
