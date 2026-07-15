"""Generate short Volcano TTS samples for each supported voice.

Usage:
    export VOLCANO_TTS_API_KEY=...          # new console
    # or
    export VOLCANO_TTS_APP_ID=...
    export VOLCANO_TTS_ACCESS_TOKEN=...     # legacy console

    PYTHONPATH=. uv run python scripts/generate_volcano_voice_samples.py

Outputs are written to output/volcano_voice_samples/.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from src.config import Config
from src.models import Metadata, Scene, Script, Voice
from src.tts_generator import VOLCANO_VOICES_V1, VOLCANO_VOICES_V3, TTSGenerator

SAMPLE_TEXT = "你好，这是火山引擎语音合成大模型的音色试听。"


def _voice_list(config: Config) -> dict[str, str]:
    """Pick the right voice list for the configured Volcano endpoint/version."""
    is_v1 = (
        "/api/v1/tts" in config.VOLCANO_TTS_BASE_URL
        or config.VOLCANO_TTS_RESOURCE_ID in {"seed-tts-1.0", "volc.service_type.10029"}
    )
    return VOLCANO_VOICES_V1 if is_v1 else VOLCANO_VOICES_V3


async def generate_sample(generator: TTSGenerator, voice_id: str, output_path: Path) -> None:
    scene = Scene(
        scene_id=1,
        subtitle=SAMPLE_TEXT,
        voice=Voice(voice_id=voice_id, provider="volcano"),
    )
    script = Script(
        scenes=[scene],
        metadata=Metadata(title="volcano-tts-voice-samples", voice=Voice(provider="volcano")),
    )
    await generator._generate_volcano(scene, script, output_path)


async def main() -> None:
    config = Config(Path("projects") / "example-proj")
    config.ensure_dirs()

    has_api_key = bool(config.VOLCANO_TTS_API_KEY)
    has_legacy_creds = bool(config.VOLCANO_TTS_APP_ID) and bool(config.VOLCANO_TTS_ACCESS_TOKEN)
    if not (has_api_key or has_legacy_creds):
        print(
            "Error: set either VOLCANO_TTS_API_KEY (new console) "
            "or both VOLCANO_TTS_APP_ID and VOLCANO_TTS_ACCESS_TOKEN (legacy console)",
            file=sys.stderr,
        )
        sys.exit(1)

    generator = TTSGenerator(config)
    output_dir = Path("output") / "volcano_voice_samples"
    output_dir.mkdir(parents=True, exist_ok=True)

    voices = _voice_list(config)
    for voice_id, description in voices.items():
        output_path = output_dir / f"{voice_id}.mp3"
        if output_path.exists():
            print(f"Skipping existing: {voice_id} ({description})")
            continue

        print(f"Generating: {voice_id} ({description})")
        try:
            await generate_sample(generator, voice_id, output_path)
            duration = generator.get_duration(output_path)
            print(f"  Saved {output_path} ({duration:.2f}s)")
        except Exception as exc:  # noqa: BLE001
            print(f"  Failed: {exc}", file=sys.stderr)

    print(f"\nSamples saved to {output_dir.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
