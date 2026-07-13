"""TTS generation using Edge TTS."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import edge_tts
from pydub import AudioSegment

from .config import Config
from .cost_tracker import CostTracker
from .models import Scene, Script

logger = logging.getLogger(__name__)


class TTSGenerator:
    """Generate audio for all scenes using Edge TTS."""

    def __init__(self, config: Config, cost_tracker: CostTracker | None = None) -> None:
        self.config = config
        self.cost_tracker = cost_tracker

    def _voice_for_scene(self, scene: Scene, script: Script) -> str:
        """Determine TTS voice for a scene.

        Priority: scene.voice -> metadata.voice -> config.TTS_VOICE.
        """
        return (
            (scene.voice.voice_id if scene.voice else None)
            or script.metadata.voice.voice_id
            or self.config.TTS_VOICE
        )

    def _rate_for_scene(self, scene: Scene, script: Script) -> str:
        """Determine Edge TTS rate string for a scene.

        Priority: scene.voice.speed -> metadata.voice.speed.
        """
        speed = 1.0
        if scene.voice is not None:
            speed = scene.voice.speed
        else:
            speed = script.metadata.voice.speed
        # Convert speed multiplier to Edge TTS rate percentage.
        # 1.0 -> +0%, 1.5 -> +50%, 0.8 -> -20%
        return f"{int(round((speed - 1.0) * 100)):+d}%"

    async def _generate_one(self, scene: Scene, script: Script, output_dir: Path) -> Path:
        """Generate audio for a single scene."""
        output_path = output_dir / f"scene_{scene.scene_id}.mp3"
        if output_path.exists():
            logger.info("Audio already exists for scene %s", scene.scene_id)
            return output_path

        voice = self._voice_for_scene(scene, script)
        rate = self._rate_for_scene(scene, script)
        logger.info(
            "Generating TTS for scene %s with voice %s rate %s",
            scene.scene_id,
            voice,
            rate,
        )

        communicate = edge_tts.Communicate(scene.subtitle, voice, rate=rate)
        await communicate.save(str(output_path))

        logger.info("Saved audio for scene %s", scene.scene_id)
        if self.cost_tracker:
            self.cost_tracker.log_tts(
                model=f"edge-tts-{voice}",
                text=scene.subtitle,
                note=f"scene_id={scene.scene_id}, voice={voice}, rate={rate}",
            )
        return output_path

    async def generate(self, script: Script) -> dict[int, Path]:
        """Generate audio for all scenes concurrently."""
        output_dir = Path(self.config.AUDIO_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)

        tasks = [self._generate_one(scene, script, output_dir) for scene in script.scenes]
        paths = await asyncio.gather(*tasks)
        return {scene.scene_id: path for scene, path in zip(script.scenes, paths)}

    def get_duration(self, audio_path: Path) -> float:
        """Return audio duration in seconds."""
        audio = AudioSegment.from_file(audio_path)
        return len(audio) / 1000.0

    def apply_to_script(self, script: Script) -> None:
        """Fill actual_duration for each scene based on generated audio."""
        output_dir = Path(self.config.AUDIO_DIR)
        for scene in script.scenes:
            audio_path = output_dir / f"scene_{scene.scene_id}.mp3"
            if audio_path.exists():
                scene.actual_duration = self.get_duration(audio_path)
            else:
                logger.warning("Audio not found for scene %s", scene.scene_id)
                scene.actual_duration = scene.duration_hint or 3.0
