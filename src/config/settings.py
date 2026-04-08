"""
Application settings loaded from environment variables.

Uses pydantic-settings for type-safe configuration with .env file support.
"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global application configuration."""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM ---
    gemini_api_key: str = ""
    ollama_base_url: str = ""
    llm_model: str = "gemini-2.5-flash-lite"
    llm_temperature: float = 0.0

    # --- Database (existing linux-server-manager PostgreSQL) ---
    database_url: str = "postgresql://lsm_user:lsm_password@localhost:5432/linux_server_manager"

    # --- SSH ---
    ssh_key_path: str = "~/.ssh/id_rsa"
    ssh_default_user: str = "root"
    ssh_timeout: int = 30


# Singleton instance
settings = Settings()
