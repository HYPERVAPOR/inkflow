"""Video generation for shots using Seedance via Ark / Volces."""

from __future__ import annotations

import asyncio
import base64
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from src.core.config import Config
from src.core.models import Metadata, Script, Shot
from src.cost.tracker import CostTracker

logger = logging.getLogger(__name__)

# Hardcoded Seedance generation settings. These cannot be overridden.
VIDEO_MODEL = "doubao-seedance-1-0-pro-fast-251015"
VIDEO_RESOLUTION = "720p"
VIDEO_FPS = 12
VIDEO_WATERMARK = False
VIDEO_STYLE_PREFIX = "一拍二 逐帧手绘动画，每帧独立绘制，线条轻微抖动，蜡笔涂鸦质感"


@dataclass
class VideoTaskResult:
    video_name: str
    task_id: str | None = None
    video_url: str | None = None
    error: str | None = None
    error_detail: dict[str, Any] | None = None
    status: str = "pending"
    usage: dict[str, Any] = field(default_factory=dict)


@dataclass
class VideoGenerationConfig:
    first_frame: str | None = None
    last_frame: str | None = None
    ratio: str = "16:9"
    duration: int | None = None
    resolution: str | None = None
    frames: int | None = None
    watermark: bool = True
    seed: int | None = None


def _nearest_valid_frames(target: int) -> int:
    """Snap a target frame count to the nearest Seedance-legal value.

    Seedance requires total frame count of the form ``25 + 4n`` within
    ``[29, 289]``. We aim for ``VIDEO_FPS * duration`` frames to reach ~12 fps.
    """
    n = round((target - 25) / 4)
    n = max(1, min(66, n))
    return 25 + 4 * n


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
        self.api_key = self.config.ARK_API_KEY or ""
        self.api_base = self.config.SEEDANCE_BASE_URL.rstrip("/")
        self.semaphore = asyncio.Semaphore(self.config.SEEDANCE_MAX_WORKERS)

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
        if config.last_frame:
            content.append({
                "type": "image_url",
                "image_url": {"url": config.last_frame},
                "role": "last_frame",
            })
        return content

    def _build_request_body(
        self, prompt: str, config: VideoGenerationConfig, model_name: str
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": model_name,
            "content": self._build_content(prompt, config),
        }

        for field_name in ["ratio", "duration", "resolution", "frames", "seed", "watermark"]:
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
            data: dict[str, Any] = response.json()
            return data

    async def _get_task_status(self, task_id: str) -> dict[str, Any]:
        url = f"{self.api_base}/contents/generations/tasks/{task_id}"

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url, headers=self._get_headers())
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            return data

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

    async def _generate_one_with_limit(
        self,
        shot: Shot,
        metadata: Metadata,
        output_dir: Path,
        start_frame_path: Path,
        duration: int,
        last_frame_path: Path | None = None,
    ) -> Path:
        """Generate a video clip with concurrency limit."""
        async with self.semaphore:
            return await self._generate_one(
                shot, metadata, output_dir, start_frame_path, duration, last_frame_path
            )

    async def _generate_one(
        self,
        shot: Shot,
        metadata: Metadata,
        output_dir: Path,
        start_frame_path: Path,
        duration: int,
        last_frame_path: Path | None = None,
    ) -> Path:
        """Generate a video clip for a single shot."""
        output_path = output_dir / f"shot_{shot.shot_id}.mp4"
        if output_path.exists():
            logger.info("Video already exists for shot %s", shot.shot_id)
            if self.cost_tracker:
                self.cost_tracker.log_video_generation(
                    model=VIDEO_MODEL,
                    ratio=metadata.aspect_ratio,
                    resolution=VIDEO_RESOLUTION,
                    duration=duration,
                    usage={},
                    note=f"shot_id={shot.shot_id} (existing, estimated)",
                )
            return output_path

        prompt = shot.video_motion_prompt
        if metadata.video_system_prompt:
            prompt = f"{metadata.video_system_prompt}，{VIDEO_STYLE_PREFIX}，{prompt}"
        else:
            prompt = f"{VIDEO_STYLE_PREFIX}，{prompt}"

        frames = _nearest_valid_frames(VIDEO_FPS * duration)
        config = VideoGenerationConfig(
            first_frame=_image_to_data_url(start_frame_path),
            ratio=metadata.aspect_ratio,
            duration=duration,
            resolution=VIDEO_RESOLUTION,
            frames=frames,
            watermark=VIDEO_WATERMARK,
        )
        # NOTE: last_frame is disabled because the hardcoded cheapest model
        # (doubao-seedance-1-0-pro-fast) does not support both first and last
        # frames in the same request.
        # NOTE: generate_audio is never sent -> silent video (the 1.0 series
        # has no audio support anyway).

        logger.info(
            "Generating video for shot %s (model=%s, ratio=%s, duration=%ss, "
            "resolution=%s, fps=%s, frames=%s)",
            shot.shot_id,
            VIDEO_MODEL,
            metadata.aspect_ratio,
            duration,
            VIDEO_RESOLUTION,
            VIDEO_FPS,
            frames,
        )

        task_data = await self._create_task(prompt, config, VIDEO_MODEL)
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
                model=VIDEO_MODEL,
                ratio=metadata.aspect_ratio,
                resolution=VIDEO_RESOLUTION,
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
        """Generate video clips for all shots."""
        output_dir = Path(self.config.VIDEOS_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)

        sorted_shots = sorted(script.shots, key=lambda s: s.shot_id)
        next_frame_map: dict[int, Path | None] = {}
        for idx, shot in enumerate(sorted_shots):
            if idx + 1 < len(sorted_shots):
                next_id = sorted_shots[idx + 1].shot_id
                next_frame_map[shot.shot_id] = start_frame_map.get(next_id)
            else:
                next_frame_map[shot.shot_id] = None

        tasks = []
        for shot in sorted_shots:
            start_frame = start_frame_map.get(shot.shot_id)
            if not start_frame or not start_frame.exists():
                raise FileNotFoundError(f"Start frame not found for shot {shot.shot_id}")
            duration = shot_durations.get(shot.shot_id, 5)
            last_frame = next_frame_map.get(shot.shot_id)
            tasks.append(
                self._generate_one_with_limit(
                    shot, script.metadata, output_dir, start_frame, duration, last_frame
                )
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        video_map: dict[int, Path] = {}
        for shot, result in zip(sorted_shots, results):
            if isinstance(result, BaseException):
                logger.error("Failed to generate video for shot %s: %s", shot.shot_id, result)
                raise result
            video_map[shot.shot_id] = result

        return video_map
