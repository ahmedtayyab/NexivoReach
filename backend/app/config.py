import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "NexivoReach"
    GEMINI_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    SERPER_API_KEY: str = ""
    BRAVE_SEARCH_API_KEY: str = ""
    TAVILY_API_KEY: str = ""
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:3000/api/auth/google/callback"
    JWT_SECRET: str = "dev-only-change-me"
    APP_URL: str = "http://localhost:3000"
    AUTH_DISABLED: bool = False
    DATABASE_URL: str = "sqlite:///./nexivoreach.db"
    GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON: str = ""
    GOOGLE_SHEETS_SPREADSHEET_ID: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()


def effective_app_url() -> str:
    render_url = os.getenv("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
    if render_url:
        return render_url
    return settings.APP_URL.rstrip("/")


def effective_google_redirect_uri() -> str:
    explicit = settings.GOOGLE_REDIRECT_URI.strip()
    if explicit and "localhost" not in explicit:
        return explicit
    return f"{effective_app_url()}/api/auth/google/callback"

