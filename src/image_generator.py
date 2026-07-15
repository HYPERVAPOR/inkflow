"""Image generation using Seedream via Ark / Volces."""

from __future__ import annotations

import base64
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import httpx

from .config import Config
from .cost_tracker import CostTracker
from .models import Metadata, Scene, Script

logger = logging.getLogger(__name__)


class ImageGenerator:
    """Generate images for all scenes in a script."""

    def __init__(self, config: Config, cost_tracker: CostTracker | None = None) -> None:
        self.config = config
        self.cost_tracker = cost_tracker
        self.client = httpx.Client(
            base_url=self.config.SEEDREAM_BASE_URL,
            headers={"Authorization": f"Bearer {self.config.ARK_API_KEY}"},
            timeout=httpx.Timeout(120.0),
        )

    def build_prompt(self, scene: Scene, metadata: Metadata, uses_prev: bool = False) -> str:
        """Combine global style prompt with scene-specific prompt and reference hints.

        The optional metadata.video_system_prompt is prepended to the content
        prompt so every scene shares the same animation-system directive.
        """
        if uses_prev:
            prefix = "保持图1的画风，在图2的基础上"
        else:
            prefix = "与图1的画风保持一致"
        content = scene.image_prompt
        if metadata.video_system_prompt:
            content = f"{metadata.video_system_prompt}，{content}"
        parts = [prefix, metadata.style_prompt, content]
        return "，".join(p for p in parts if p)

    def _parse_resolution(self, resolution: str) -> tuple[int, int]:
        """Parse WIDTHxHEIGHT from metadata resolution."""
        parts = resolution.split("x")
        return int(parts[0]), int(parts[1])

    def _map_size(self, width: int, height: int) -> str:
        """Map width/height to Seedream size parameter."""
        return f"{width}x{height}"

    def _call_api(
        self,
        prompt: str,
        width: int,
        height: int,
        reference_image_paths: list[Path],
    ) -> tuple[bytes, dict[str, Any]]:
        """Call Seedream API and return image bytes plus usage info.

        reference_image_paths: ordered list of reference images.
            The first image is the project's visual-reference.png (style anchor).
            The second image, if present, is the previous scene image for continuity.
        """
        payload: dict[str, Any] = {
            "model": self.config.SEEDREAM_MODEL,
            "prompt": prompt,
            "n": 1,
            "size": self._map_size(width, height),
            "watermark": False,
        }

        valid_refs = [p for p in reference_image_paths if p and p.exists()]
        if valid_refs:
            refs: list[str] = [
                f"data:image/png;base64,{base64.b64encode(p.read_bytes()).decode()}"
                for p in valid_refs
            ]
            # Seedream accepts a single reference (str) or multiple references (list).
            # See seedream-doc for "image" field usage in single / multi image-to-image.
            payload["image"] = refs if len(refs) > 1 else refs[0]

        # NOTE: Adjust payload fields to match the actual Seedream API documentation.
        response = self.client.post("", json=payload)
        response.raise_for_status()
        data = response.json()

        # Try to extract usage/cost info from response
        usage = data.get("usage", {})
        if not usage:
            usage = {"raw_response_keys": list(data.keys())}

        # OpenAI-compatible response shape
        if "data" in data and len(data["data"]) > 0:
            image_item = data["data"][0]
            if "b64_json" in image_item:
                return base64.b64decode(image_item["b64_json"]), usage
            if "url" in image_item:
                return httpx.get(image_item["url"], timeout=60.0).content, usage

        raise ValueError(f"Unexpected response format: {json.dumps(data, ensure_ascii=False)[:200]}")

    def _generate_one(
        self, scene: Scene, metadata: Metadata, output_dir: Path, reference_map: dict[int, Path]
    ) -> Path:
        """Generate image for a single scene."""
        output_path = output_dir / f"scene_{scene.scene_id}.png"
        if output_path.exists():
            logger.info("Image already exists for scene %s", scene.scene_id)
            return output_path

        width, height = self._parse_resolution(metadata.resolution)

        reference_paths: list[Path] = []
        uses_prev = False
        if self.config.VISUAL_REFERENCE_PATH.exists():
            reference_paths.append(self.config.VISUAL_REFERENCE_PATH)
        else:
            logger.warning(
                "Visual reference image not found at %s",
                self.config.VISUAL_REFERENCE_PATH,
            )

        if scene.use_reference_image:
            ref_id = scene.reference_from
            if ref_id == "prev":
                ref_id = scene.scene_id - 1
            if isinstance(ref_id, int) and ref_id in reference_map:
                reference_paths.append(reference_map[ref_id])
                uses_prev = True
            else:
                logger.warning("Reference image not found for scene %s", scene.scene_id)

        prompt = self.build_prompt(scene, metadata, uses_prev=uses_prev)
        logger.info("Generating image for scene %s", scene.scene_id)

        max_retries = 3
        for attempt in range(max_retries):
            try:
                image_bytes, usage = self._call_api(prompt, width, height, reference_paths)
                output_path.write_bytes(image_bytes)
                logger.info("Saved image for scene %s", scene.scene_id)
                if self.cost_tracker:
                    self.cost_tracker.log_image_generation(
                        model=self.config.SEEDREAM_MODEL,
                        quantity=1,
                        width=width,
                        height=height,
                        usage=usage,
                        note=f"scene_id={scene.scene_id}",
                    )
                return output_path
            except Exception as e:
                logger.error("Image generation failed for scene %s (attempt %s): %s", scene.scene_id, attempt + 1, e)
                time.sleep(2 ** attempt)

        # Fallback: create a placeholder image
        logger.warning("Using placeholder for scene %s", scene.scene_id)
        if self.cost_tracker:
            self.cost_tracker.log_image_generation(
                model=self.config.SEEDREAM_MODEL,
                quantity=0,
                width=width,
                height=height,
                cost=0.0,
                note=f"placeholder for scene_id={scene.scene_id}",
            )
        return self._create_placeholder(output_path)

    def _create_placeholder(self, output_path: Path) -> Path:
        """Create a simple placeholder image using FFmpeg."""
        import subprocess

        cmd = [
            "ffmpeg",
            "-y",
            "-f", "lavfi",
            "-i", "color=c=black:s=1080x1920",
            "-frames:v", "1",
            str(output_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return output_path

    def generate(self, script: Script) -> dict[int, Path]:
        """Generate all images respecting hold_image flags and reference dependencies.

        - Independent scenes (no prev reference) are generated concurrently.
        - Dependent scenes (use_reference_image with prev) are generated sequentially.
        - hold_image scenes reuse the previous scene's image after all non-hold
          scenes have been generated.
        - Every generated image uses the project's visual-reference.png as the default
          reference. Scenes requiring continuity with the previous scene append the
          previous image as the second reference.
        """
        output_dir = Path(self.config.IMAGES_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)

        reference_map: dict[int, Path] = {}
        scenes = sorted(script.scenes, key=lambda s: s.scene_id)
        non_hold_scenes = [s for s in scenes if not s.hold_image]

        # 1. Generate independent scenes concurrently
        independent_scenes = [s for s in non_hold_scenes if not s.use_reference_image]
        if independent_scenes:
            logger.info("Generating %s independent scenes concurrently", len(independent_scenes))
            with ThreadPoolExecutor(max_workers=self.config.SEEDREAM_MAX_WORKERS) as executor:
                futures = {
                    executor.submit(
                        self._generate_one, scene, script.metadata, output_dir, reference_map
                    ): scene
                    for scene in independent_scenes
                }
                for future in as_completed(futures):
                    scene = futures[future]
                    try:
                        path = future.result()
                        reference_map[scene.scene_id] = path
                    except Exception as e:
                        logger.error("Failed to generate image for scene %s: %s", scene.scene_id, e)
                        raise

        # 2. Generate dependent scenes sequentially in scene_id order
        dependent_scenes = [s for s in non_hold_scenes if s.use_reference_image]
        if dependent_scenes:
            logger.info("Generating %s dependent scenes sequentially", len(dependent_scenes))
            for scene in sorted(dependent_scenes, key=lambda s: s.scene_id):
                path = self._generate_one(scene, script.metadata, output_dir, reference_map)
                reference_map[scene.scene_id] = path

        # 3. Handle hold_image scenes after their predecessors exist
        hold_scenes = [s for s in scenes if s.hold_image]
        for scene in sorted(hold_scenes, key=lambda s: s.scene_id):
            prev_path = reference_map.get(scene.scene_id - 1)
            if prev_path and prev_path.exists():
                reference_map[scene.scene_id] = prev_path
                logger.info("Scene %s holds image from scene %s", scene.scene_id, scene.scene_id - 1)
            else:
                logger.warning(
                    "Could not hold image for scene %s, previous image not found",
                    scene.scene_id,
                )

        return reference_map

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> ImageGenerator:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
