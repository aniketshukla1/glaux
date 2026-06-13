"""Athena LLM gateway."""

from .gateway import AnthropicClient, LLMClient, LLMResponse, Message, ScriptedLLM
from .ollama import OllamaClient, ollama_status
from .providers import (
    PROVIDERS,
    LLMError,
    OpenAICompatibleClient,
    Provider,
    key_available,
    make_client,
    provider_catalog,
)

__all__ = [
    "LLMClient",
    "LLMResponse",
    "Message",
    "ScriptedLLM",
    "AnthropicClient",
    "OllamaClient",
    "ollama_status",
    "OpenAICompatibleClient",
    "Provider",
    "PROVIDERS",
    "LLMError",
    "provider_catalog",
    "make_client",
    "key_available",
]
