"""Orchestrate the full video generation pipeline."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from inkflow_assembly.assembler import VideoAssembler
from inkflow_core.config import Config
from inkflow_core.models import Script
from inkflow_core.script_loader import load_script, save_script
from inkflow_generators.cost import CostTracker
from inkflow_generators.cover import CoverGenerator
from inkflow_generators.image.seedream import ImageGenerator
from inkflow_generators.image.shot_frame import ShotFrameGenerator
from inkflow_generators.subtitle import SubtitleGenerator
from inkflow_generators.tts.generator import TTSGenerator

from .base import WorkflowRegistry

logger = logging.getLogger(__name__)


class Pipeline:
    """End-to-end video generation pipeline."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.config.ensure_dirs()

    def _run_tts_and_compute_durations(self, script: Script, cost_tracker: CostTracker) -> None:
        """Generate TTS audio and compute actual scene durations."""
        logger.info("Step 1/5: Generating TTS audio...")
        tts_gen = TTSGenerator(self.config, cost_tracker)
        asyncio.run(tts_gen.generate(script))

        logger.info("Step 2/5: Computing audio durations...")
        tts_gen.apply_to_script(script)
        save_script(script, Path(self.config.LOGS_DIR) / "script_with_duration.json")

    def run(self, script_path: str | Path, bgm_path: str | Path | None = None) -> Path:
        """Run the full pipeline and return the final video path."""
        script = load_script(script_path)
        self.config.validate()

        cost_tracker = CostTracker(self.config)

        # 1-2. TTS and timing (shared by all workflows)
        self._run_tts_and_compute_durations(script, cost_tracker)

        # 3-5. Dispatch to the correct workflow for media generation
        workflow_cls = WorkflowRegistry.resolve(script)
        workflow = workflow_cls(self.config, cost_tracker)
        output = asyncio.run(workflow.run(script))

        # 6. Assemble final video
        logger.info("Assembling final video...")
        assembler = VideoAssembler(self.config)
        bgm = Path(bgm_path) if bgm_path else None
        if output.subtitle_path is None:
            raise RuntimeError("Workflow did not produce a subtitle path")
        final_path = assembler.assemble(
            script, output.subtitle_path, bgm, scene_clips=output.scene_clips
        )

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

        if step == "audio":
            tts_gen = TTSGenerator(self.config, cost_tracker)
            asyncio.run(tts_gen.generate(script))
        elif step == "subtitles":
            tts_gen = TTSGenerator(self.config, cost_tracker)
            tts_gen.apply_to_script(script)
            SubtitleGenerator(self.config).generate(script)
        elif step == "images":
            self._run_tts_and_compute_durations(script, cost_tracker)
            workflow_name = script.resolved_workflow
            if workflow_name == "shot":
                with ShotFrameGenerator(self.config, cost_tracker) as gen:
                    gen.generate(script)
            else:
                with ImageGenerator(self.config, cost_tracker) as gen:
                    gen.generate_for_script(script)
            with CoverGenerator(self.config, cost_tracker) as gen:
                gen.generate(script)
        elif step == "video":
            self._run_tts_and_compute_durations(script, cost_tracker)
            workflow_cls = WorkflowRegistry.resolve(script)
            workflow = workflow_cls(self.config, cost_tracker)
            output = asyncio.run(workflow.run(script))
            if output.subtitle_path is None:
                raise RuntimeError("Workflow did not produce a subtitle path")
            VideoAssembler(self.config).assemble(script, output.subtitle_path)
        else:
            raise ValueError(f"Unknown step: {step}")

        cost_tracker.save()
        summary = cost_tracker.summary()
        logger.info(
            "Step cost: %.6f USD (approx %.4f CNY)",
            summary["total_cost_usd"],
            summary["total_cost_cny_approx"],
        )
