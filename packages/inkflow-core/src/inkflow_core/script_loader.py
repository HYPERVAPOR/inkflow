"""Load and validate script.json."""

import json
from pathlib import Path

from .models import Script


def load_script(path: str | Path) -> Script:
    """Load a script from JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Script.model_validate(data)


def save_script(script: Script, path: str | Path) -> None:
    """Save a script back to JSON file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(script.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
