"""Application configuration loaded from environment variables.

Uses pydantic-settings: every field can be overridden via a `.env` file
or real environment variables (env var names are case-insensitive
matches of the field names, e.g. POSTGRES_HOST).

Why this approach: no credential or environment-specific value is ever
hardcoded in the source (task requirement) — the committed defaults are
only fall-backs, real secrets live in the git-ignored `.env`.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Tell pydantic to read a `.env` file in the working directory.
    # `extra="ignore"` makes unknown keys in .env harmless instead of
    # raising a validation error (useful when .env holds values for
    # other tools too).
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- PostgreSQL ---
    # Defaults describe a typical local dev setup; the real values used
    # for this project live in .env (the container is exposed on 5433
    # because the local Windows PostgreSQL service already owns 5432).
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "django_rag"
    postgres_user: str = "rag_user"
    postgres_password: int = 123

    # --- Crawler ---
    # Custom, identifiable User-Agent: polite crawling practice (task
    # requirement) so the docs site can recognize and rate-limit us.
    user_agent: str = "Mozilla/5.0 (compatible; DjangoRAGBot/1.0)"
    # Minimum delay between consecutive HTTP requests — be a good
    # citizen towards docs.djangoproject.com.
    request_delay_seconds: float = 1.0
    # Disk cache for downloaded HTML: re-runs hit the disk, not the site.
    cache_dir: Path = Path("data/cache")
    # Hard cap on pages crawled per run (task suggests 40-80 pages).
    max_pages: int = 60
    # Entry point of the corpus: the Topics section of the Django docs.
    base_url: str = "https://docs.djangoproject.com/en/stable/topics/"

    # --- MCP server (read-only user) ---
    # The MCP server connects with a dedicated SELECT-only database
    # user, so even a malicious/buggy tool call can never mutate data.
    mcp_db_user: str = "rag_readonly"
    mcp_db_password: str = ""
    # Security cap: a client can never request more than this many
    # search results in one call (prevents k=10000 abuse).
    mcp_max_k: int = 10
    # Security cap: maximum characters of page/chunk content returned
    # to the client, applied via _clip() — a 67k-char page must not
    # blow up the client's context window.
    mcp_max_content_chars: int = 4000

    @property
    def database_url(self) -> str:
        """Build the SQLAlchemy connection URL for the *main* (read-write)
        connection used by the crawler/indexer.

        NOTE: this URL contains the password — never log it. For the
        MCP server use get_readonly_engine() in app/storage/database.py
        instead, which uses the dedicated read-only credentials.
        """
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


# Single module-level instance — imported everywhere as `settings`.
# pydantic reads .env at import time, so all modules see the same config.
settings = Settings()
