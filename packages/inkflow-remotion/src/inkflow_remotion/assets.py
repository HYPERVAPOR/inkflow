"""Prepare Remotion public/ assets for the current project."""

from __future__ import annotations

import json
import logging
import shutil

from inkflow_core.config import Config
from inkflow_core.models import Script

logger = logging.getLogger(__name__)


class AssetManager:
    """Copy project assets into the Remotion public directory."""

    def __init__(self, config: Config) -> None:
        self.config = config

    def _clear_public(self) -> None:
        """Remove previous runtime assets from Remotion public/."""
        public_dir = self.config.REMOTION_PUBLIC_DIR
        if not public_dir.exists():
            return
        for path in public_dir.iterdir():
            if path.name == ".gitkeep":
                continue
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()

    def _copy_images(self) -> None:
        """Copy generated images into Remotion public/."""
        images_dir = self.config.IMAGES_DIR
        if not images_dir.exists():
            return
        for image_path in images_dir.iterdir():
            if image_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
                dest = self.config.REMOTION_PUBLIC_DIR / image_path.name
                shutil.copy2(image_path, dest)
                logger.debug("Copied asset: %s", image_path.name)

    def _write_manifest(self, script: Script) -> None:
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

    def prepare(self, script: Script) -> None:
        """Prepare Remotion public/ directory for rendering."""
        self.config.REMOTION_PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
        self._clear_public()
        self._copy_images()
        self._write_manifest(script)
        logger.info("Prepared Remotion public/ directory")
