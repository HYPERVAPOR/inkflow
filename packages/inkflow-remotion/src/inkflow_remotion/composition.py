"""Build Remotion composition.json from InkFlow script."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from inkflow_core.config import Config
from inkflow_core.models import Script

from .assets import FetchedAsset
from .planner import VisualPlanner

logger = logging.getLogger(__name__)


def _parse_resolution(resolution: str) -> tuple[int, int]:
    """Parse WIDTHxHEIGHT from metadata resolution."""
    parts = resolution.split("x")
    return int(parts[0]), int(parts[1])


class CompositionBuilder:
    """Build composition.json consumed by the Remotion project."""

    def __init__(self, script: Script, config: Config) -> None:
        self.script = script
        self.config = config
        self.width, self.height = _parse_resolution(script.metadata.resolution)
        self.fps = script.metadata.remotion.fps if script.metadata.remotion else 30

    def _shot_duration(self, shot_index: int) -> float:
        """Return total actual duration of all subtitles in a shot."""
        durations: dict[int, float] = getattr(self.script, "_subtitle_durations", {})
        shot = self.script.shots[shot_index]
        return sum(durations.get(i, 3.0) for i in shot.subtitle_indices)

    def _transition_for_shot(self, shot_index: int) -> dict[str, Any] | None:
        """Return the transition config for a shot, falling back to metadata default."""
        shot = self.script.shots[shot_index]
        transition = shot.transition or self.script.metadata.default_transition
        if transition is None:
            return None

        if transition.type == "seedance":
            logger.warning(
                "Seedance transition fallback is not implemented yet; using fade instead."
            )
            transition = transition.model_copy(update={"type": "fade"})

        return transition.model_dump(mode="json")

    def _background_for_shot(
        self, shot_index: int, fetched_assets: list[FetchedAsset]
    ) -> str | None:
        """Determine background color/gradient for a shot."""
        shot = self.script.shots[shot_index]
        if shot.visual.background:
            return shot.visual.background
        # If no image/video asset, use a subtle default background.
        if not fetched_assets:
            return "#1a1a2e"
        return None

    def _build_composition(
        self, shot_index: int, fetched_assets: list[FetchedAsset]
    ) -> dict[str, Any]:
        """Build a single composition entry for a shot."""
        shot = self.script.shots[shot_index]
        duration = self._shot_duration(shot_index)
        duration_in_frames = max(int(duration * self.fps), 1)

        planner = VisualPlanner(self.script, self.width, self.height, self.fps)
        elements = planner.plan(shot, fetched_assets)

        return {
            "id": f"shot-{shot.shot_id}",
            "durationInFrames": duration_in_frames,
            "fps": self.fps,
            "width": self.width,
            "height": self.height,
            "elements": elements,
            "transition": self._transition_for_shot(shot_index),
            "background": self._background_for_shot(shot_index, fetched_assets),
        }

    def build(self, fetched_assets_map: dict[int, list[FetchedAsset]]) -> dict[str, Any]:
        """Return the full composition data structure."""
        compositions = [
            self._build_composition(index, fetched_assets_map.get(index, []))
            for index, shot in enumerate(sorted(self.script.shots, key=lambda s: s.shot_id))
        ]
        return {"compositions": compositions}

    def write(
        self,
        fetched_assets_map: dict[int, list[FetchedAsset]],
        path: Path | None = None,
    ) -> Path:
        """Write composition.json to the Remotion public directory."""
        output_path = path or Path(self.config.REMOTION_PUBLIC_DIR) / "composition.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        data = self.build(fetched_assets_map)
        output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Wrote composition.json with %s compositions", len(data["compositions"]))
        return output_path
