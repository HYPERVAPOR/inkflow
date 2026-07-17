"""Unified Seedream image generation."""

from __future__ import annotations

import base64
import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx

from src.core.config import Config
from src.media.ffmpeg import create_placeholder_image

logger = logging.getLogger(__name__)


class ImageGeneratorClient:
    """Client for Seedream image generation via Ark / Volces."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.client = httpx.Client(
            base_url=self.config.SEEDREAM_BASE_URL,
            headers={"Authorization": f"Bearer {self.config.ARK_API_KEY}"},
            timeout=httpx.Timeout(120.0),
        )

    def build_prompt(
        self,
        content: str,
        style: str,
        system_prompt: str = "",
        uses_prev: bool = False,
    ) -> str:
        """Combine global style prompt with content prompt."""
        if uses_prev:
            prefix = "保持图1的画风，在图2的基础上"
        else:
            prefix = "与图1的画风保持一致"
        if system_prompt:
            content = f"{system_prompt}，{content}"
        # Fixed trailing instruction to keep frames clean and free of extra elements.
        clean_tail = "保持画面简洁，没有多余元素"
        parts = [prefix, style, content, clean_tail]
        return "，".join(p for p in parts if p)

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

    def generate(
        self,
        prompt: str,
        width: int,
        height: int,
        reference_paths: list[Path] | None = None,
        max_retries: int = 3,
    ) -> tuple[bytes, dict[str, Any]]:
        """Generate image and return bytes with usage info."""
        reference_paths = reference_paths or []
        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                return self._call_api(prompt, width, height, reference_paths)
            except Exception as e:
                last_error = e
                logger.error("Image generation failed (attempt %s): %s", attempt + 1, e)
                time.sleep(2**attempt)
        raise RuntimeError(f"Image generation failed after {max_retries} attempts") from last_error

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "ImageGeneratorClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def generate_placeholder(output_path: Path, width: int, height: int) -> Path:
    """Create a placeholder image when generation fails."""
    logger.warning("Using placeholder image: %s", output_path)
    return create_placeholder_image(output_path, width, height)
