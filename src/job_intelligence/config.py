"""Application configuration.

Environment settings come from `.env` / real environment variables via
pydantic-settings. Company adapter configuration comes from `config/companies.yml`
(versioned, derived from verified reconnaissance).
"""

from __future__ import annotations

import functools
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .domain.exceptions import ConfigurationError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"


class Settings(BaseSettings):
    """Environment-driven runtime settings."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = "sqlite:///data/app.db"

    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "job-intelligence"

    dev_job_limit: int = 20
    dev_page_limit: int = 2
    headless: bool = True
    capture_debug_artifacts: bool = False

    scrape_request_timeout_seconds: float = 30.0
    scrape_max_retries: int = 3
    scrape_domain_concurrency: int = 2
    scrape_user_agent: str = (
        "Capgemini-FS-JobIntel-POC/0.1 (internal research)"
    )
    # Safety cap so a runaway paginator can never loop forever.
    scrape_max_pages: int = 500
    scrape_page_delay_seconds: float = 1.0

    proxy_enabled: bool = False
    proxy_provider: str = "brightdata"
    proxy_endpoint: str = ""
    proxy_username: str = ""
    proxy_password: str = ""
    proxy_country: str = "us"
    proxy_session_mode: str = "rotating"
    proxy_max_retries: int = 2

    llm_enabled: bool = False
    llm_provider: str = "anthropic"
    llm_api_key: str = ""
    llm_model: str = "claude-haiku-4-5-20251001"

    @property
    def project_root(self) -> Path:
        return PROJECT_ROOT

    @property
    def debug_dir(self) -> Path:
        return PROJECT_ROOT / "data" / "debug"


# --------------------------------------------------------------------------- #
# Company configuration (config/companies.yml)
# --------------------------------------------------------------------------- #
class CompanyConfig(BaseModel):
    code: str
    name: str
    active: bool = True
    career_site_url: str
    extraction_strategy: str
    proxy_enabled: bool = False
    allowed_domains: list[str] = Field(default_factory=list)
    settings: dict = Field(default_factory=dict)


class CompaniesConfig(BaseModel):
    recon_version: str
    companies: dict[str, CompanyConfig]

    def get(self, key: str) -> CompanyConfig:
        # Accept either the yaml key (wells_fargo) or the code (WELLS_FARGO).
        by_key = self.companies.get(key)
        if by_key is not None:
            return by_key
        for cfg in self.companies.values():
            if cfg.code == key:
                return cfg
        raise ConfigurationError(f"Unknown company: {key!r}")

    def active_keys(self) -> list[str]:
        return [k for k, c in self.companies.items() if c.active]


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


@functools.lru_cache(maxsize=1)
def load_companies_config() -> CompaniesConfig:
    path = CONFIG_DIR / "companies.yml"
    if not path.exists():
        raise ConfigurationError(f"Missing companies config: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return CompaniesConfig.model_validate(data)


def load_yaml_config(name: str) -> dict:
    """Load an arbitrary config/<name> YAML file (skills.yml, roles.yml, ...)."""
    path = CONFIG_DIR / name
    if not path.exists():
        raise ConfigurationError(f"Missing config file: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
