"""
Application configuration — single source of truth for all settings.

Uses pydantic-settings for type-safe, validated configuration loaded from
environment variables and .env files.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# ──────────────────────────────────────────────
# Root directory detection
# ──────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Immutable, validated application settings."""

    model_config = SettingsConfigDict(
        env_file=_PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,  # Immutable after creation
    )

    # ── LLM ──────────────────────────────────
    gemini_api_key: str = ""
    openrouter_api_key: str = ""
    ollama_base_url: str = ""
    llm_model: str = "gemini-2.5-flash-lite"
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    llm_provider: Literal["auto", "gemini", "openrouter", "ollama"] = "auto"

    # ── Database ─────────────────────────────
    database_url: str = "postgresql://lsm_user:lsm_password@localhost:5432/linux_server_manager"
    db_pool_min_size: int = Field(default=2, ge=1)
    db_pool_max_size: int = Field(default=10, ge=1)

    # ── SSH ───────────────────────────────────
    ssh_key_path: str = "~/.ssh/id_rsa"
    ssh_default_user: str = "root"
    ssh_timeout: int = Field(default=30, ge=5, le=300)

    # ── MCP ───────────────────────────────────
    mcp_host: str = "0.0.0.0"
    mcp_port: int = Field(default=8811, ge=1024, le=65535)

    @property
    def resolved_llm_provider(self) -> str:
        """Determine which LLM provider to use based on config."""
        if self.llm_provider != "auto":
            return self.llm_provider
        if self.ollama_base_url:
            return "ollama"
        if self.openrouter_api_key:
            return "openrouter"
        return "gemini"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached, singleton Settings instance.

    Using a function (not a module-level global) enables dependency
    injection and test overrides via ``get_settings.cache_clear()``.
    """
    return Settings()
