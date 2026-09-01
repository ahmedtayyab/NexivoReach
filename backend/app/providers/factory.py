from app.providers.base import AIProvider
from app.providers.gemini import GeminiProvider
from app.providers.fallback import FallbackProvider
from app.config import settings

def get_ai_provider() -> AIProvider:
    if settings.GEMINI_API_KEY:
        return GeminiProvider()
    return FallbackProvider()
