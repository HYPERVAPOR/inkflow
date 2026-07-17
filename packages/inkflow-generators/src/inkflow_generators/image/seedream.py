"""Image generation using Seedream via Ark / Volces."""

from __future__ import annotations

import base64
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from inkflow_core.config import Config
from inkflow_core.models import Metadata, Script

from inkflow_generators.cost import CostTracker

logger = logging.getLogger(__name__)


@dataclass
class FrameRequest:
    """A request to generate a single image."""

    id: int
    prompt: str
    use_reference_image: bool = False
    reference_from: str | int | None = None
    hold_image: bool = False
    motion: dict[str, Any] = field(default_factory=dict)


class ImageGenerator:
    """Generate images from text prompts using Seedream."""

    def __init__(self, config: Config, cost_tracker: CostTracker | None = None) -> None:
        self.config = config
        self.cost_tracker = cost_tracker
        self.client = httpx.Client(
            base_url=self.config.SEEDREAM_BASE_URL,
            headers={"Authorization": f"Bearer {self.config.ARK_API_KEY}"},
            timeout=httpx.Timeout(120.0),
        )

    def build_prompt(
        self, request: FrameRequest, metadata: Metadata, uses_prev: bool = False
    ) -> str:
        """Combine global style prompt with request-specific prompt and reference hints."""
        if uses_prev:
            prefix = "保持图1的画风，在图2的基础上"
        else:
            prefix = "与图1的画风保持一致"
        content = request.prompt
        if metadata.video_system_prompt:
            content = f"{metadata.video_system_prompt}，{content}"
        parts = [prefix, metadata.style_prompt, content]
        return "，".join(p for p in parts if p)

    def _parse_resolution(self, resolution: str) -> tuple[int, int]:
        """Parse WIDTHxHEIGHT from metadata resolution."""
        parts = resolution.split("x")
        return int(parts[0]), int(parts[1])

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

        preview = json.dumps(data, ensure_ascii=False)[:200]
        raise ValueError(f"Unexpected response format: {preview}")

    def _generate_one(
        self,
        request: FrameRequest,
        metadata: Metadata,
        output_dir: Path,
        reference_map: dict[int, Path],
    ) -> Path:
        """Generate image for a single request."""
        output_path = output_dir / f"scene_{request.id}.png"
        if output_path.exists():
            logger.info("Image already exists for request %s", request.id)
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

        if request.use_reference_image:
            ref_id = request.reference_from
            if ref_id == "prev":
                ref_id = request.id - 1
            if isinstance(ref_id, int) and ref_id in reference_map:
                reference_paths.append(reference_map[ref_id])
                uses_prev = True
            else:
                logger.warning("Reference image not found for request %s", request.id)

        prompt = self.build_prompt(request, metadata, uses_prev=uses_prev)
        logger.info("Generating image for request %s", request.id)

        max_retries = 3
        for attempt in range(max_retries):
            try:
                image_bytes, usage = self._call_api(prompt, width, height, reference_paths)
                output_path.write_bytes(image_bytes)
                logger.info("Saved image for request %s", request.id)
                if self.cost_tracker:
                    self.cost_tracker.log_image_generation(
                        model=self.config.SEEDREAM_MODEL,
                        quantity=1,
                        width=width,
                        height=height,
                        usage=usage,
                        note=f"request_id={request.id}",
                    )
                return output_path
            except Exception as e:
                logger.error(
                    "Image generation failed for request %s (attempt %s): %s",
                    request.id,
                    attempt + 1,
                    e,
                )
                time.sleep(2 ** attempt)

        logger.warning("Using placeholder for request %s", request.id)
        if self.cost_tracker:
            self.cost_tracker.log_image_generation(
                model=self.config.SEEDREAM_MODEL,
                quantity=0,
                width=width,
                height=height,
                cost=0.0,
                note=f"placeholder for request_id={request.id}",
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

    def generate(self, requests: list[FrameRequest], metadata: Metadata) -> dict[int, Path]:
        """Generate all images respecting hold_image flags and reference dependencies."""
        output_dir = Path(self.config.IMAGES_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)

        reference_map: dict[int, Path] = {}
        sorted_requests = sorted(requests, key=lambda r: r.id)
        non_hold_requests = [r for r in sorted_requests if not r.hold_image]

        # 1. Generate independent requests concurrently
        independent_requests = [r for r in non_hold_requests if not r.use_reference_image]
        if independent_requests:
            logger.info("Generating %s independent images concurrently", len(independent_requests))
            with ThreadPoolExecutor(max_workers=self.config.SEEDREAM_MAX_WORKERS) as executor:
                futures = {
                    executor.submit(
                        self._generate_one, request, metadata, output_dir, reference_map
                    ): request
                    for request in independent_requests
                }
                for future in as_completed(futures):
                    request = futures[future]
                    try:
                        path = future.result()
                        reference_map[request.id] = path
                    except Exception as e:
                        logger.error("Failed to generate image for request %s: %s", request.id, e)
                        raise

        # 2. Generate dependent requests sequentially in id order
        dependent_requests = [r for r in non_hold_requests if r.use_reference_image]
        if dependent_requests:
            logger.info("Generating %s dependent images sequentially", len(dependent_requests))
            for request in sorted(dependent_requests, key=lambda r: r.id):
                path = self._generate_one(request, metadata, output_dir, reference_map)
                reference_map[request.id] = path

        # 3. Handle hold_image requests after their predecessors exist
        hold_requests = [r for r in sorted_requests if r.hold_image]
        for request in sorted(hold_requests, key=lambda r: r.id):
            prev_path = reference_map.get(request.id - 1)
            if prev_path and prev_path.exists():
                reference_map[request.id] = prev_path
                logger.info(
                    "Request %s holds image from request %s", request.id, request.id - 1
                )
            else:
                logger.warning(
                    "Could not hold image for request %s, previous image not found",
                    request.id,
                )

        return reference_map

    def generate_for_script(self, script: Script) -> dict[int, Path]:
        """Generate one image per subtitle for legacy image-based workflow."""
        requests = [
            FrameRequest(
                id=index,
                prompt=text,
                motion={
                    "type": "ken_burns",
                    "start": "zoom_1.0_pan_0_0",
                    "end": "zoom_1.15_pan_0_0",
                },
            )
            for index, text in enumerate(script.subtitles)
        ]
        return self.generate(requests, script.metadata)

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> ImageGenerator:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
