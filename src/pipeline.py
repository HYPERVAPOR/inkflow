"""Orchestrate the full video generation pipeline."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from .config import Config
from .cost_tracker import CostTracker
from .cover_generator import CoverGenerator
from .image_generator import ImageGenerator
from .models import Script
from .script_loader import load_script, save_script
from .shot_frame_generator import ShotFrameGenerator
from .subtitle_generator import SubtitleGenerator
from .tts_generator import TTSGenerator
from .video_assembler import VideoAssembler
from .video_generator import VideoGenerator

logger = logging.getLogger(__name__)


class Pipeline:
    """End-to-end video generation pipeline."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.config.ensure_dirs()

    def _compute_shot_durations(self, script: Script) -> dict[int, int]:
        """Compute target video duration in seconds for each shot.

        The duration is the sum of actual scene durations rounded up to the
        nearest integer and capped at the model's per-clip limit (12s).
        """
        max_duration = 12
        durations: dict[int, int] = {}
        for shot in script.shots:
            scenes = script.scenes_for_shot(shot)
            total = sum(s.actual_duration or s.duration_hint or 3.0 for s in scenes)
            durations[shot.shot_id] = min(max(int(total) + (1 if total % 1 > 0 else 0), 1), max_duration)
        return durations

    def run(self, script_path: str | Path, bgm_path: str | Path | None = None) -> Path:
        """Run the full pipeline and return the final video path."""
        script = load_script(script_path)
        self.config.validate()

        cost_tracker = CostTracker(self.config)

        # 1. Generate TTS audio (needed for timing in both workflows)
        logger.info("Step 1/5: Generating TTS audio...")
        tts_gen = TTSGenerator(self.config, cost_tracker)
        asyncio.run(tts_gen.generate(script))

        # 2. Compute actual durations
        logger.info("Step 2/5: Computing audio durations...")
        tts_gen.apply_to_script(script)
        save_script(script, Path(self.config.LOGS_DIR) / "script_with_duration.json")

        if script.uses_shots:
            # Shot-based workflow: script -> TTS -> shots -> start frames -> videos
            logger.info("Using shot-based video workflow")

            # 3. Generate start-frame images for shots
            logger.info("Step 3/5: Generating shot start frames...")
            with ShotFrameGenerator(self.config, cost_tracker) as frame_gen:
                start_frame_map = frame_gen.generate(script)

            # 3.5 Generate cover images
            logger.info("Generating cover images...")
            with CoverGenerator(self.config, cost_tracker) as cover_gen:
                cover_gen.generate(script)

            # 4. Generate video clips from start frames
            logger.info("Step 4/5: Generating shot videos...")
            shot_durations = self._compute_shot_durations(script)
            video_gen = VideoGenerator(self.config, cost_tracker)
            asyncio.run(video_gen.generate(script, start_frame_map, shot_durations))
        else:
            # Legacy image-based workflow
            logger.info("Using legacy image-based workflow")

            # 3. Generate images
            logger.info("Step 3/5: Generating images...")
            with ImageGenerator(self.config, cost_tracker) as image_gen:
                image_gen.generate(script)

            # 3.5 Generate cover images
            logger.info("Generating cover images...")
            with CoverGenerator(self.config, cost_tracker) as cover_gen:
                cover_gen.generate(script)

            # 4. No separate video generation step for legacy path
            logger.info("Step 4/5: Image generation complete")

        # 5. Generate subtitles
        logger.info("Step 5/5: Generating subtitles...")
        subtitle_gen = SubtitleGenerator(self.config)
        subtitle_path = subtitle_gen.generate(script)

        # 6. Assemble video
        logger.info("Assembling final video...")
        assembler = VideoAssembler(self.config)
        bgm = Path(bgm_path) if bgm_path else None
        final_path = assembler.assemble(script, subtitle_path, bgm)

        # 7. Save cost summary
        cost_tracker.save()
        summary = cost_tracker.summary()
        logger.info(
            "Total cost: %.6f USD (approx %.4f CNY)",
            summary["total_cost_usd"],
            summary["total_cost_cny_approx"],
        )

        logger.info("Pipeline complete: %s", final_path)
        return final_path

    def run_step(
        self,
        script_path: str | Path,
        step: str,
    ) -> None:
        """Run a single step for debugging."""
        script = load_script(script_path)
        self.config.validate()

        cost_tracker = CostTracker(self.config)

        if step == "images":
            if script.uses_shots:
                with ShotFrameGenerator(self.config, cost_tracker) as gen:
                    gen.generate(script)
            else:
                with ImageGenerator(self.config, cost_tracker) as gen:
                    gen.generate(script)
        elif step == "audio":
            tts_gen = TTSGenerator(self.config, cost_tracker)
            asyncio.run(tts_gen.generate(script))
        elif step == "subtitles":
            tts_gen = TTSGenerator(self.config, cost_tracker)
            tts_gen.apply_to_script(script)
            SubtitleGenerator(self.config).generate(script)
        elif step == "video":
            tts_gen = TTSGenerator(self.config, cost_tracker)
            tts_gen.apply_to_script(script)
            if script.uses_shots:
                with ShotFrameGenerator(self.config, cost_tracker) as frame_gen:
                    start_frame_map = frame_gen.generate(script)
                shot_durations = self._compute_shot_durations(script)
                video_gen = VideoGenerator(self.config, cost_tracker)
                asyncio.run(video_gen.generate(script, start_frame_map, shot_durations))
            subtitle_path = Path(self.config.SUBTITLES_DIR) / "caption.srt"
            VideoAssembler(self.config).assemble(script, subtitle_path)
        else:
            raise ValueError(f"Unknown step: {step}")

        cost_tracker.save()
        summary = cost_tracker.summary()
        logger.info(
            "Step cost: %.6f USD (approx %.4f CNY)",
            summary["total_cost_usd"],
            summary["total_cost_cny_approx"],
        )
