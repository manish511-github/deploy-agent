"""Configuration module — backward-compatibility bridge.

All new code should import from ``src.core.config`` directly.
This module re-exports the settings singleton for existing code.
"""

from src.core.config import get_settings

# Backward compatibility: ``from src.config import settings``
settings = get_settings()

__all__ = ["settings"]
