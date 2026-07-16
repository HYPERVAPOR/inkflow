"""Shared public types for InkFlow packages."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class WorkflowOutput:
    """Output produced by a workflow before final assembly."""

    video_path: Path | None = None
    audio_path: Path | None = None
    subtitle_path: Path | None = None
    scene_clips: list[Path] | None = None
