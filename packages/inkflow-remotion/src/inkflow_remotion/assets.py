"""Fetch and prepare assets for the Remotion infographic workflow."""

from __future__ import annotations

import base64
import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from inkflow_core.config import Config
from inkflow_core.models import Asset, Script

logger = logging.getLogger(__name__)


@dataclass
class FetchedAsset:
    """An asset with a local filename usable from Remotion public/."""

    asset: Asset
    filename: str
    local_path: Path


class AssetFetcher:
    """Resolve declarative assets into local Remotion public/ files."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.client = httpx.Client(timeout=120.0, follow_redirects=True)

    def _public_path(self, filename: str) -> Path:
        return self.config.REMOTION_PUBLIC_DIR / filename

    def _project_image_path(self, filename: str) -> Path:
        return self.config.IMAGES_DIR / filename

    def _project_video_path(self, filename: str) -> Path:
        return self.config.VIDEOS_DIR / filename

    def _seedream_image(self, asset: Asset, index: int) -> FetchedAsset:
        """Generate a Seedream image for an asset description."""
        filename = f"asset_{index}_seedream.png"
        local_path = self._project_image_path(filename)
        public_path = self._public_path(filename)

        if public_path.exists():
            logger.info("Seedream asset %s already exists", filename)
            return FetchedAsset(asset, filename, local_path)

        prompt = asset.description
        if self.config.VISUAL_REFERENCE_PATH.exists():
            style_prefix = "与参考图画风保持一致"
        else:
            style_prefix = ""
        full_prompt = "，".join(p for p in [style_prefix, prompt] if p)

        width, height = self._parse_resolution(self.config.project_dir)
        image_bytes, usage = self._call_seedream(full_prompt, width, height)

        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(image_bytes)
        shutil.copy2(local_path, public_path)
        logger.info("Generated Seedream asset %s", filename)
        return FetchedAsset(asset, filename, local_path)

    def _call_seedream(
        self, prompt: str, width: int, height: int
    ) -> tuple[bytes, dict[str, Any]]:
        """Call Seedream API and return image bytes plus usage info."""
        payload: dict[str, Any] = {
            "model": self.config.SEEDREAM_MODEL,
            "prompt": prompt,
            "n": 1,
            "size": f"{width}x{height}",
            "watermark": False,
        }

        reference_paths: list[Path] = []
        if self.config.VISUAL_REFERENCE_PATH.exists():
            reference_paths.append(self.config.VISUAL_REFERENCE_PATH)

        if reference_paths:
            refs: list[str] = [
                f"data:image/png;base64,{base64.b64encode(p.read_bytes()).decode()}"
                for p in reference_paths
            ]
            payload["image"] = refs if len(refs) > 1 else refs[0]

        response = self.client.post(
            self.config.SEEDREAM_BASE_URL,
            headers={"Authorization": f"Bearer {self.config.ARK_API_KEY}"},
            json=payload,
        )
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
            f"Unexpected Seedream response format: {json.dumps(data, ensure_ascii=False)[:200]}"
        )

    def _download_image(self, asset: Asset, index: int) -> FetchedAsset:
        """Download a remote image asset."""
        if not asset.url:
            raise ValueError(f"image_url asset {asset.id} is missing URL")
        ext = Path(asset.url.split("?")[0]).suffix or ".png"
        filename = f"asset_{index}_image{ext}"
        local_path = self._project_image_path(filename)
        public_path = self._public_path(filename)

        if not public_path.exists():
            response = self.client.get(asset.url)
            response.raise_for_status()
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(response.content)
            shutil.copy2(local_path, public_path)
            logger.info("Downloaded image asset %s", filename)

        return FetchedAsset(asset, filename, local_path)

    def _download_video(self, asset: Asset, index: int) -> FetchedAsset:
        """Download a remote video asset."""
        if not asset.url:
            raise ValueError(f"video_url asset {asset.id} is missing URL")
        ext = Path(asset.url.split("?")[0]).suffix or ".mp4"
        filename = f"asset_{index}_video{ext}"
        local_path = self._project_video_path(filename)
        public_path = self._public_path(filename)

        if not public_path.exists():
            response = self.client.get(asset.url)
            response.raise_for_status()
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(response.content)
            shutil.copy2(local_path, public_path)
            logger.info("Downloaded video asset %s", filename)

        return FetchedAsset(asset, filename, local_path)

    def _local_image(self, asset: Asset, index: int) -> FetchedAsset:
        """Copy a local image into Remotion public/."""
        if not asset.url:
            raise ValueError(f"local_image asset {asset.id} is missing path")
        source = Path(asset.url)
        if not source.exists():
            source = self.config.project_dir / asset.url
        if not source.exists():
            raise FileNotFoundError(f"Local image not found: {asset.url}")

        ext = source.suffix or ".png"
        filename = f"asset_{index}_local_image{ext}"
        public_path = self._public_path(filename)
        if not public_path.exists():
            shutil.copy2(source, public_path)
            logger.info("Copied local image asset %s", filename)

        return FetchedAsset(asset, filename, source)

    def _local_video(self, asset: Asset, index: int) -> FetchedAsset:
        """Copy a local video into Remotion public/."""
        if not asset.url:
            raise ValueError(f"local_video asset {asset.id} is missing path")
        source = Path(asset.url)
        if not source.exists():
            source = self.config.project_dir / asset.url
        if not source.exists():
            raise FileNotFoundError(f"Local video not found: {asset.url}")

        ext = source.suffix or ".mp4"
        filename = f"asset_{index}_local_video{ext}"
        public_path = self._public_path(filename)
        if not public_path.exists():
            shutil.copy2(source, public_path)
            logger.info("Copied local video asset %s", filename)

        return FetchedAsset(asset, filename, source)

    def _seedance_video(self, asset: Asset, index: int) -> FetchedAsset:
        """Placeholder for Seedance-generated video assets."""
        raise NotImplementedError(
            "seedance_video asset type is not supported in the infographic workflow yet"
        )

    def fetch(self, asset: Asset, index: int) -> FetchedAsset:
        """Resolve a single asset."""
        if asset.type == "seedream_image":
            return self._seedream_image(asset, index)
        if asset.type == "image_url":
            return self._download_image(asset, index)
        if asset.type == "video_url":
            return self._download_video(asset, index)
        if asset.type == "local_image":
            return self._local_image(asset, index)
        if asset.type == "local_video":
            return self._local_video(asset, index)
        if asset.type == "seedance_video":
            return self._seedance_video(asset, index)
        raise ValueError(f"Unknown asset type: {asset.type}")

    def fetch_for_shot(self, script: Script, shot_index: int) -> list[FetchedAsset]:
        """Resolve all assets for a single shot."""
        shot = script.shots[shot_index]
        assets: list[FetchedAsset] = []
        for i, asset in enumerate(shot.visual.assets, start=1):
            assets.append(self.fetch(asset, shot_index * 100 + i))
        return assets

    def prepare_public_dir(self) -> None:
        """Ensure Remotion public/ exists and clear runtime files."""
        self.config.REMOTION_PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
        for path in self.config.REMOTION_PUBLIC_DIR.iterdir():
            if path.name == ".gitkeep":
                continue
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()

    def write_manifest(self, script: Script) -> None:
        """Write a small manifest for debugging/inspection."""
        manifest = {
            "project": str(self.config.project_dir),
            "title": script.metadata.title,
            "shots": [shot.shot_id for shot in script.shots],
        }
        manifest_path = self.config.REMOTION_PUBLIC_DIR / "asset-manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @staticmethod
    def _parse_resolution(project_dir: Path) -> tuple[int, int]:
        """Placeholder resolution parser (uses default 9:16)."""
        # The real resolution comes from script metadata via the caller.
        return 1080, 1920

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> AssetFetcher:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
