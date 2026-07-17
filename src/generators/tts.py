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

from src.core.config import Config
from src.core.models import Script, Subtitle
from src.cost.tracker import CostTracker
from src.media.audio import get_duration

logger = logging.getLogger(__name__)

VOLCANO_VOICES_V3: dict[str, str] = {
    "zh_male_dayi_uranus_bigtts": "大壹 2.0",
    "zh_female_vv_uranus_bigtts": "Vivi 2.0",
    "zh_female_cancan_uranus_bigtts": "知性灿灿 2.0",
    "zh_female_sajiaoxuemei_uranus_bigtts": "撒娇学妹 2.0",
    "zh_female_peiqi_uranus_bigtts": "佩奇猪 2.0",
    "zh_female_wenroushunv_uranus_bigtts": "温柔淑女 2.0",
    "zh_female_gufengshaoyu_uranus_bigtts": "古风少御 2.0",
    "zh_female_wenjingmaomao_uranus_bigtts": "文静毛毛 2.0",
    "zh_male_zhuangzhou_uranus_bigtts": "庄周 2.0",
    "zh_male_kailangdidi_uranus_bigtts": "开朗弟弟 2.0",
    "zh_male_fanjuanqingnian_uranus_bigtts": "反卷青年 2.0",
    "zh_male_youyoujunzi_uranus_bigtts": "悠悠君子 2.0",
    "zh_male_zhubajie_uranus_bigtts": "猪八戒 2.0",
    "zh_male_sunwukong_uranus_bigtts": "猴哥 2.0",
}

VOLCANO_VOICES_V1: dict[str, str] = {
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

VOLCANO_VOICES = VOLCANO_VOICES_V3


class TTSGenerator:
    """Generate audio for all subtitles using Edge TTS or Volcano TTS."""

    def __init__(self, config: Config, cost_tracker: CostTracker | None = None) -> None:
        self.config = config
        self.cost_tracker = cost_tracker
        self._volcano_sem = asyncio.Semaphore(config.VOLCANO_TTS_MAX_WORKERS)

    def _provider_for_subtitle(self, subtitle: Subtitle, script: Script) -> str:
        """Select TTS provider for a subtitle."""
        return (
            (subtitle.voice.provider if subtitle.voice else None)
            or (script.metadata.voice.provider if script.metadata.voice else None)
            or self.config.TTS_PROVIDER
        )

    def _voice_for_subtitle(self, subtitle: Subtitle, script: Script, provider: str) -> str:
        """Determine TTS voice/speaker for a subtitle."""
        voice_id = (subtitle.voice.voice_id if subtitle.voice else None) or (
            script.metadata.voice.voice_id if script.metadata.voice else None
        )
        if voice_id:
            return voice_id
        return self.config.VOLCANO_TTS_VOICE if provider == "volcano" else self.config.TTS_VOICE

    def _speed_for_subtitle(self, subtitle: Subtitle, script: Script) -> float:
        """Determine speech speed multiplier for a subtitle."""
        if subtitle.voice is not None:
            return subtitle.voice.speed
        if script.metadata.voice is not None:
            return script.metadata.voice.speed
        return self.config.TTS_SPEED

    @staticmethod
    def _edge_rate(speed: float) -> str:
        """Convert a speed multiplier to an Edge TTS rate string."""
        return f"{int(round((speed - 1.0) * 100)):+d}%"

    async def _generate_edge(
        self,
        subtitle: Subtitle,
        script: Script,
        output_path: Path,
    ) -> None:
        """Generate a subtitle's audio using Edge TTS."""
        voice = self._voice_for_subtitle(subtitle, script, "edge_tts")
        rate = self._edge_rate(self._speed_for_subtitle(subtitle, script))
        logger.info(
            "Generating Edge TTS for subtitle %s with voice %s rate %s",
            subtitle.subtitle_id,
            voice,
            rate,
        )

        communicate = edge_tts.Communicate(subtitle.text, voice, rate=rate)
        await communicate.save(str(output_path))
        logger.info("Saved Edge TTS audio for subtitle %s", subtitle.subtitle_id)

        if self.cost_tracker:
            self.cost_tracker.log_tts(
                model=f"edge-tts-{voice}",
                text=subtitle.text,
                note=f"subtitle_id={subtitle.subtitle_id}, voice={voice}, rate={rate}",
            )

    async def _generate_volcano(
        self,
        subtitle: Subtitle,
        script: Script,
        output_path: Path,
    ) -> None:
        """Generate a subtitle's audio using Volcano TTS."""
        async with self._volcano_sem:
            voice = self._voice_for_subtitle(subtitle, script, "volcano")
            speed = self._speed_for_subtitle(subtitle, script)
            logger.info(
                "Generating Volcano TTS for subtitle %s with voice %s speed %.2f",
                subtitle.subtitle_id,
                voice,
                speed,
            )

            if "/api/v1/tts" in self.config.VOLCANO_TTS_BASE_URL:
                await self._generate_volcano_v1(subtitle, output_path, voice, speed)
            else:
                await self._generate_volcano_v3(subtitle, output_path, voice, speed)

    async def _generate_volcano_v1(
        self,
        subtitle: Subtitle,
        output_path: Path,
        voice: str,
        speed: float,
    ) -> None:
        """Generate audio using the legacy Volcano TTS v1 HTTP endpoint."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer;{self.config.VOLCANO_TTS_ACCESS_TOKEN}",
        }
        payload = {
            "app": {
                "appid": self.config.VOLCANO_TTS_APP_ID,
                "token": self.config.VOLCANO_TTS_ACCESS_TOKEN,
                "cluster": self.config.VOLCANO_TTS_CLUSTER,
            },
            "user": {"uid": "inkflow"},
            "audio": {
                "voice_type": voice,
                "encoding": "mp3",
                "speed_ratio": speed,
                "volume_ratio": 1.0,
                "pitch_ratio": 1.0,
            },
            "request": {
                "reqid": str(uuid.uuid4()),
                "text": subtitle.text,
                "text_type": "plain",
                "operation": "query",
                "with_frontend": 1,
            },
        }

        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            response = await client.post(
                self.config.VOLCANO_TTS_BASE_URL,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            code = data.get("code")
            if code is not None and code != 0:
                msg = data.get("message", "")
                raise RuntimeError(f"Volcano TTS v1 returned error: {msg} (code={code})")

            audio_b64 = data.get("data")
            if not audio_b64:
                raise RuntimeError(
                    f"Volcano TTS v1 returned empty audio for subtitle {subtitle.subtitle_id}"
                )

            audio_bytes = base64.b64decode(audio_b64)

        output_path.write_bytes(audio_bytes)
        logger.info("Saved Volcano TTS v1 audio for subtitle %s", subtitle.subtitle_id)

        if self.cost_tracker:
            self.cost_tracker.log_tts(
                model=f"volcano-tts-v1-{voice}",
                text=subtitle.text,
                note=f"subtitle_id={subtitle.subtitle_id}, voice={voice}, speed={speed}",
            )

    async def _generate_volcano_v3(
        self,
        subtitle: Subtitle,
        output_path: Path,
        voice: str,
        speed: float,
    ) -> None:
        """Generate audio using the Volcano TTS v3 unidirectional endpoint."""
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

        speech_rate = int(round((speed - 1.0) * 100))
        speech_rate = max(-50, min(100, speech_rate))
        payload = {
            "user": {"uid": "inkflow"},
            "req_params": {
                "text": subtitle.text,
                "speaker": voice,
                "audio_params": {
                    "format": "mp3",
                    "sample_rate": 24000,
                    "speech_rate": speech_rate,
                },
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
                response.raise_for_status()
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
                    if code is not None and str(code) not in {"0", "20000000"}:
                        msg = data.get("message", "")
                        raise RuntimeError(f"Volcano TTS v3 returned error: {msg} (code={code})")

                    chunk = data.get("data")
                    if chunk:
                        audio_bytes.extend(base64.b64decode(chunk))

        if not audio_bytes:
            raise RuntimeError(
                f"Volcano TTS v3 returned empty audio for subtitle {subtitle.subtitle_id}"
            )

        output_path.write_bytes(audio_bytes)
        logger.info("Saved Volcano TTS v3 audio for subtitle %s", subtitle.subtitle_id)

        if self.cost_tracker:
            self.cost_tracker.log_tts(
                model=f"volcano-tts-v3-{voice}",
                text=subtitle.text,
                note=f"subtitle_id={subtitle.subtitle_id}, voice={voice}, speed={speed}",
            )

    async def _generate_one(
        self,
        subtitle: Subtitle,
        script: Script,
        output_dir: Path,
    ) -> Path:
        """Generate audio for a single subtitle using its configured provider."""
        output_path = output_dir / f"subtitle_{subtitle.subtitle_id}.mp3"
        if output_path.exists():
            logger.info("Audio already exists for subtitle %s", subtitle.subtitle_id)
            return output_path

        provider = self._provider_for_subtitle(subtitle, script)
        if provider == "volcano":
            await self._generate_volcano(subtitle, script, output_path)
        else:
            await self._generate_edge(subtitle, script, output_path)

        return output_path

    async def generate(self, script: Script) -> dict[int, Path]:
        """Generate audio for all subtitles concurrently."""
        output_dir = Path(self.config.AUDIO_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)

        tasks = [self._generate_one(subtitle, script, output_dir) for subtitle in script.subtitles]
        paths = await asyncio.gather(*tasks)
        return {subtitle.subtitle_id: path for subtitle, path in zip(script.subtitles, paths)}

    def apply_to_script(self, script: Script) -> None:
        """Fill duration for each subtitle based on generated audio."""
        output_dir = Path(self.config.AUDIO_DIR)
        for subtitle in script.subtitles:
            audio_path = output_dir / f"subtitle_{subtitle.subtitle_id}.mp3"
            if audio_path.exists():
                subtitle.duration = get_duration(audio_path)
            else:
                logger.warning("Audio not found for subtitle %s", subtitle.subtitle_id)
                subtitle.duration = subtitle.duration or 3.0
