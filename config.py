"""Configuration management for DeskMate Zero.

Cities and settings persist in config.json so user changes survive reboots.
"""

import copy
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "base_dir": "/home/rpi/weather_app",
    "pictures_dir": "/home/rpi/pictures",
    "icon_subdir": "weather_icons",
    "refresh_interval": 1800,
    "city_limit": 10,
    "lock_double_tap_seconds": 0.2,
    "slideshow_minutes": 60,
    "cities": [
        {
            "name": "New York City",
            "lat": 40.7128,
            "lon": -74.0060,
            "timezone": "America/New_York",
        }
    ],
}

_CONFIG_PATH = Path(__file__).parent / "config.json"


def load_config() -> dict:
    """Load config from disk or return defaults."""
    if _CONFIG_PATH.exists():
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            merged = copy.deepcopy(DEFAULT_CONFIG)
            merged.update(data)
            return merged
        except Exception as exc:
            logger.warning("Failed to load config: %s. Using defaults.", exc)
    return copy.deepcopy(DEFAULT_CONFIG)


def save_config(config: dict) -> None:
    """Write config to disk."""
    try:
        with open(_CONFIG_PATH, "w", encoding="utf-8") as fh:
            json.dump(config, fh, indent=2)
    except Exception as exc:
        logger.error("Failed to save config: %s", exc)


def get_icon_path(config: dict) -> Path:
    """Return resolved icon folder path."""
    return Path(config["base_dir"]) / config["icon_subdir"]
