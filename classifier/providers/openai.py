"""OpenAI provider — calls GPT models with JSON mode enforced for structured output."""

import os

from openai import OpenAI

from .base import LLMProvider


class OpenAIProvider(LLMProvider):
    """Calls OpenAI GPT models. Uses json_object response_format to guarantee valid JSON."""

    def __init__(self) -> None:
        self._model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self._client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def complete(self, system: str, user: str) -> str:
        """Call the OpenAI Chat Completions API and return the response text."""
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=300,
            temperature=0.0,
            # json_object mode prevents the model from wrapping output in markdown fences
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content or ""

    def model_name(self) -> str:
        return self._model

    def provider_name(self) -> str:
        return "openai"
