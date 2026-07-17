"""Load and validate script.json / script.md."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from .models import Asset, Metadata, Script, Shot, VisualPlan


def load_script(path: str | Path) -> Script:
    """Load a script from JSON or Markdown file."""
    path = Path(path)
    if path.suffix.lower() in {".md", ".markdown"}:
        return load_script_md(path)
    return load_script_json(path)


def load_script_json(path: str | Path) -> Script:
    """Load a script from JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Script.model_validate(data)


def save_script(script: Script, path: str | Path) -> None:
    """Save a script back to JSON file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(script.model_dump(mode="json"), f, ensure_ascii=False, indent=2)


def load_script_md(path: str | Path) -> Script:
    """Parse a Markdown script with YAML frontmatter into a Script."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")

    # Split YAML frontmatter and body
    if text.startswith("---"):
        _, frontmatter, body = text.split("---", 2)
        metadata_dict = yaml.safe_load(frontmatter) or {}
    else:
        metadata_dict = {}
        body = text

    metadata = Metadata.model_validate(metadata_dict)

    # Default workflow to infographic if not specified
    if metadata.workflow is None:
        metadata.workflow = "infographic"

    # Parse shots from headings
    shot_blocks = re.split(r"\n#\s+", body.strip())
    # First block may be empty if body starts with a heading
    shot_blocks = [block.strip() for block in shot_blocks if block.strip()]

    subtitles: list[str] = []
    shots: list[Shot] = []

    for shot_id, block in enumerate(shot_blocks, start=1):
        lines = block.splitlines()
        # Heading line is the first line; rest is content
        # Actually re.split keeps the heading text in the block
        # We don't need the heading text itself for now.
        content_lines = lines[1:] if len(lines) > 1 else lines
        content = "\n".join(content_lines).strip()

        # Extract visual description and assets
        visual_match = re.search(
            r"(?:画面[:：]|visual[:：])\s*(.+?)(?=\n(?:素材[:：]|assets[:：])|$)",
            content,
            re.DOTALL | re.IGNORECASE,
        )
        assets_match = re.search(
            r"(?:素材[:：]|assets[:：])\s*(.+)$", content, re.DOTALL | re.IGNORECASE
        )

        visual_text = visual_match.group(1).strip() if visual_match else ""
        assets_text = assets_match.group(1).strip() if assets_match else ""

        # Remove visual/assets sections from content to get subtitles
        subtitle_text = content
        if visual_match:
            subtitle_text = subtitle_text[: visual_match.start()].strip()
        if assets_match:
            subtitle_text = subtitle_text[: assets_match.start()].strip()

        # Split subtitle text into paragraphs; each paragraph is a subtitle line
        shot_subtitles = [line.strip() for line in subtitle_text.split("\n\n") if line.strip()]

        start_index = len(subtitles)
        subtitles.extend(shot_subtitles)
        subtitle_indices = list(range(start_index, len(subtitles)))

        assets = _parse_assets(assets_text)

        shots.append(
            Shot(
                shot_id=shot_id,
                subtitle_indices=subtitle_indices,
                visual=VisualPlan(
                    description=visual_text,
                    style="infographic",
                    assets=assets,
                ),
                transition=metadata.default_transition,
            )
        )

    return Script(metadata=metadata, subtitles=subtitles, shots=shots)


def _parse_assets(text: str) -> list[Asset]:
    """Parse asset declarations from markdown text."""
    assets: list[Asset] = []
    if not text:
        return assets

    # Each asset line: - type: description or - type url description
    for line in text.splitlines():
        line = line.strip()
        if not line or not line.startswith("-"):
            continue
        line = line[1:].strip()

        # Try to match "type: description"
        match = re.match(r"(\w+)\s*[:：]\s*(.+)", line)
        if not match:
            continue

        asset_type = match.group(1).lower()
        rest = match.group(2).strip()

        # Extract URL if present
        url_match = re.search(r"(https?://\S+)", rest)
        url = url_match.group(1) if url_match else None
        description = rest
        if url:
            description = rest.replace(url, "").strip()

        if asset_type in {
            "seedream_image",
            "seedance_video",
            "image_url",
            "video_url",
            "local_image",
            "local_video",
        }:
            assets.append(
                Asset(
                    id=f"asset_{len(assets) + 1}",
                    type=asset_type,  # type: ignore[arg-type]
                    description=description,
                    url=url,
                )
            )

    return assets
