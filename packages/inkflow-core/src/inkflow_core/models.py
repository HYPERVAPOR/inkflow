"""Pydantic models for declarative video scripts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Motion(BaseModel):
    """Simple motion effect configuration (legacy workflow)."""

    type: Literal["static", "ken_burns"] = "static"
    start: str = "zoom_1.0_pan_0_0"
    end: str = "zoom_1.0_pan_0_0"


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


class TransitionConfig(BaseModel):
    """Transition configuration between shots."""

    type: Literal["none", "fade", "slide", "shader", "seedance"] = "fade"
    name: str | None = None
    duration: float = 0.5
    direction: Literal["left", "right", "top", "bottom"] | None = None


class Asset(BaseModel):
    """A declarative asset required by a shot."""

    id: str
    type: Literal[
        "seedream_image",
        "seedance_video",
        "image_url",
        "video_url",
        "local_image",
        "local_video",
    ]
    description: str = ""
    url: str | None = None


class VisualPlan(BaseModel):
    """Declarative description of what a shot should look like."""

    description: str = ""
    style: str = "infographic"
    background: str | None = None
    assets: list[Asset] = Field(default_factory=list)
    motion: Motion = Field(default_factory=Motion)


class Shot(BaseModel):
    """A continuous visual clip covering one or more subtitle lines."""

    shot_id: int
    subtitle_indices: list[int] = Field(default_factory=list)
    visual: VisualPlan = Field(default_factory=VisualPlan)
    transition: TransitionConfig | None = None

    # Legacy / shot-workflow fields. Optional in the new declarative format.
    start_frame_prompt: str = ""
    video_motion_prompt: str = ""
    use_reference_image: bool = False
    reference_from: str | int | None = None
    hold_video: bool = False
    transition_to_next: bool = False


class RemotionConfig(BaseModel):
    """Global Remotion rendering configuration."""

    fps: int = 30
    scale: float = 1.0
    concurrency: int = 1
    browser_executable: str | None = None


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

    # Global TTS voice settings.
    voice: Voice = Field(default_factory=Voice)

    # Video generation settings for shot/legacy workflows.
    video_model: str = "doubao-seedance-1-5-pro-251215"
    video_resolution: Literal["720p"] = "720p"
    video_watermark: bool = False
    video_system_prompt: str = ""

    # Workflow selection. When omitted, the workflow is auto-detected.
    workflow: Literal["legacy", "shot", "infographic"] | None = None

    # Infographic / Remotion workflow configuration.
    remotion: RemotionConfig | None = None
    default_transition: TransitionConfig | None = None


class Script(BaseModel):
    """Root video script model."""

    metadata: Metadata
    subtitles: list[str] = Field(default_factory=list)
    shots: list[Shot] = Field(default_factory=list)

    def subtitles_for_shot(self, shot: Shot) -> list[str]:
        """Return subtitle texts belonging to a shot."""
        return [self.subtitles[i] for i in shot.subtitle_indices if 0 <= i < len(self.subtitles)]

    def shot_duration(
        self, shot: Shot, subtitle_durations: dict[int, float] | None = None
    ) -> float:
        """Return total duration of a shot from its subtitle durations."""
        durations = subtitle_durations or getattr(self, "_subtitle_durations", {})
        return sum(durations.get(i, 3.0) for i in shot.subtitle_indices)

    @property
    def uses_shots(self) -> bool:
        """Return True if the script has shots defined."""
        return bool(self.shots)

    @property
    def resolved_workflow(self) -> Literal["legacy", "shot", "infographic"]:
        """Return the resolved workflow name for this script."""
        if self.metadata.workflow:
            return self.metadata.workflow
        return "shot" if self.uses_shots else "legacy"
