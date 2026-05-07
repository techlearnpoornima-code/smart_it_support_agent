"""Abstract interface for LLM providers — swap backends without changing classifier code."""

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Shared contract for all LLM backends (Ollama, Anthropic, OpenAI)."""

    @abstractmethod
    def complete(self, system: str, user: str) -> str:
        """Send a system + user message pair and return the model's text response."""
        ...

    @abstractmethod
    def model_name(self) -> str:
        """Return the active model identifier (e.g. 'llama3.2', 'claude-sonnet-4-6')."""
        ...

    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider slug used in event logs (e.g. 'ollama', 'anthropic')."""
        ...
