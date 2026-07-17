"""Audio utilities."""

from __future__ import annotations

from pathlib import Path

from pydub import AudioSegment  # type: ignore[import-untyped]


def get_duration(audio_path: Path) -> float:
    """Return audio duration in seconds."""
    audio = AudioSegment.from_file(audio_path)
    return len(audio) / 1000.0
