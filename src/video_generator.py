"""Video generation for shots using Seedance via Ark / Volces."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from .config import Config
from .cost_tracker import CostTracker
from .models import Metadata, Script, Shot

logger = logging.getLogger(__name__)


@dataclass
class VideoTaskResult:
    video_name: str
    task_id: str | None = None
    video_url: str | None = None
    error: str | None = None
    error_detail: dict | None = None
    status: str = "pending"
    usage: dict[str, Any] = field(default_factory=dict)


@dataclass
class VideoGenerationConfig:
    first_frame: str | None = None
    ratio: str = "16:9"
    duration: int | None = None
    resolution: str | None = None
    watermark: bool = True
    seed: int | None = None


def _image_to_data_url(image_path: Path) -> str:
    """Convert a local image file to a base64 data URL."""
    data = image_path.read_bytes()
    b64 = base64.b64encode(data).decode()
    return f"data:image/png;base64,{b64}"


class VideoGenerator:
    """Generate video clips for shots using Seedance."""

    def __init__(self, config: Config, cost_tracker: CostTracker | None = None) -> None:
        self.config = config
        self.cost_tracker = cost_tracker
        self.api_key = (
            self.config.ARK_API_KEY
            or ""
        )
        self.api_base = self.config.SEEDANCE_BASE_URL.rstrip("/")
        self.semaphore = asyncio.Semaphore(self.config.SEEDANCE_MAX_WORKERS)

    async def _generate_one_with_limit(
        self,
        shot: Shot,
        metadata: Metadata,
        output_dir: Path,
        start_frame_path: Path,
        duration: int,
    ) -> Path:
        """Generate a video clip with concurrency limit."""
        async with self.semaphore:
            return await self._generate_one(
                shot, metadata, output_dir, start_frame_path, duration
            )

    def _get_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def _build_content(self, prompt: str, config: VideoGenerationConfig) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        if config.first_frame:
            content.append({
                "type": "image_url",
                "image_url": {"url": config.first_frame},
                "role": "first_frame",
            })
        return content

    def _build_request_body(
        self, prompt: str, config: VideoGenerationConfig, model_name: str
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": model_name,
            "content": self._build_content(prompt, config),
        }

        optional_fields = [
            "ratio",
            "duration",
            "resolution",
            "seed",
            "watermark",
        ]
        for field_name in optional_fields:
            value = getattr(config, field_name, None)
            if value is not None:
                body[field_name] = value

        return body

    async def _create_task(
        self, prompt: str, config: VideoGenerationConfig, model_name: str
    ) -> dict[str, Any]:
        url = f"{self.api_base}/contents/generations/tasks"
        body = self._build_request_body(prompt, config, model_name)

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, headers=self._get_headers(), json=body)
            response.raise_for_status()
            return response.json()

    async def _get_task_status(self, task_id: str) -> dict[str, Any]:
        url = f"{self.api_base}/contents/generations/tasks/{task_id}"

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url, headers=self._get_headers())
            response.raise_for_status()
            return response.json()

    async def _poll_task(
        self,
        task_id: str,
        video_name: str,
        max_wait_seconds: int = 1200,
        poll_interval: int = 10,
    ) -> VideoTaskResult:
        max_polls = max_wait_seconds // poll_interval

        for _ in range(max_polls):
            result = await self._get_task_status(task_id)
            status = result.get("status")

            if status == "succeeded":
                content = result.get("content", {})
                return VideoTaskResult(
                    video_name=video_name,
                    task_id=task_id,
                    video_url=content.get("video_url"),
                    status="succeeded",
                    usage=result.get("usage", {}),
                )

            if status == "failed":
                error = result.get("error", {})
                return VideoTaskResult(
                    video_name=video_name,
                    task_id=task_id,
                    error=str(error),
                    error_detail=error,
                    status="failed",
                )

            logger.info("Video %s status: %s, waiting...", video_name, status)
            await asyncio.sleep(poll_interval)

        result = await self._get_task_status(task_id)
        return VideoTaskResult(
            video_name=video_name,
            task_id=task_id,
            error="polling_timeout",
            status="pending",
            usage=result.get("usage", {}),
        )

    async def _download_video(self, video_url: str, output_path: Path) -> Path:
        """Download generated video from URL to local path."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.get(video_url)
            response.raise_for_status()
            output_path.write_bytes(response.content)
        return output_path

    async def _generate_one(
        self,
        shot: Shot,
        metadata: Metadata,
        output_dir: Path,
        start_frame_path: Path,
        duration: int,
    ) -> Path:
        """Generate a video clip for a single shot."""
        output_path = output_dir / f"shot_{shot.shot_id}.mp4"
        if output_path.exists():
            logger.info("Video already exists for shot %s", shot.shot_id)
            if self.cost_tracker:
                self.cost_tracker.log_video_generation(
                    model=metadata.video_model,
                    ratio=metadata.aspect_ratio,
                    resolution=metadata.video_resolution,
                    duration=duration,
                    usage={},
                    note=f"shot_id={shot.shot_id} (existing, estimated)",
                )
            return output_path

        model_name = metadata.video_model
        ratio = metadata.aspect_ratio
        resolution = metadata.video_resolution

        prompt = shot.video_motion_prompt
        if metadata.video_system_prompt:
            prompt = f"{metadata.video_system_prompt}，{prompt}"

        config = VideoGenerationConfig(
            first_frame=_image_to_data_url(start_frame_path),
            ratio=ratio,
            duration=duration,
            resolution=resolution,
            watermark=metadata.video_watermark,
        )

        logger.info(
            "Generating video for shot %s (model=%s, ratio=%s, duration=%ss, resolution=%s)",
            shot.shot_id,
            model_name,
            ratio,
            duration,
            resolution,
        )

        task_data = await self._create_task(prompt, config, model_name)
        task_id = task_data.get("id")
        if not task_id:
            raise ValueError(f"Failed to create video task for shot {shot.shot_id}: {task_data}")

        result = await self._poll_task(task_id, f"shot_{shot.shot_id}")

        if result.status != "succeeded" or not result.video_url:
            raise RuntimeError(
                f"Video generation failed for shot {shot.shot_id}: {result.error}"
            )

        await self._download_video(result.video_url, output_path)
        logger.info("Saved video for shot %s: %s", shot.shot_id, output_path)

        if self.cost_tracker:
            self.cost_tracker.log_video_generation(
                model=model_name,
                ratio=ratio,
                resolution=resolution,
                duration=duration,
                usage=result.usage,
                note=f"shot_id={shot.shot_id}",
            )

        return output_path

    async def generate(
        self,
        script: Script,
        start_frame_map: dict[int, Path],
        shot_durations: dict[int, int],
    ) -> dict[int, Path]:
        """Generate video clips for all shots.

        Args:
            script: The script with shots.
            start_frame_map: Mapping from shot_id to start-frame image path.
            shot_durations: Mapping from shot_id to video duration in seconds.
        """
        if not script.uses_shots:
            return {}

        output_dir = Path(self.config.VIDEOS_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)

        tasks = []
        for shot in script.shots:
            if shot.hold_video:
                continue
            start_frame = start_frame_map.get(shot.shot_id)
            if not start_frame or not start_frame.exists():
                raise FileNotFoundError(f"Start frame not found for shot {shot.shot_id}")
            duration = shot_durations.get(shot.shot_id, 5)
            tasks.append(
                self._generate_one_with_limit(
                    shot, script.metadata, output_dir, start_frame, duration
                )
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        video_map: dict[int, Path] = {}
        for shot, result in zip(script.shots, results):
            if isinstance(result, Exception):
                logger.error("Failed to generate video for shot %s: %s", shot.shot_id, result)
                raise result
            video_map[shot.shot_id] = result

        # Handle hold_video shots
        for shot in script.shots:
            if shot.hold_video:
                prev_path = video_map.get(shot.shot_id - 1)
                if prev_path and prev_path.exists():
                    video_map[shot.shot_id] = prev_path
                    logger.info("Shot %s holds video from shot %s", shot.shot_id, shot.shot_id - 1)
                else:
                    logger.warning(
                        "Could not hold video for shot %s, previous video not found",
                        shot.shot_id,
                    )

        return video_map
