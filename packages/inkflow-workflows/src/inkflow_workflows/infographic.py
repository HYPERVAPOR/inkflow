"""Remotion-based dynamic infographic workflow."""

from __future__ import annotations

import logging
from pathlib import Path

from inkflow_core.models import Script
from inkflow_core.types import WorkflowOutput
from inkflow_generators.cover import CoverGenerator
from inkflow_generators.subtitle import SubtitleGenerator
from inkflow_remotion import AssetFetcher, CompositionBuilder, FetchedAsset, RemotionRenderer

from .base import Workflow, WorkflowRegistry

logger = logging.getLogger(__name__)


@WorkflowRegistry.register
class InfographicWorkflow(Workflow):
    """Generate a video using Remotion dynamic infographics with Seedream assets."""

    name = "infographic"

    async def run(self, script: Script) -> WorkflowOutput:
        """Render infographic video via Remotion."""
        logger.info("Using infographic (Remotion) workflow")

        # 1. Resolve all assets and copy them into Remotion public/.
        logger.info("Step 3/5: Fetching assets for infographic...")
        fetched_assets: dict[int, list[FetchedAsset]] = {}
        with AssetFetcher(self.config) as fetcher:
            fetcher.prepare_public_dir()
            for index in range(len(script.shots)):
                fetched_assets[index] = fetcher.fetch_for_shot(script, index)
            fetcher.write_manifest(script)

        # 2. Generate cover images.
        logger.info("Generating cover images...")
        with CoverGenerator(self.config, self.cost_tracker) as cover_gen:
            cover_gen.generate(script)

        # 3. Build Remotion composition.json.
        logger.info("Step 4/5: Building Remotion composition...")
        composer = CompositionBuilder(script, self.config)
        composer.write(fetched_assets)

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
