"""Start-frame image generation for shots."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from src.core.config import Config
from src.core.models import Metadata, Script, Shot
from src.cost.tracker import CostTracker
from src.generators.image import ImageGeneratorClient, generate_placeholder

logger = logging.getLogger(__name__)


class StartFrameGenerator:
    """Generate start-frame images for all shots in a script."""

    def __init__(self, config: Config, cost_tracker: CostTracker | None = None) -> None:
        self.config = config
        self.cost_tracker = cost_tracker
        self.image_client = ImageGeneratorClient(config)

    def build_prompt(self, shot: Shot, metadata: Metadata, uses_prev: bool = False) -> str:
        """Combine global style prompt with shot-specific start-frame prompt."""
        return self.image_client.build_prompt(
            content=shot.start_frame_prompt,
            style=metadata.style_prompt,
            system_prompt=metadata.video_system_prompt,
            uses_prev=uses_prev,
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
                self.cost_tracker.log_image_generation(
                    model=self.config.SEEDREAM_MODEL,
                    quantity=1,
                    width=metadata.width,
                    height=metadata.height,
                    usage={},
                    note=f"shot_id={shot.shot_id} (existing, estimated)",
                )
            return output_path

        reference_paths: list[Path] = []
        uses_prev = False
        if self.config.VISUAL_REFERENCE_PATH.exists():
            reference_paths.append(self.config.VISUAL_REFERENCE_PATH)
        else:
            logger.warning(
                "Visual reference image not found at %s", self.config.VISUAL_REFERENCE_PATH
            )

        ref_id = shot.reference_from
        if ref_id == "prev":
            ref_id = shot.shot_id - 1
        if isinstance(ref_id, int) and ref_id in reference_map:
            reference_paths.append(reference_map[ref_id])
            uses_prev = True
        elif ref_id is not None:
            logger.warning("Reference frame not found for shot %s", shot.shot_id)

        prompt = self.build_prompt(shot, metadata, uses_prev=uses_prev)
        logger.info("Generating start frame for shot %s", shot.shot_id)

        try:
            image_bytes, usage = self.image_client.generate(
                prompt=prompt,
                width=metadata.width,
                height=metadata.height,
                reference_paths=reference_paths,
            )
            output_path.write_bytes(image_bytes)
            logger.info("Saved start frame for shot %s", shot.shot_id)
            if self.cost_tracker:
                self.cost_tracker.log_image_generation(
                    model=self.config.SEEDREAM_MODEL,
                    quantity=1,
                    width=metadata.width,
                    height=metadata.height,
                    usage=usage,
                    note=f"shot_id={shot.shot_id}",
                )
            return output_path
        except Exception as e:
            logger.error("Start-frame generation failed for shot %s: %s", shot.shot_id, e)
            if self.cost_tracker:
                self.cost_tracker.log_image_generation(
                    model=self.config.SEEDREAM_MODEL,
                    quantity=0,
                    width=metadata.width,
                    height=metadata.height,
                    cost=0.0,
                    note=f"placeholder for shot_id={shot.shot_id}",
                )
            return generate_placeholder(output_path, metadata.width, metadata.height)

    def generate(self, script: Script) -> dict[int, Path]:
        """Generate start-frame images for all shots respecting dependencies."""
        output_dir = Path(self.config.IMAGES_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)

        shots = sorted(script.shots, key=lambda s: s.shot_id)
        shot_by_id = {s.shot_id: s for s in shots}
        reference_map: dict[int, Path] = {}

        # Build dependency graph from reference_from fields.
        parent_of: dict[int, int | None] = {}
        for shot in shots:
            ref = shot.reference_from
            if ref == "prev":
                parent = shot.shot_id - 1
            elif isinstance(ref, int):
                parent = ref
            else:
                parent = None
            if parent is not None and parent in shot_by_id:
                parent_of[shot.shot_id] = parent
            else:
                parent_of[shot.shot_id] = None

        remaining = {s.shot_id for s in shots}
        completed: set[int] = set()

        def _can_run(sid: int) -> bool:
            parent = parent_of.get(sid)
            return parent is None or parent in completed

        # Topological wave generation: run all currently-runnable shots concurrently.
        while remaining:
            runnable = sorted(sid for sid in remaining if _can_run(sid))
            if not runnable:
                raise RuntimeError("Dependency cycle detected among shots")

            logger.info(
                "Generating %s start frame(s) concurrently: %s",
                len(runnable),
                runnable,
            )
            runnable_shots = [shot_by_id[sid] for sid in runnable]
            with ThreadPoolExecutor(max_workers=self.config.SEEDREAM_MAX_WORKERS) as executor:
                futures = {
                    executor.submit(
                        self._generate_one, shot, script.metadata, output_dir, reference_map
                    ): shot
                    for shot in runnable_shots
                }
                for future in as_completed(futures):
                    shot = futures[future]
                    try:
                        path = future.result()
                        reference_map[shot.shot_id] = path
                        completed.add(shot.shot_id)
                    except Exception as e:
                        logger.error(
                            "Failed to generate start frame for shot %s: %s", shot.shot_id, e
                        )
                        raise
            remaining -= completed

        return reference_map

    def close(self) -> None:
        self.image_client.close()

    def __enter__(self) -> "StartFrameGenerator":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
