from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "JurisSync API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    ENV: str = "development"

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

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
