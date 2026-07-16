"""Subtitle generation based on scene durations."""

from __future__ import annotations

from pathlib import Path

from inkflow_core.config import Config
from inkflow_core.models import Scene, Script


def _format_srt_time(seconds: float) -> str:
    """Format seconds as SRT timecode HH:MM:SS,mmm."""
    millis = int((seconds % 1) * 1000)
    total_seconds = int(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


class SubtitleGenerator:
    """Generate SRT subtitle files."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config

    def _scene_to_entry(self, index: int, scene: Scene, start: float, end: float) -> str:
        """Create a single SRT entry."""
        return (
            f"{index}\n"
            f"{_format_srt_time(start)} --> {_format_srt_time(end)}\n"
            f"{scene.subtitle}\n"
        )

    def generate(self, script: Script, output_path: str | Path | None = None) -> Path:
        """Generate SRT file from script scenes."""
        output_path = Path(output_path or Path(self.config.SUBTITLES_DIR) / "caption.srt")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        entries = []
        current_time = 0.0
        for idx, scene in enumerate(script.scenes, start=1):
            duration = scene.actual_duration or scene.duration_hint or 3.0
            start = current_time
            end = current_time + duration
            entries.append(self._scene_to_entry(idx, scene, start, end))
            current_time = end

        output_path.write_text("\n".join(entries), encoding="utf-8")
        return output_path
