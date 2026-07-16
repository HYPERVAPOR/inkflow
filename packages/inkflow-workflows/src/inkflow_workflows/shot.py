"""Shot-based Seedance video workflow."""

from __future__ import annotations

import logging
from pathlib import Path

from inkflow_core.models import Script, Shot
from inkflow_core.types import WorkflowOutput
from inkflow_generators.cover import CoverGenerator
from inkflow_generators.image.shot_frame import ShotFrameGenerator
from inkflow_generators.subtitle import SubtitleGenerator
from inkflow_generators.video.seedance import VideoGenerator

from .base import Workflow, WorkflowRegistry

logger = logging.getLogger(__name__)


@WorkflowRegistry.register
class ShotWorkflow(Workflow):
    """Generate a video from Seedance shot clips driven by start-frame images."""

    name = "shot"

    def _compute_shot_durations(self, script: Script) -> dict[int, int]:
        """Compute target video duration in seconds for each shot.

        The duration is the sum of actual scene durations rounded up to the
        nearest integer and capped at the model's per-clip limit (12s).
        """
        max_duration = 12
        durations: dict[int, int] = {}
        for shot in script.shots:
            scenes = script.scenes_for_shot(shot)
            total = sum(s.actual_duration or s.duration_hint or 3.0 for s in scenes)
            rounded = int(total) + (1 if total % 1 > 0 else 0)
            durations[shot.shot_id] = min(max(rounded, 1), max_duration)
        return durations

    def _build_last_frame_map(
        self, script: Script, start_frame_map: dict[int, Path]
    ) -> dict[int, Path]:
        """Build a mapping from shot_id to last-frame image path.

        For shots with transition_to_next=True, the next non-hold shot's start
        frame is used as the last frame to guide Seedance toward a smoother cut.
        """
        last_frame_map: dict[int, Path] = {}
        sorted_shots = sorted(script.shots, key=lambda s: s.shot_id)

        for i, shot in enumerate(sorted_shots):
            if not shot.transition_to_next:
                continue
            # Find the next non-hold shot after this one
            next_shot: Shot | None = None
            for j in range(i + 1, len(sorted_shots)):
                candidate = sorted_shots[j]
                if not candidate.hold_video:
                    next_shot = candidate
                    break
            if next_shot is None:
                continue
            next_frame = start_frame_map.get(next_shot.shot_id)
            if next_frame and next_frame.exists():
                last_frame_map[shot.shot_id] = next_frame
                logger.info(
                    "Shot %s will transition to shot %s start frame as last frame",
                    shot.shot_id,
                    next_shot.shot_id,
                )
        return last_frame_map

    async def run(self, script: Script) -> WorkflowOutput:
        """Generate start frames, cover, shot videos, and subtitles."""
        logger.info("Using shot-based video workflow")

        logger.info("Step 3/5: Generating shot start frames...")
        with ShotFrameGenerator(self.config, self.cost_tracker) as frame_gen:
            start_frame_map = frame_gen.generate(script)

        logger.info("Generating cover images...")
        with CoverGenerator(self.config, self.cost_tracker) as cover_gen:
            cover_gen.generate(script)

        logger.info("Step 4/5: Generating shot videos...")
        shot_durations = self._compute_shot_durations(script)
        last_frame_map = self._build_last_frame_map(script, start_frame_map)
        video_gen = VideoGenerator(self.config, self.cost_tracker)
        await video_gen.generate(script, start_frame_map, shot_durations, last_frame_map)

        logger.info("Step 5/5: Generating subtitles...")
        subtitle_gen = SubtitleGenerator(self.config)
        subtitle_path = subtitle_gen.generate(script)

        return WorkflowOutput(subtitle_path=subtitle_path)
