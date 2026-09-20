from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "django_rag"
    postgres_user: str = "rag_user"
    postgres_password: str = "rag_password"

    user_agent: str = "Mozilla/5.0 (compatible; DjangoRAGBot/1.0)"
    request_delay_seconds: float = 1.0
    cache_dir: Path = Path("data/cache")
    max_pages: int = 60

    base_url: str = "https://docs.djangoproject.com/en/stable/topics/"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
