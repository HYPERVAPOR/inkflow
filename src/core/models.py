"""Pydantic models for script.json."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Voice(BaseModel):
    """Voice configuration for TTS."""

    voice_id: str | None = None
    speed: float = Field(default=1.2, ge=0.5, le=2.0)
    emotion: str = "neutral"
    provider: Literal["edge_tts", "volcano"] | None = None


class CoverImage(BaseModel):
    """Cover image configuration."""

    prompt: str = ""
    text: str = ""


class Subtitle(BaseModel):
    """A single subtitle line in the video."""

    subtitle_id: int
    text: str
    duration: float | None = None

    # Optional per-subtitle TTS override.
    voice: Voice | None = None


class Shot(BaseModel):
    """A continuous video clip covering one or more subtitles."""

    shot_id: int
    subtitle_ids: list[int] = Field(default_factory=list)
    start_frame_prompt: str = ""
    video_motion_prompt: str = ""
    # null: no reference; "prev": reference previous shot; int: reference shot_id.
    reference_from: int | Literal["prev"] | None = None


class Metadata(BaseModel):
    """Global video metadata."""

    title: str
    width: int = 1920
    height: int = 1080
    aspect_ratio: str = "16:9"
    fps: int = 24
    style_prompt: str = ""
    music_mood: str = "calm"
    music_source: Literal["stock", "ai"] = "stock"
    tags: list[str] = Field(default_factory=list)
    cover_image: CoverImage = Field(default_factory=CoverImage)
    subtitle_style: dict[str, str | int | float] = Field(default_factory=dict)
    burn_subtitles: bool = False

    # Global TTS voice settings. If None, fallback to .env config.
    # Can be overridden per subtitle via subtitle.voice.
    voice: Voice | None = None

    # NOTE: video generation model / resolution / fps / watermark are hardcoded
    # constants in src/generators/video.py (VIDEO_MODEL / VIDEO_RESOLUTION /
    # VIDEO_FPS / VIDEO_WATERMARK) and CANNOT be overridden from script.json.
    # System-level prompt prepended to every video-related prompt.
    video_system_prompt: str = ""


class Script(BaseModel):
    """Root video script model."""

    metadata: Metadata
    subtitles: list[Subtitle] = Field(default_factory=list)
    shots: list[Shot] = Field(default_factory=list)

    @property
    def total_duration(self) -> float:
        """Return total duration based on subtitle durations."""
        return sum(s.duration or 0 for s in self.subtitles)

    def subtitle_by_id(self, subtitle_id: int) -> Subtitle | None:
        """Return subtitle by id."""
        for subtitle in self.subtitles:
            if subtitle.subtitle_id == subtitle_id:
                return subtitle
        return None

    def shot_duration(self, shot: Shot) -> float:
        """Return total duration of all subtitles in a shot."""
        return sum(
            (self.subtitle_by_id(sid) or Subtitle(subtitle_id=sid, text="")).duration or 0
            for sid in shot.subtitle_ids
        )
