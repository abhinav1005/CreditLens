"""LLM providers behind one small interface. `get_provider(model)` picks by config."""

from assistant.config import Config, load_config
from assistant.providers.base import Provider, ProviderRequest, ProviderResponse, ToolCall

__all__ = ["Provider", "ProviderRequest", "ProviderResponse", "ToolCall", "get_provider"]


def get_provider(model: str, config: Config | None = None) -> Provider:
    config = config or load_config()
    model_config = config.model_config_for(model)
    if model_config.provider == "anthropic":
        from dotenv import load_dotenv

        from assistant.providers.anthropic_provider import AnthropicProvider

        load_dotenv()
        return AnthropicProvider(model_config)
    raise ValueError(f"unsupported provider {model_config.provider!r} for {model}")
