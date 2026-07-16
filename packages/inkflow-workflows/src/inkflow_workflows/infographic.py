"""Remotion-based dynamic infographic workflow."""

from __future__ import annotations

import logging
from pathlib import Path

from inkflow_core.models import Script
from inkflow_core.types import WorkflowOutput
from inkflow_generators.cover import CoverGenerator
from inkflow_generators.image.shot_frame import ShotFrameGenerator
from inkflow_generators.subtitle import SubtitleGenerator
from inkflow_remotion import AssetManager, CompositionBuilder, RemotionRenderer

from .base import Workflow, WorkflowRegistry

logger = logging.getLogger(__name__)


@WorkflowRegistry.register
class InfographicWorkflow(Workflow):
    """Generate a video using Remotion dynamic infographics with Seedream assets."""

    name = "infographic"

    def _ensure_shot_prompts(self, script: Script) -> None:
        """Populate empty start_frame_prompt fields for infographic shots."""
        for shot in script.shots:
            if shot.start_frame_prompt:
                continue
            scenes = script.scenes_for_shot(shot)
            text_summary = "，".join(s.subtitle for s in scenes)
            shot.start_frame_prompt = f"信息图背景画面：{text_summary}"

    async def run(self, script: Script) -> WorkflowOutput:
        """Render infographic video via Remotion."""
        logger.info("Using infographic (Remotion) workflow")

        # 1. Ensure every shot has an image prompt, then generate Seedream images.
        logger.info("Step 3/5: Generating Seedream base images...")
        self._ensure_shot_prompts(script)
        with ShotFrameGenerator(self.config, self.cost_tracker) as frame_gen:
            frame_gen.generate(script)

        # 2. Generate cover images.
        logger.info("Generating cover images...")
        with CoverGenerator(self.config, self.cost_tracker) as cover_gen:
            cover_gen.generate(script)

        # 3. Prepare Remotion public/ assets and composition.json.
        logger.info("Step 4/5: Building Remotion composition...")
        asset_manager = AssetManager(self.config)
        asset_manager.prepare(script)

        composer = CompositionBuilder(script, self.config)
        composer.write()

        # 4. Render each shot composition.
        logger.info("Rendering Remotion clips...")
        renderer = RemotionRenderer(self.config)
        clip_paths: list[Path] = []
        for shot in sorted(script.shots, key=lambda s: s.shot_id):
            output = self.config.VIDEOS_DIR / f"shot_{shot.shot_id}.mp4"
            renderer.render(f"shot-{shot.shot_id}", output)
            clip_paths.append(output)

        # 5. Generate subtitles.
        logger.info("Step 5/5: Generating subtitles...")
        subtitle_gen = SubtitleGenerator(self.config)
        subtitle_path = subtitle_gen.generate(script)

        return WorkflowOutput(scene_clips=clip_paths, subtitle_path=subtitle_path)
