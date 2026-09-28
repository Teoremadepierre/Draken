"""Application configuration.

Everything is driven by environment variables prefixed with ``DRAKEN_`` so the
same image can run locally, in Docker, or on a private VPS without code edits.
"""

from __future__ import annotations

import functools
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data"
SEEDS_DIR = DATA_DIR / "seeds"
FRONTEND_DIR = REPO_ROOT / "frontend"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DRAKEN_",
        env_file=(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- core ---------------------------------------------------------------
    env: str = "development"
    secret_key: str = "dev-only-insecure-secret-key"
    host: str = "127.0.0.1"
    port: int = 8000
    database_url: str = f"sqlite:///{DATA_DIR / 'draken.db'}"

    # --- auth ---------------------------------------------------------------
    auth_enabled: bool = False
    admin_user: str = "admin"
    admin_password_hash: str = ""
    # Plain-text alternative for platforms where you type env vars into a
    # dashboard (Render, Fly, Railway) and hashing first is awkward. The hash is
    # still preferred: it never puts the password itself in the environment.
    admin_password: str = ""
    session_ttl_hours: int = 72

    # --- crawler ------------------------------------------------------------
    user_agent: str = "DrakenSEO/0.1 (+https://example.com/bot)"
    respect_robots: bool = True
    crawl_concurrency: int = 5
    crawl_delay_seconds: float = 0.5
    request_timeout: float = 20.0
    max_pages_per_audit: int = 500

    # --- keyword / SERP providers ------------------------------------------
    suggest_providers: str = "google,bing,duckduckgo"
    serp_provider: str = ""          # pin one; empty = best available
    serpapi_key: str = ""
    dataforseo_login: str = ""
    dataforseo_password: str = ""
    brave_api_key: str = ""          # free tier: 2,000 queries/month
    searxng_url: str = ""            # your own SearXNG instance

    # --- first-party data (real, measured - not estimates) ------------------
    gsc_service_account_file: str = ""
    # The key file's contents, for platforms with no writable disk where you
    # paste the JSON straight into an environment variable.
    gsc_service_account_json: str = ""
    gsc_client_id: str = ""
    gsc_client_secret: str = ""
    gsc_refresh_token: str = ""
    gsc_site_url: str = ""           # e.g. sc-domain:example.com
    bing_webmaster_api_key: str = ""
    bing_site_url: str = ""

    # --- backlink providers -------------------------------------------------
    commoncrawl_enabled: bool = True
    openpagerank_key: str = ""

    # --- AI visibility engines ---------------------------------------------
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    perplexity_api_key: str = ""
    gemini_api_key: str = ""

    # --- outreach -----------------------------------------------------------
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    outreach_send_enabled: bool = False

    # --- submission safety rails -------------------------------------------
    submissions_dry_run: bool = True
    submissions_require_approval: bool = True
    submissions_per_domain_daily_cap: int = 1
    submissions_global_daily_cap: int = 25

    # --- misc ---------------------------------------------------------------
    cors_origins: str = "*"
    log_level: str = "INFO"
    scheduler_enabled: bool = Field(default=True)

    @field_validator("database_url")
    @classmethod
    def _ensure_sqlite_dir(cls, v: str) -> str:
        if v.startswith("sqlite"):
            # sqlite:///relative/path or sqlite:////absolute/path
            raw = v.split("sqlite:///", 1)[-1]
            # An in-memory database has no directory; resolving it would create
            # a file literally named ":memory:" in the repository.
            if not raw or raw.startswith(":memory:") or raw.startswith("file:"):
                return v
            path = Path(raw)
            if not path.is_absolute():
                path = (REPO_ROOT / raw).resolve()
                v = f"sqlite:///{path}"
            path.parent.mkdir(parents=True, exist_ok=True)
        return v

    @property
    def suggest_provider_list(self) -> list[str]:
        return [p.strip() for p in self.suggest_providers.split(",") if p.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def has_admin_credentials(self) -> bool:
        return bool(self.admin_password_hash or self.admin_password)

    @property
    def is_production(self) -> bool:
        return self.env.lower() in {"production", "prod"}

    def first_party_data_configured(self) -> dict[str, bool]:
        """Sources that return measured data about your own site, not estimates."""
        from pathlib import Path as _Path

        gsc = bool(
            (self.gsc_service_account_file and _Path(self.gsc_service_account_file).exists())
            or self.gsc_service_account_json.strip()
            or (self.gsc_client_id and self.gsc_client_secret and self.gsc_refresh_token)
        )
        return {
            "search_console": gsc,
            "bing_webmaster": bool(self.bing_webmaster_api_key),
        }

    def ai_engines_configured(self) -> dict[str, bool]:
        return {
            "anthropic": bool(self.anthropic_api_key),
            "openai": bool(self.openai_api_key),
            "perplexity": bool(self.perplexity_api_key),
            "gemini": bool(self.gemini_api_key),
        }


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
