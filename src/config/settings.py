"""Legacy settings module — kept for backward compatibility.

The canonical config is now ``src.core.config``. This file delegates to it.
"""

from src.core.config import Settings, get_settings

settings = get_settings()

__all__ = ["Settings", "settings"]
