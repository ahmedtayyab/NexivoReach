import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent


def _resolve_database_url(raw: str) -> str:
    """
    Normalize DATABASE_URL for local SQLite and hosted Postgres.

    - Relative sqlite paths are pinned to the backend folder (cwd-safe).
    - Render/Heroku style postgres:// is rewritten to postgresql+psycopg2://
    - Hosted Postgres gets sslmode=require when missing (Render needs this).
    """
    url = (raw or "").strip() or "sqlite:///./nexivoreach.db"

    if url.startswith("postgres://"):
        url = "postgresql+psycopg2://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    elif url.startswith("postgresql+psycopg2://"):
        pass
    elif url.startswith("sqlite:///"):
        path_part = url[len("sqlite:///"):]
        if path_part.startswith("/") or (len(path_part) > 2 and path_part[1] == ":"):
            return url
        abs_path = (_BACKEND_DIR / path_part.lstrip("./")).resolve()
        return f"sqlite:///{abs_path.as_posix()}"
    else:
        return url

    # Require TLS for remote Postgres (Render, most managed hosts).
    lower = url.lower()
    local = "localhost" in lower or "127.0.0.1" in lower
    if not local and "sslmode=" not in lower:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}sslmode=require"
    return url


def database_backend(url: str | None = None) -> str:
    u = (url or "").strip()
    if not u:
        u = settings.DATABASE_URL
    if u.startswith("sqlite"):
        return "sqlite"
    if "postgres" in u:
        return "postgres"
    return "other"


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
    # Local default: SQLite. Production (Render): managed Postgres via DATABASE_URL.
    DATABASE_URL: str = "sqlite:///./nexivoreach.db"
    GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON: str = ""
    GOOGLE_SHEETS_SPREADSHEET_ID: str = ""

    model_config = SettingsConfigDict(
        env_file=str(_BACKEND_DIR / ".env"),
        extra="ignore",
    )


_settings = Settings()
_settings.DATABASE_URL = _resolve_database_url(
    os.getenv("DATABASE_URL", _settings.DATABASE_URL)
)
settings = _settings


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
