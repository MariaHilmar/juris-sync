from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "JurisSync API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    ENV: str = "development"

    # Origens permitidas para CORS. Aceita lista separada por vírgula no .env.
    # "*" libera todas as origens (apenas para desenvolvimento).
    BACKEND_CORS_ORIGINS: list[str] = ["*"]

    # SQLite local por padrão; sobrescreva via .env para PostgreSQL em produção.
    DATABASE_URL: str = "sqlite+aiosqlite:///./juris_sync.db"

    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    DATAJUD_API_KEY: str = ""
    DATAJUD_API_URL: str = "https://api-publica.datajud.cnj.jus.br"

    RAG_TOP_K: int = 3
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4o-mini"

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


settings = Settings()
