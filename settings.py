"""
settings.py — persistent application settings

Saves to ~/.flashscan_settings.json
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

SETTINGS_FILE = Path.home() / ".flashscan_settings.json"

DEFAULTS: dict = {
    "lastPath":    "",
    "lastOutput":  "",
    "lastFormats": ["MD"],
    "inclHidden":  False,
    "inclSystem":  False,
    "customExts":  [],
}


def load() -> dict:
    try:
        if SETTINGS_FILE.exists():
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            return {**DEFAULTS, **data}
    except Exception as e:
        log.warning("Cannot load settings from %s: %s", SETTINGS_FILE, e)
    return dict(DEFAULTS)


def save(settings: dict) -> None:
    try:
        merged = {**load(), **settings}
        SETTINGS_FILE.write_text(
            json.dumps(merged, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        log.warning("Cannot save settings to %s: %s", SETTINGS_FILE, e)
