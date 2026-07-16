"""Remotion-based dynamic infographic workflow."""

from __future__ import annotations

import logging

from inkflow_core.models import Script
from inkflow_core.types import WorkflowOutput

from .base import Workflow, WorkflowRegistry

logger = logging.getLogger(__name__)


@WorkflowRegistry.register
class InfographicWorkflow(Workflow):
    """Generate a video using Remotion dynamic infographics with Seedream assets."""

    name = "infographic"

    async def run(self, script: Script) -> WorkflowOutput:
        """Render infographic video via Remotion."""
        logger.info("Using infographic (Remotion) workflow")
        raise NotImplementedError(
            "Infographic workflow is not implemented yet. "
            "Complete Phase 3 to enable Remotion rendering."
        )
