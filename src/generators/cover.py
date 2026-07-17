"""Cover image generation for video projects."""

from __future__ import annotations

import logging
from pathlib import Path

from src.core.config import Config
from src.core.models import Script
from src.cost.tracker import CostTracker
from src.generators.image import ImageGeneratorClient
from src.media.image import crop_vertical, draw_centered_text

logger = logging.getLogger(__name__)


class CoverGenerator:
    """Generate horizontal and vertical cover images for a video."""

    HORIZONTAL_WIDTH = 1440
    HORIZONTAL_HEIGHT = 1080

    def __init__(self, config: Config, cost_tracker: CostTracker | None = None) -> None:
        self.config = config
        self.cost_tracker = cost_tracker
        self.image_client = ImageGeneratorClient(config)

    def _build_prompt(self, script: Script) -> str:
        """Combine style prompt with cover-specific content prompt."""
        cover_prompt = script.metadata.cover_image.prompt
        style = script.metadata.style_prompt
        content = cover_prompt
        if script.metadata.video_system_prompt:
            content = f"{script.metadata.video_system_prompt}，{content}"
        return f"与参考图画风保持一致，{style}，{content}".strip("，")

    def _generate_horizontal(self, script: Script, output_dir: Path) -> Path:
        """Generate the 4:3 horizontal cover image."""
        output_path = output_dir / "cover_horizontal.png"
        if output_path.exists():
            logger.info("Horizontal cover already exists")
            return output_path

        width = self.HORIZONTAL_WIDTH
        height = self.HORIZONTAL_HEIGHT
        prompt = self._build_prompt(script)

        reference_paths: list[Path] = []
        if self.config.VISUAL_REFERENCE_PATH.exists():
            reference_paths.append(self.config.VISUAL_REFERENCE_PATH)
        else:
            logger.warning(
                "Visual reference image not found at %s", self.config.VISUAL_REFERENCE_PATH
            )

        logger.info("Generating horizontal cover (%dx%d)", width, height)
        image_bytes, usage = self.image_client.generate(prompt, width, height, reference_paths)
        output_path.write_bytes(image_bytes)
        logger.info("Saved horizontal cover: %s", output_path)

        if self.cost_tracker:
            self.cost_tracker.log_image_generation(
                model=self.config.SEEDREAM_MODEL,
                quantity=1,
                width=width,
                height=height,
                usage=usage,
                note="cover_horizontal",
            )

        return output_path

    def generate(self, script: Script) -> tuple[Path, Path]:
        """Generate horizontal and vertical covers with overlaid text."""
        if not script.metadata.cover_image.prompt or not script.metadata.cover_image.text:
            logger.info("No cover_image config found, skipping cover generation")
            return Path(), Path()

        output_dir = Path(self.config.IMAGES_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)

        horizontal_raw = self._generate_horizontal(script, output_dir)
        vertical_raw = crop_vertical(horizontal_raw, output_dir / "cover_vertical.png")

        text = script.metadata.cover_image.text
        horizontal_with_text = draw_centered_text(
            horizontal_raw, output_dir / "cover_horizontal_text.png", text
        )
        vertical_with_text = draw_centered_text(
            vertical_raw, output_dir / "cover_vertical_text.png", text
        )

        return horizontal_with_text, vertical_with_text

    def close(self) -> None:
        self.image_client.close()

    def __enter__(self) -> "CoverGenerator":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
