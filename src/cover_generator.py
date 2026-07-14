"""Cover image generation for video projects."""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageDraw, ImageFont

from .config import Config
from .cost_tracker import CostTracker
from .models import Metadata, Script

logger = logging.getLogger(__name__)


class CoverGenerator:
    """Generate horizontal and vertical cover images for a video."""

    # 4:3 horizontal cover size. 1440x1080 = 1.555MP, staying under the
    # 2.36MP Seedream price threshold.
    HORIZONTAL_WIDTH = 1440
    HORIZONTAL_HEIGHT = 1080

    def __init__(self, config: Config, cost_tracker: CostTracker | None = None) -> None:
        self.config = config
        self.cost_tracker = cost_tracker
        self.client = httpx.Client(
            base_url=self.config.SEEDREAM_BASE_URL,
            headers={"Authorization": f"Bearer {self.config.ARK_API_KEY}"},
            timeout=httpx.Timeout(120.0),
        )

    def _call_api(
        self,
        prompt: str,
        width: int,
        height: int,
        reference_image_paths: list[Path],
    ) -> tuple[bytes, dict[str, Any]]:
        """Call Seedream API and return image bytes plus usage info."""
        payload: dict[str, Any] = {
            "model": self.config.SEEDREAM_MODEL,
            "prompt": prompt,
            "n": 1,
            "size": f"{width}x{height}",
            "watermark": False,
        }

        valid_refs = [p for p in reference_image_paths if p and p.exists()]
        if valid_refs:
            refs: list[str] = [
                f"data:image/png;base64,{base64.b64encode(p.read_bytes()).decode()}"
                for p in valid_refs
            ]
            payload["image"] = refs if len(refs) > 1 else refs[0]

        response = self.client.post("", json=payload)
        response.raise_for_status()
        data = response.json()

        usage = data.get("usage", {})
        if not usage:
            usage = {"raw_response_keys": list(data.keys())}

        if "data" in data and len(data["data"]) > 0:
            image_item = data["data"][0]
            if "b64_json" in image_item:
                return base64.b64decode(image_item["b64_json"]), usage
            if "url" in image_item:
                return httpx.get(image_item["url"], timeout=60.0).content, usage

        raise ValueError(
            f"Unexpected response format: {json.dumps(data, ensure_ascii=False)[:200]}"
        )

    def _build_prompt(self, metadata: Metadata) -> str:
        """Combine style prompt with cover-specific content prompt."""
        cover_prompt = metadata.cover_image.prompt
        style = metadata.style_prompt
        return f"与参考图画风保持一致，{style}，{cover_prompt}".strip("，")

    def _generate_horizontal(
        self,
        script: Script,
        output_dir: Path,
    ) -> Path:
        """Generate the 4:3 horizontal cover image."""
        output_path = output_dir / "cover_horizontal.png"
        if output_path.exists():
            logger.info("Horizontal cover already exists")
            return output_path

        width = self.HORIZONTAL_WIDTH
        height = self.HORIZONTAL_HEIGHT
        prompt = self._build_prompt(script.metadata)

        reference_paths: list[Path] = []
        if self.config.VISUAL_REFERENCE_PATH.exists():
            reference_paths.append(self.config.VISUAL_REFERENCE_PATH)
        else:
            logger.warning(
                "Visual reference image not found at %s",
                self.config.VISUAL_REFERENCE_PATH,
            )

        logger.info("Generating horizontal cover (%dx%d)", width, height)
        image_bytes, usage = self._call_api(prompt, width, height, reference_paths)
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

    def _crop_vertical(self, horizontal_path: Path, output_path: Path) -> Path:
        """Crop a 3:4 vertical cover from the center of the horizontal cover."""
        if output_path.exists():
            logger.info("Vertical cover already exists")
            return output_path

        with Image.open(horizontal_path) as img:
            width, height = img.size
            # Target 3:4 ratio using full height.
            target_width = int(height * 3 / 4)
            if target_width > width:
                target_width = width
                target_height = int(width * 4 / 3)
                left = 0
                top = (height - target_height) // 2
                right = width
                bottom = top + target_height
            else:
                left = (width - target_width) // 2
                top = 0
                right = left + target_width
                bottom = height

            cropped = img.crop((left, top, right, bottom))
            cropped.save(output_path)

        logger.info("Saved vertical cover: %s", output_path)
        return output_path

    def _load_font(self, font_size: int) -> ImageFont.FreeTypeFont | ImageFont.Font:
        """Load a CJK-capable font if available, otherwise fall back to default."""
        candidates = [
            "Noto Sans CJK SC",
            "NotoSansCJK-Regular.ttc",
            "SourceHanSansSC-Regular.otf",
            "WenQuanYi Micro Hei",
            "SimHei",
        ]
        for candidate in candidates:
            try:
                return ImageFont.truetype(candidate, font_size)
            except OSError:
                continue
        logger.warning("No CJK font found, falling back to default font")
        return ImageFont.load_default()

    def _draw_text(
        self,
        image_path: Path,
        text: str,
        output_path: Path,
    ) -> Path:
        """Draw centered text with outline over an image."""
        if output_path.exists():
            logger.info("Text cover already exists: %s", output_path)
            return output_path

        with Image.open(image_path).convert("RGBA") as img:
            width, height = img.size
            draw = ImageDraw.Draw(img)

            # Dynamic font size based on image width.
            font_size = max(32, min(72, width // 12))
            font = self._load_font(font_size)

            # Wrap long text to roughly 80% image width.
            max_text_width = int(width * 0.8)
            lines = self._wrap_text(draw, text, font, max_text_width)

            # Calculate total text block height.
            line_heights = [
                draw.textbbox((0, 0), line, font=font)[3]
                - draw.textbbox((0, 0), line, font=font)[1]
                for line in lines
            ]
            line_spacing = int(font_size * 0.2)
            total_height = sum(line_heights) + line_spacing * (len(lines) - 1)
            start_y = (height - total_height) // 2

            for i, line in enumerate(lines):
                bbox = draw.textbbox((0, 0), line, font=font)
                line_width = bbox[2] - bbox[0]
                line_height = line_heights[i]
                x = (width - line_width) // 2
                y = start_y + sum(line_heights[:i]) + line_spacing * i

                # Black outline.
                outline_range = 2
                for dx in range(-outline_range, outline_range + 1):
                    for dy in range(-outline_range, outline_range + 1):
                        draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0, 200))
                # White fill.
                draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))

            img.save(output_path)

        logger.info("Saved cover with text: %s", output_path)
        return output_path

    def _wrap_text(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.Font,
        max_width: int,
    ) -> list[str]:
        """Wrap text into lines that fit within max_width."""
        lines: list[str] = []
        current_line = ""

        for char in text:
            test_line = current_line + char
            bbox = draw.textbbox((0, 0), test_line, font=font)
            if bbox[2] - bbox[0] <= max_width or not current_line:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = char

        if current_line:
            lines.append(current_line)

        return lines if lines else [text]

    def generate(self, script: Script) -> tuple[Path, Path]:
        """Generate horizontal and vertical covers with overlaid text.

        Returns paths to (horizontal_with_text, vertical_with_text).
        """
        if not script.metadata.cover_image.prompt or not script.metadata.cover_image.text:
            logger.info("No cover_image config found, skipping cover generation")
            return Path(), Path()

        output_dir = Path(self.config.IMAGES_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)

        horizontal_raw = self._generate_horizontal(script, output_dir)
        vertical_raw = self._crop_vertical(
            horizontal_raw, output_dir / "cover_vertical.png"
        )

        text = script.metadata.cover_image.text
        horizontal_with_text = self._draw_text(
            horizontal_raw, text, output_dir / "cover_horizontal_text.png"
        )
        vertical_with_text = self._draw_text(
            vertical_raw, text, output_dir / "cover_vertical_text.png"
        )

        return horizontal_with_text, vertical_with_text

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> CoverGenerator:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
