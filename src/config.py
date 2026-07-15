"""Configuration loaded from environment variables and project path."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class Config:
    """Application configuration for a specific video project."""

    # Ark / Volces
    ARK_API_KEY: str = os.getenv("ARK_API_KEY", "")

    # Seedream image generation
    SEEDREAM_MODEL: str = os.getenv("SEEDREAM_MODEL", "doubao-seedream-5-0-pro-260628")
    SEEDREAM_BASE_URL: str = os.getenv(
        "SEEDREAM_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3/images/generations"
    )
    SEEDREAM_MAX_WORKERS: int = int(os.getenv("SEEDREAM_MAX_WORKERS", "32"))

    # Seedance video generation
    SEEDANCE_MODEL: str = os.getenv("SEEDANCE_MODEL", "doubao-seedance-1-0-pro-250528")
    SEEDANCE_BASE_URL: str = os.getenv(
        "SEEDANCE_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"
    )
    SEEDANCE_MAX_WORKERS: int = int(os.getenv("SEEDANCE_MAX_WORKERS", "10"))

    # TTS
    TTS_PROVIDER: str = os.getenv("TTS_PROVIDER", "edge_tts")
    TTS_VOICE: str = os.getenv("TTS_VOICE", "zh-CN-YunjianNeural")
    TTS_SPEED: float = float(os.getenv("TTS_SPEED", "1.2"))

    # Volcano TTS (Doubao / Seed-TTS)
    # New BytePlus Speech Console uses a single API key.
    VOLCANO_TTS_API_KEY: str = os.getenv("VOLCANO_TTS_API_KEY", "")
    # Legacy Speech Console uses App ID + Access Token.
    VOLCANO_TTS_APP_ID: str = os.getenv("VOLCANO_TTS_APP_ID", "")
    VOLCANO_TTS_ACCESS_TOKEN: str = os.getenv("VOLCANO_TTS_ACCESS_TOKEN", "")
    VOLCANO_TTS_BASE_URL: str = os.getenv(
        "VOLCANO_TTS_BASE_URL", "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
    )
    VOLCANO_TTS_RESOURCE_ID: str = os.getenv("VOLCANO_TTS_RESOURCE_ID", "volc.service_type.10029")
    VOLCANO_TTS_VOICE: str = os.getenv("VOLCANO_TTS_VOICE", "zh_male_aojiaobazong_moon_bigtts")

    def __init__(self, project_dir: str | Path) -> None:
        self.project_dir = Path(project_dir)

        # Project-local paths
        self.ASSETS_DIR = self.project_dir / "assets"
        self.IMAGES_DIR = self.ASSETS_DIR / "images"
        self.VIDEOS_DIR = self.ASSETS_DIR / "videos"
        self.AUDIO_DIR = self.ASSETS_DIR / "audio"
        self.MUSIC_DIR = self.ASSETS_DIR / "music"
        self.SUBTITLES_DIR = self.ASSETS_DIR / "subtitles"
        self.OUTPUT_DIR = self.project_dir / "output"
        self.LOGS_DIR = self.project_dir / "logs"

        # Global visual reference image for consistent art style
        self.VISUAL_REFERENCE_PATH = self.project_dir / "visual-reference.png"

    def ensure_dirs(self) -> None:
        """Create asset/output directories if they do not exist."""
        for path in [
            self.IMAGES_DIR,
            self.VIDEOS_DIR,
            self.AUDIO_DIR,
            self.MUSIC_DIR,
            self.SUBTITLES_DIR,
            self.OUTPUT_DIR,
            self.LOGS_DIR,
        ]:
            path.mkdir(parents=True, exist_ok=True)

    @classmethod
    def validate(cls) -> None:
        """Validate required global configuration."""
        if not cls.ARK_API_KEY:
            raise ValueError("ARK_API_KEY is required for image generation")
        if cls.TTS_PROVIDER not in {"edge_tts", "volcano"}:
            raise ValueError(f"Unsupported TTS provider: {cls.TTS_PROVIDER}")
        if cls.TTS_PROVIDER == "volcano":
            has_api_key = bool(cls.VOLCANO_TTS_API_KEY)
            has_legacy_creds = bool(cls.VOLCANO_TTS_APP_ID) and bool(cls.VOLCANO_TTS_ACCESS_TOKEN)
            if not (has_api_key or has_legacy_creds):
                raise ValueError(
                    "Volcano TTS requires either VOLCANO_TTS_API_KEY (new console) "
                    "or both VOLCANO_TTS_APP_ID and VOLCANO_TTS_ACCESS_TOKEN (legacy console)"
                )
