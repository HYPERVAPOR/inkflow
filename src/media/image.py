"""Image manipulation utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


def crop_vertical(horizontal_path: Path, output_path: Path) -> Path:
    """Crop a 3:4 vertical image from the center of a horizontal image."""
    with Image.open(horizontal_path) as img:
        width, height = img.size
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

    return output_path


def draw_centered_text(
    image_path: Path,
    output_path: Path,
    text: str,
    font_name: str = "Noto Sans CJK SC",
) -> Path:
    """Draw centered white text with black outline over an image."""
    with Image.open(image_path).convert("RGBA") as img:
        width, height = img.size
        draw = ImageDraw.Draw(img)

        font_size = max(32, min(72, width // 12))
        font = _load_font(font_name, font_size)

        max_text_width = int(width * 0.8)
        lines = _wrap_text(draw, text, font, max_text_width)

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
            x = (width - line_width) // 2
            y = start_y + sum(line_heights[:i]) + line_spacing * i

            outline_range = 2
            for dx in range(-outline_range, outline_range + 1):
                for dy in range(-outline_range, outline_range + 1):
                    draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0, 200))
            draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))

        img.save(output_path)

    return output_path


def _load_font(font_name: str, font_size: int) -> Any:
    """Load a CJK-capable font if available, otherwise fall back to default."""
    candidates = [
        font_name,
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
    return ImageFont.load_default()


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: Any,
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
