from app.providers.base import AIProvider
from app.providers.gemini import GeminiProvider
from app.providers.groq_provider import GroqProvider
from app.providers.fallback import FallbackProvider
from app.config import settings


def get_ai_provider() -> AIProvider:
    if settings.GEMINI_API_KEY:
        return GeminiProvider()
    if settings.GROQ_API_KEY:
        return GroqProvider()
    return FallbackProvider()
