"""Legacy image-based workflow."""

from __future__ import annotations

import logging

from inkflow_core.models import Script
from inkflow_core.types import WorkflowOutput
from inkflow_generators.cover import CoverGenerator
from inkflow_generators.image.seedream import ImageGenerator
from inkflow_generators.subtitle import SubtitleGenerator

from .base import Workflow, WorkflowRegistry

logger = logging.getLogger(__name__)


@WorkflowRegistry.register
class LegacyWorkflow(Workflow):
    """Generate a video from static scene images with Ken Burns motion."""

    name = "legacy"

    async def run(self, script: Script) -> WorkflowOutput:
        """Generate images, cover, and subtitles for the legacy workflow."""
        logger.info("Using legacy image-based workflow")

        logger.info("Step 3/5: Generating images...")
        with ImageGenerator(self.config, self.cost_tracker) as image_gen:
            image_gen.generate(script)

        logger.info("Generating cover images...")
        with CoverGenerator(self.config, self.cost_tracker) as cover_gen:
            cover_gen.generate(script)

        logger.info("Step 5/5: Generating subtitles...")
        subtitle_gen = SubtitleGenerator(self.config)
        subtitle_path = subtitle_gen.generate(script)

        return WorkflowOutput(subtitle_path=subtitle_path)
