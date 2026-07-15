"""Generate short Volcano TTS samples for each supported voice.

Usage:
    export VOLCANO_TTS_APP_ID=...
    export VOLCANO_TTS_ACCESS_TOKEN=...
    PYTHONPATH=. uv run python scripts/generate_volcano_voice_samples.py

Outputs are written to output/volcano_voice_samples/.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from src.config import Config
from src.models import Metadata, Scene, Script, Voice
from src.tts_generator import VOLCANO_VOICES, TTSGenerator

SAMPLE_TEXT = "你好，这是火山引擎语音合成大模型的音色试听。"


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

    if not config.VOLCANO_TTS_APP_ID or not config.VOLCANO_TTS_ACCESS_TOKEN:
        print(
            "Error: VOLCANO_TTS_APP_ID and VOLCANO_TTS_ACCESS_TOKEN must be set",
            file=sys.stderr,
        )
        sys.exit(1)

    generator = TTSGenerator(config)
    output_dir = Path("output") / "volcano_voice_samples"
    output_dir.mkdir(parents=True, exist_ok=True)

    for voice_id, description in VOLCANO_VOICES.items():
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
