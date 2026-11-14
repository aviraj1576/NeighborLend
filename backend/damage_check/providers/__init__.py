from ..config import Settings
from ..exceptions import ProviderError
from .base import VisionProvider, parse_view_result
from .gemini import GeminiProvider
from .mock import MockProvider


def provider_from_settings(settings: Settings) -> VisionProvider:
    if settings.provider == "mock":
        return MockProvider()
    if settings.provider == "gemini":
        if not settings.gemini_api_key:
            raise ProviderError("DAMAGE_GEMINI_API_KEY is not set.")
        return GeminiProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            timeout=settings.request_timeout,
            max_retries=settings.max_retries,
        )
    raise ProviderError("Unknown DAMAGE_PROVIDER: %s" % settings.provider)


__all__ = ["VisionProvider", "GeminiProvider", "MockProvider",
           "parse_view_result", "provider_from_settings"]
