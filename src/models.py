"""Pydantic models for script.json."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Motion(BaseModel):
    """Simple motion effect configuration."""

    type: Literal["static", "ken_burns"] = "static"
    start: str = "zoom_1.0_pan_0_0"
    end: str = "zoom_1.0_pan_0_0"


class Voice(BaseModel):
    """Voice configuration for TTS."""

    voice_id: str | None = None
    speed: float = Field(default=1.2, ge=0.5, le=2.0)
    emotion: str = "neutral"


class CoverImage(BaseModel):
    """Cover image configuration."""

    prompt: str = ""
    text: str = ""


class Scene(BaseModel):
    """A single scene in the video."""

    scene_id: int
    subtitle: str
    duration_hint: float | None = None

    # Optional per-scene TTS override. If omitted, metadata.voice is used.
    voice: Voice | None = None

    # New shot-based workflow: every scene belongs to a shot.
    # If shot_id is omitted and the script has no shots, the legacy image-based
    # workflow is used (image_prompt/hold_image/motion fields below).
    shot_id: int | None = None

    # Legacy image-based workflow fields (optional).
    image_prompt: str = ""
    use_reference_image: bool = False
    reference_from: int | Literal["prev"] | None = None
    hold_image: bool = False
    motion: Motion = Motion()

    # Filled at runtime
    actual_duration: float | None = None


class Shot(BaseModel):
    """A continuous video clip covering one or more scenes."""

    shot_id: int
    start_frame_prompt: str
    video_motion_prompt: str
    use_reference_image: bool = False
    reference_from: int | Literal["prev"] | None = None
    hold_video: bool = False


class Metadata(BaseModel):
    """Global video metadata."""

    title: str
    target_duration: int | None = None
    resolution: str = "1080x1920"
    aspect_ratio: str = "9:16"
    fps: int = 24
    style_prompt: str = ""
    music_mood: str = "calm"
    music_source: Literal["stock", "ai"] = "stock"
    tags: list[str] = Field(default_factory=list)
    cover_image: CoverImage = Field(default_factory=CoverImage)
    subtitle_style: dict[str, str | int | float] = Field(default_factory=dict)
    burn_subtitles: bool = True

    # Global TTS voice settings. Can be overridden per scene via scene.voice.
    voice: Voice = Voice()

    # Video generation settings
    # Cost guard: only 720p is allowed for Seedance to keep expenses under control.
    video_model: str = "doubao-seedance-1-5-pro-251215"
    video_resolution: Literal["720p"] = "720p"
    video_watermark: bool = False


class Script(BaseModel):
    """Root video script model."""

    scenes: list[Scene]
    metadata: Metadata
    shots: list[Shot] = Field(default_factory=list)

    @property
    def total_duration(self) -> float:
        """Return total duration based on actual scene durations."""
        return sum(s.actual_duration or 0 for s in self.scenes)

    @property
    def uses_shots(self) -> bool:
        """Return True if the script uses the shot-based video workflow."""
        return bool(self.shots) and any(s.shot_id is not None for s in self.scenes)

    def shot_for_scene(self, scene: Scene) -> Shot | None:
        """Return the shot associated with a scene, if any."""
        if scene.shot_id is None:
            return None
        for shot in self.shots:
            if shot.shot_id == scene.shot_id:
                return shot
        return None

    def scenes_for_shot(self, shot: Shot) -> list[Scene]:
        """Return all scenes belonging to a shot, ordered by scene_id."""
        return sorted(
            [s for s in self.scenes if s.shot_id == shot.shot_id],
            key=lambda s: s.scene_id,
        )
