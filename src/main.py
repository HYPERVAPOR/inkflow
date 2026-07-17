"""CLI entry point for InkFlow."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from src.core.config import Config
from src.core.script import load_script
from src.pipeline.pipeline import Pipeline


def setup_logging(logs_dir: Path) -> None:
    """Configure logging."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(logs_dir / "pipeline.log", encoding="utf-8"),
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="InkFlow - AI video generation pipeline")
    parser.add_argument("project", help="Path to project directory (e.g., projects/example-proj)")
    parser.add_argument(
        "--script",
        help="Path to script.json (default: <project>/scripts/script.json)",
        default=None,
    )
    parser.add_argument(
        "--bgm",
        help="Path to background music file (default: <project>/assets/music/bgm.mp3)",
        default=None,
    )
    parser.add_argument(
        "--step",
        help="Run a single step: audio, images, covers, video, subtitles, assemble",
        default=None,
    )

    args = parser.parse_args()

    project_dir = Path(args.project)
    script_path = Path(args.script) if args.script else project_dir / "scripts" / "script.json"
    bgm_path = Path(args.bgm) if args.bgm else project_dir / "assets" / "music" / "bgm.mp3"
    bgm = bgm_path if bgm_path.exists() else None

    config = Config(project_dir)
    config.ensure_dirs()
    setup_logging(config.LOGS_DIR)

    script = load_script(script_path)
    pipeline = Pipeline(config)
    if args.step:
        pipeline.run_step(script, args.step)
    else:
        final_path = pipeline.run(script, bgm)
        print(f"Final video: {final_path}")


if __name__ == "__main__":
    main()
