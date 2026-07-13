"""Start-frame image generation for shots using Seedream via Ark / Volces."""

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
from .models import Metadata, Script, Shot

logger = logging.getLogger(__name__)


class ShotFrameGenerator:
    """Generate start-frame images for all shots in a script."""

    def __init__(self, config: Config, cost_tracker: CostTracker | None = None) -> None:
        self.config = config
        self.cost_tracker = cost_tracker
        self.client = httpx.Client(
            base_url=self.config.SEEDREAM_BASE_URL,
            headers={"Authorization": f"Bearer {self.config.ARK_API_KEY}"},
            timeout=httpx.Timeout(120.0),
        )

    def build_prompt(self, shot: Shot, metadata: Metadata, uses_prev: bool = False) -> str:
        """Combine global style prompt with shot-specific start-frame prompt."""
        if uses_prev:
            prefix = "保持图1的画风，在图2的基础上"
        else:
            prefix = "与图1的画风保持一致"
        parts = [prefix, metadata.style_prompt, shot.start_frame_prompt]
        return ", ".join(p for p in parts if p)

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
        """Call Seedream API and return image bytes plus usage info."""
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

    def _generate_one(
        self,
        shot: Shot,
        metadata: Metadata,
        output_dir: Path,
        reference_map: dict[int, Path],
    ) -> Path:
        """Generate start-frame image for a single shot."""
        output_path = output_dir / f"shot_{shot.shot_id}.png"
        if output_path.exists():
            logger.info("Start frame already exists for shot %s", shot.shot_id)
            if self.cost_tracker:
                width, height = self._parse_resolution(metadata.resolution)
                self.cost_tracker.log_image_generation(
                    model=self.config.SEEDREAM_MODEL,
                    quantity=1,
                    width=width,
                    height=height,
                    usage={},
                    note=f"shot_id={shot.shot_id} (existing, estimated)",
                )
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

        if shot.use_reference_image:
            ref_id = shot.reference_from
            if ref_id == "prev":
                ref_id = shot.shot_id - 1
            if isinstance(ref_id, int) and ref_id in reference_map:
                reference_paths.append(reference_map[ref_id])
                uses_prev = True
            else:
                logger.warning("Reference frame not found for shot %s", shot.shot_id)

        prompt = self.build_prompt(shot, metadata, uses_prev=uses_prev)
        logger.info("Generating start frame for shot %s", shot.shot_id)

        max_retries = 3
        for attempt in range(max_retries):
            try:
                image_bytes, usage = self._call_api(prompt, width, height, reference_paths)
                output_path.write_bytes(image_bytes)
                logger.info("Saved start frame for shot %s", shot.shot_id)
                if self.cost_tracker:
                    self.cost_tracker.log_image_generation(
                        model=self.config.SEEDREAM_MODEL,
                        quantity=1,
                        width=width,
                        height=height,
                        usage=usage,
                        note=f"shot_id={shot.shot_id}",
                    )
                return output_path
            except Exception as e:
                logger.error(
                    "Start-frame generation failed for shot %s (attempt %s): %s",
                    shot.shot_id,
                    attempt + 1,
                    e,
                )
                time.sleep(2**attempt)

        logger.warning("Using placeholder for shot %s", shot.shot_id)
        if self.cost_tracker:
            self.cost_tracker.log_image_generation(
                model=self.config.SEEDREAM_MODEL,
                quantity=0,
                width=width,
                height=height,
                cost=0.0,
                note=f"placeholder for shot_id={shot.shot_id}",
            )
        return self._create_placeholder(output_path)

    def _create_placeholder(self, output_path: Path) -> Path:
        """Create a simple placeholder image using FFmpeg."""
        import subprocess

        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=1080x1920",
            "-frames:v",
            "1",
            str(output_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return output_path

    def generate(self, script: Script) -> dict[int, Path]:
        """Generate start-frame images for all shots respecting dependencies.

        - Independent shots (no prev reference) are generated concurrently.
        - Dependent shots (use_reference_image with prev) are generated sequentially.
        - hold_video shots reuse the previous shot's start frame.
        """
        if not script.uses_shots:
            return {}

        output_dir = Path(self.config.IMAGES_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)

        reference_map: dict[int, Path] = {}
        shots = sorted(script.shots, key=lambda s: s.shot_id)
        non_hold_shots = [s for s in shots if not s.hold_video]

        # 1. Generate independent shots concurrently
        independent_shots = [s for s in non_hold_shots if not s.use_reference_image]
        if independent_shots:
            logger.info("Generating %s independent shot frames concurrently", len(independent_shots))
            with ThreadPoolExecutor(max_workers=self.config.SEEDREAM_MAX_WORKERS) as executor:
                futures = {
                    executor.submit(
                        self._generate_one, shot, script.metadata, output_dir, reference_map
                    ): shot
                    for shot in independent_shots
                }
                for future in as_completed(futures):
                    shot = futures[future]
                    try:
                        path = future.result()
                        reference_map[shot.shot_id] = path
                    except Exception as e:
                        logger.error("Failed to generate start frame for shot %s: %s", shot.shot_id, e)
                        raise

        # 2. Generate dependent shots sequentially in shot_id order
        dependent_shots = [s for s in non_hold_shots if s.use_reference_image]
        if dependent_shots:
            logger.info("Generating %s dependent shot frames sequentially", len(dependent_shots))
            for shot in sorted(dependent_shots, key=lambda s: s.shot_id):
                path = self._generate_one(shot, script.metadata, output_dir, reference_map)
                reference_map[shot.shot_id] = path

        # 3. Handle hold_video shots after their predecessors exist
        hold_shots = [s for s in shots if s.hold_video]
        for shot in sorted(hold_shots, key=lambda s: s.shot_id):
            prev_path = reference_map.get(shot.shot_id - 1)
            if prev_path and prev_path.exists():
                reference_map[shot.shot_id] = prev_path
                logger.info("Shot %s holds start frame from shot %s", shot.shot_id, shot.shot_id - 1)
            else:
                logger.warning(
                    "Could not hold start frame for shot %s, previous frame not found",
                    shot.shot_id,
                )

        return reference_map

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> ShotFrameGenerator:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
