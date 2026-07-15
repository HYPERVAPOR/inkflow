"""TTS generation supporting Edge TTS and Volcano (Doubao) TTS."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import uuid
from pathlib import Path

import edge_tts
import httpx
from pydub import AudioSegment  # type: ignore[import-untyped]

from .config import Config
from .cost_tracker import CostTracker
from .models import Scene, Script

logger = logging.getLogger(__name__)


# Verified Chinese voices for Volcano TTS v3 (seed-tts-2.0 / volc.service_type.10029).
VOLCANO_VOICES: dict[str, str] = {
    "zh_female_sajiaonvyou_moon_bigtts": "撒娇女友",
    "zh_female_gaolengyujie_moon_bigtts": "高冷御姐",
    "zh_female_tianmeixiaoyuan_moon_bigtts": "甜美校园",
    "zh_female_yuanqinvyou_moon_bigtts": "元气女友",
    "zh_female_wanwanxiaohe_moon_bigtts": "弯弯小何",
    "zh_female_linjianvhai_moon_bigtts": "邻家女孩",
    "zh_male_aojiaobazong_moon_bigtts": "傲娇霸总",
    "zh_male_jingqiangkanye_moon_bigtts": "京腔侃爷",
    "zh_male_wennuanahu_moon_bigtts": "温暖阿虎",
    "zh_male_yangguangqingnian_moon_bigtts": "阳光青年",
}


class TTSGenerator:
    """Generate audio for all scenes using Edge TTS or Volcano TTS."""

    def __init__(self, config: Config, cost_tracker: CostTracker | None = None) -> None:
        self.config = config
        self.cost_tracker = cost_tracker

    def _provider_for_scene(self, scene: Scene, script: Script) -> str:
        """Select TTS provider for a scene.

        Priority: scene.voice.provider -> metadata.voice.provider -> config.TTS_PROVIDER.
        """
        return (
            (scene.voice.provider if scene.voice else None)
            or script.metadata.voice.provider
            or self.config.TTS_PROVIDER
        )

    def _voice_for_scene(self, scene: Scene, script: Script, provider: str) -> str:
        """Determine TTS voice/speaker for a scene."""
        voice_id = (
            (scene.voice.voice_id if scene.voice else None)
            or script.metadata.voice.voice_id
        )
        if voice_id:
            return voice_id
        return (
            self.config.VOLCANO_TTS_VOICE
            if provider == "volcano"
            else self.config.TTS_VOICE
        )

    def _speed_for_scene(self, scene: Scene, script: Script) -> float:
        """Determine speech speed multiplier for a scene."""
        if scene.voice is not None:
            return scene.voice.speed
        return script.metadata.voice.speed

    def _edge_rate(self, speed: float) -> str:
        """Convert a speed multiplier to an Edge TTS rate string."""
        # 1.0 -> +0%, 1.5 -> +50%, 0.8 -> -20%
        return f"{int(round((speed - 1.0) * 100)):+d}%"

    async def _generate_edge(
        self,
        scene: Scene,
        script: Script,
        output_path: Path,
    ) -> None:
        """Generate a scene's audio using Edge TTS."""
        voice = self._voice_for_scene(scene, script, "edge_tts")
        rate = self._edge_rate(self._speed_for_scene(scene, script))
        logger.info(
            "Generating Edge TTS for scene %s with voice %s rate %s",
            scene.scene_id,
            voice,
            rate,
        )

        communicate = edge_tts.Communicate(scene.subtitle, voice, rate=rate)
        await communicate.save(str(output_path))

        logger.info("Saved Edge TTS audio for scene %s", scene.scene_id)
        if self.cost_tracker:
            self.cost_tracker.log_tts(
                model=f"edge-tts-{voice}",
                text=scene.subtitle,
                note=f"scene_id={scene.scene_id}, voice={voice}, rate={rate}",
            )

    async def _generate_volcano(
        self,
        scene: Scene,
        script: Script,
        output_path: Path,
    ) -> None:
        """Generate a scene's audio using Volcano TTS v3."""
        voice = self._voice_for_scene(scene, script, "volcano")
        speed = self._speed_for_scene(scene, script)
        logger.info(
            "Generating Volcano TTS for scene %s with voice %s speed %.2f",
            scene.scene_id,
            voice,
            speed,
        )

        if self.config.VOLCANO_TTS_API_KEY:
            headers = {
                "Content-Type": "application/json",
                "X-Api-Key": self.config.VOLCANO_TTS_API_KEY,
                "X-Api-Resource-Id": self.config.VOLCANO_TTS_RESOURCE_ID,
                "X-Api-Request-Id": str(uuid.uuid4()),
            }
        else:
            headers = {
                "Content-Type": "application/json",
                "X-Api-App-Id": self.config.VOLCANO_TTS_APP_ID,
                "X-Api-Access-Key": self.config.VOLCANO_TTS_ACCESS_TOKEN,
                "X-Api-Resource-Id": self.config.VOLCANO_TTS_RESOURCE_ID,
                "X-Api-Request-Id": str(uuid.uuid4()),
            }
        payload = {
            "user": {"uid": "inkflow"},
            "req_params": {
                "text": scene.subtitle,
                "speaker": voice,
                "speed_ratio": speed,
                "audio_params": {"format": "mp3", "sample_rate": 24000},
            },
        }

        audio_bytes = bytearray()
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            async with client.stream(
                "POST",
                self.config.VOLCANO_TTS_BASE_URL,
                headers=headers,
                json=payload,
            ) as response:
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    raise RuntimeError(
                        f"Volcano TTS request failed: {exc.response.status_code} "
                        f"{exc.response.text}"
                    ) from exc

                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        logger.debug("Skipping non-JSON Volcano TTS chunk: %s", line)
                        continue

                    code = data.get("code")
                    if code is not None and code != 0:
                        raise RuntimeError(
                            f"Volcano TTS returned error: {data.get('message')} (code={code})"
                        )

                    chunk = data.get("data")
                    if chunk:
                        audio_bytes.extend(base64.b64decode(chunk))

        if not audio_bytes:
            raise RuntimeError(
                f"Volcano TTS returned empty audio for scene {scene.scene_id}"
            )

        output_path.write_bytes(audio_bytes)
        logger.info("Saved Volcano TTS audio for scene %s", scene.scene_id)

        if self.cost_tracker:
            self.cost_tracker.log_tts(
                model=f"volcano-tts-{voice}",
                text=scene.subtitle,
                note=f"scene_id={scene.scene_id}, voice={voice}, speed={speed}",
            )

    async def _generate_one(
        self,
        scene: Scene,
        script: Script,
        output_dir: Path,
    ) -> Path:
        """Generate audio for a single scene using its configured provider."""
        output_path = output_dir / f"scene_{scene.scene_id}.mp3"
        if output_path.exists():
            logger.info("Audio already exists for scene %s", scene.scene_id)
            return output_path

        provider = self._provider_for_scene(scene, script)
        if provider == "volcano":
            await self._generate_volcano(scene, script, output_path)
        else:
            await self._generate_edge(scene, script, output_path)

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
