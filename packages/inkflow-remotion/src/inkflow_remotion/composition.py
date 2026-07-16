"""Build Remotion composition.json from InkFlow script."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from inkflow_core.config import Config
from inkflow_core.models import CompositionElement, Scene, Script, Shot, TransitionConfig

logger = logging.getLogger(__name__)


def _parse_resolution(resolution: str) -> tuple[int, int]:
    """Parse WIDTHxHEIGHT from metadata resolution."""
    parts = resolution.split("x")
    return int(parts[0]), int(parts[1])


def _shot_duration(shot: Shot, script: Script) -> float:
    """Return total actual duration of all scenes in a shot."""
    scenes = script.scenes_for_shot(shot)
    return sum(s.actual_duration or s.duration_hint or 3.0 for s in scenes)


def _build_text_element(scene: Scene, index: int) -> CompositionElement:
    """Create a text element from a scene subtitle."""
    return CompositionElement(
        id=f"text_{scene.scene_id}",
        type="text",
        props={
            "text": scene.subtitle,
            "fontSize": 48,
            "color": "#ffffff",
            "textAlign": "center",
        },
        layout={
            "x": 0,
            "y": 1200,
            "width": "100%",
            "height": 200,
        },
        animation={
            "type": "fade_in",
            "duration": 0.5,
            "delay": index * 0.3,
        },
    )


def _build_seedream_element(shot: Shot, image_filename: str) -> CompositionElement:
    """Create a Seedream image element for a shot."""
    return CompositionElement(
        id=f"image_{shot.shot_id}",
        type="seedream_image",
        props={"src": image_filename},
        layout={
            "x": 0,
            "y": 0,
            "width": "100%",
            "height": "100%",
        },
        animation={"type": "fade_in", "duration": 0.6},
    )


def _transition_for_shot(shot: Shot, script: Script) -> TransitionConfig | None:
    """Return the transition config for a shot, falling back to metadata default."""
    if shot.composition and shot.composition.transition:
        return shot.composition.transition
    return script.metadata.default_transition


class CompositionBuilder:
    """Build composition.json consumed by the Remotion project."""

    def __init__(self, script: Script, config: Config) -> None:
        self.script = script
        self.config = config
        self.width, self.height = _parse_resolution(script.metadata.resolution)
        self.fps = script.metadata.remotion.fps if script.metadata.remotion else 30

    def _build_composition(self, shot: Shot, index: int) -> dict[str, Any]:
        """Build a single composition entry for a shot."""
        duration = _shot_duration(shot, self.script)
        duration_in_frames = max(int(duration * self.fps), 1)

        elements: list[CompositionElement] = []

        # Add Seedream image if a start frame was generated for this shot.
        image_filename = f"shot_{shot.shot_id}.png"
        image_path = self.config.IMAGES_DIR / image_filename
        if image_path.exists():
            elements.append(_build_seedream_element(shot, image_filename))

        # Add text elements for each scene in the shot.
        scenes = self.script.scenes_for_shot(shot)
        for scene_index, scene in enumerate(scenes):
            elements.append(_build_text_element(scene, scene_index))

        # Use user-defined composition elements if provided.
        if shot.composition and shot.composition.elements:
            elements = shot.composition.elements

        transition = _transition_for_shot(shot, self.script)
        background = (
            shot.composition.background
            if shot.composition and shot.composition.background
            else None
        )

        return {
            "id": f"shot-{shot.shot_id}",
            "durationInFrames": duration_in_frames,
            "fps": self.fps,
            "width": self.width,
            "height": self.height,
            "elements": [e.model_dump(mode="json") for e in elements],
            "transition": transition.model_dump(mode="json") if transition else None,
            "background": background,
        }

    def build(self) -> dict[str, Any]:
        """Return the full composition data structure."""
        compositions = [
            self._build_composition(shot, index)
            for index, shot in enumerate(sorted(self.script.shots, key=lambda s: s.shot_id))
        ]
        return {"compositions": compositions}

    def write(self, path: Path | None = None) -> Path:
        """Write composition.json to the Remotion public directory."""
        output_path = path or Path(self.config.REMOTION_PUBLIC_DIR) / "composition.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        data = self.build()
        output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Wrote composition.json with %s compositions", len(data["compositions"]))
        return output_path
