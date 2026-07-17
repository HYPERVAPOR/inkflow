"""Load and save script.json and script_text.md."""

from __future__ import annotations

import json
from pathlib import Path

from .models import Script, Subtitle


def load_script(path: str | Path) -> Script:
    """Load a script from JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Script.model_validate(data)


def save_script(script: Script, path: str | Path) -> None:
    """Save a script back to JSON file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(script.model_dump(mode="json"), f, ensure_ascii=False, indent=2)


def load_script_text(path: str | Path) -> list[str]:
    """Load plain-text subtitles from script_text.md.

    Returns a list of non-empty subtitle lines.
    """
    text = Path(path).read_text(encoding="utf-8")
    return [line.strip() for line in text.splitlines() if line.strip()]


def build_subtitles_from_text(lines: list[str]) -> list[Subtitle]:
    """Build subtitle objects from plain text lines."""
    return [
        Subtitle(subtitle_id=idx, text=line)
        for idx, line in enumerate(lines, start=1)
    ]
