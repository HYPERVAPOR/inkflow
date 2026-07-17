"""Orchestrate the full video generation pipeline."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from src.core.config import Config
from src.core.models import Script
from src.core.script import save_script
from src.cost.tracker import CostTracker
from src.generators.cover import CoverGenerator
from src.generators.image import ImageGeneratorClient, generate_placeholder
from src.generators.start_frame import StartFrameGenerator
from src.generators.subtitle import SubtitleGenerator
from src.generators.tts import TTSGenerator
from src.generators.video import VideoGenerator
from src.pipeline.assembler import VideoAssembler

logger = logging.getLogger(__name__)


class Pipeline:
    """End-to-end video generation pipeline."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.config.ensure_dirs()

    def _compute_shot_durations(self, script: Script) -> dict[int, int]:
        """Compute target video duration in seconds for each shot."""
        durations: dict[int, int] = {}
        for shot in script.shots:
            total = script.shot_duration(shot)
            durations[shot.shot_id] = max(1, min(int(total) + (1 if total % 1 > 0 else 0), 12))
        return durations

    def run_audio(self, script: Script, cost_tracker: CostTracker | None = None) -> None:
        """Generate TTS audio and apply durations to subtitles."""
        logger.info("Step: Generating TTS audio...")
        tts_gen = TTSGenerator(self.config, cost_tracker)
        asyncio.run(tts_gen.generate(script))
        tts_gen.apply_to_script(script)
        save_script(script, Path(self.config.LOGS_DIR) / "subtitles_with_duration.json")

    def run_images(self, script: Script, cost_tracker: CostTracker | None = None) -> None:
        """Generate images (start frames for shots or legacy subtitle images)."""
        if script.shots:
            logger.info("Step: Generating shot start frames...")
            with StartFrameGenerator(self.config, cost_tracker) as gen:
                gen.generate(script)
        else:
            logger.info("Step: Generating legacy images...")
            output_dir = Path(self.config.IMAGES_DIR)
            output_dir.mkdir(parents=True, exist_ok=True)
            client = ImageGeneratorClient(self.config)
            for subtitle in script.subtitles:
                output_path = output_dir / f"subtitle_{subtitle.subtitle_id}.png"
                if output_path.exists():
                    continue
                prompt = client.build_prompt(
                    content=subtitle.text,
                    style=script.metadata.style_prompt,
                    system_prompt=script.metadata.video_system_prompt,
                )
                try:
                    image_bytes, usage = client.generate(
                        prompt,
                        script.metadata.width,
                        script.metadata.height,
                        [self.config.VISUAL_REFERENCE_PATH],
                    )
                    output_path.write_bytes(image_bytes)
                    if cost_tracker:
                        cost_tracker.log_image_generation(
                            model=self.config.SEEDREAM_MODEL,
                            quantity=1,
                            width=script.metadata.width,
                            height=script.metadata.height,
                            usage=usage,
                            note=f"subtitle_id={subtitle.subtitle_id}",
                        )
                except Exception as e:
                    logger.error(
                        "Failed to generate image for subtitle %s: %s", subtitle.subtitle_id, e
                    )
                    generate_placeholder(output_path, script.metadata.width, script.metadata.height)
            client.close()

    def run_covers(self, script: Script, cost_tracker: CostTracker | None = None) -> None:
        """Generate cover images."""
        logger.info("Step: Generating cover images...")
        with CoverGenerator(self.config, cost_tracker) as gen:
            gen.generate(script)

    def run_videos(
        self, script: Script, cost_tracker: CostTracker | None = None
    ) -> dict[int, Path]:
        """Generate video clips for shots."""
        logger.info("Step: Generating shot videos...")
        if not script.shots:
            return {}

        with StartFrameGenerator(self.config) as frame_gen:
            start_frame_map = frame_gen.generate(script)

        shot_durations = self._compute_shot_durations(script)
        video_gen = VideoGenerator(self.config, cost_tracker)
        return asyncio.run(video_gen.generate(script, start_frame_map, shot_durations))

    def run_subtitles(self, script: Script) -> Path:
        """Generate SRT subtitle file."""
        logger.info("Step: Generating subtitles...")
        subtitle_gen = SubtitleGenerator(self.config)
        return subtitle_gen.generate(script)

    def run_assemble(
        self,
        script: Script,
        subtitle_path: Path,
        bgm_path: Path | None = None,
    ) -> Path:
        """Assemble final video."""
        logger.info("Step: Assembling final video...")
        assembler = VideoAssembler(self.config)
        return assembler.assemble(script, subtitle_path, bgm_path)

    def run(self, script: Script, bgm_path: Path | None = None) -> Path:
        """Run the full pipeline and return the final video path."""
        self.config.validate()
        cost_tracker = CostTracker(self.config)

        self.run_audio(script, cost_tracker)
        self.run_images(script, cost_tracker)
        self.run_covers(script, cost_tracker)

        if script.shots:
            self.run_videos(script, cost_tracker)

        subtitle_path = self.run_subtitles(script)
        final_path = self.run_assemble(script, subtitle_path, bgm_path)

        cost_tracker.save()
        summary = cost_tracker.summary()
        logger.info(
            "Total cost: %.6f USD (approx %.4f CNY)",
            summary["total_cost_usd"],
            summary["total_cost_cny_approx"],
        )

        logger.info("Pipeline complete: %s", final_path)
        return final_path

    def run_step(self, script: Script, step: str) -> Path | None:
        """Run a single step for debugging."""
        self.config.validate()
        cost_tracker = CostTracker(self.config)

        result: Path | None = None
        if step == "audio":
            self.run_audio(script, cost_tracker)
        elif step == "images":
            self.run_images(script, cost_tracker)
        elif step == "covers":
            self.run_covers(script, cost_tracker)
        elif step == "video":
            self.run_videos(script, cost_tracker)
        elif step == "subtitles":
            result = self.run_subtitles(script)
        elif step == "assemble":
            subtitle_path = self.run_subtitles(script)
            result = self.run_assemble(script, subtitle_path)
        else:
            raise ValueError(f"Unknown step: {step}")

        cost_tracker.save()
        summary = cost_tracker.summary()
        logger.info(
            "Step cost: %.6f USD (approx %.4f CNY)",
            summary["total_cost_usd"],
            summary["total_cost_cny_approx"],
        )

        return result
