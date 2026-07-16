"""Render Remotion compositions via CLI."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from inkflow_core.config import Config

logger = logging.getLogger(__name__)


class RemotionRenderer:
    """Shell out to npx remotion render to produce MP4 clips."""

    def __init__(self, config: Config) -> None:
        self.config = config

    def render(self, composition_id: str, output_path: Path) -> Path:
        """Render a single composition to output_path."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "npx",
            "remotion",
            "render",
            "src/index.ts",
            composition_id,
            str(output_path),
            "--props=composition.json",
            f"--concurrency={self.config.REMOTION_MAX_WORKERS}",
            f"--gl={self.config.REMOTION_GL}",
        ]
        logger.info("Rendering Remotion composition %s -> %s", composition_id, output_path)
        subprocess.run(cmd, cwd=self.config.REMOTION_DIR, check=True)
        return output_path
