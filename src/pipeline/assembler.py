"""Video assembly using FFmpeg."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from src.core.config import Config
from src.core.models import Script, Shot
from src.media import ffmpeg

logger = logging.getLogger(__name__)


class VideoAssembler:
    """Assemble images/videos, audio, subtitles and BGM into final video."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config

    def _compute_shot_durations(self, script: Script) -> dict[int, float]:
        """Compute total duration for each shot from subtitle durations."""
        return {shot.shot_id: script.shot_duration(shot) for shot in script.shots}

    def _prepare_shot_video(self, shot: Shot, shot_duration: float, output_path: Path) -> Path:
        """Trim or loop a shot video to exactly shot_duration seconds at 12fps."""
        if self.config is None:
            raise ValueError("Config is required")
        videos_dir = Path(self.config.VIDEOS_DIR)
        video_path = videos_dir / f"shot_{shot.shot_id}.mp4"
        if not video_path.exists():
            raise FileNotFoundError(f"Shot video not found: {video_path}")

        source_duration = ffmpeg.run_ffprobe(video_path)
        target_fps = self.config.SEEDANCE_FPS
        logger.info(
            "Preparing shot %s video: source=%.2fs, target=%.2fs, fps=%s",
            shot.shot_id,
            source_duration,
            shot_duration,
            target_fps,
        )

        if source_duration >= shot_duration:
            ffmpeg.trim_video(video_path, output_path, shot_duration, fps=target_fps)
        else:
            ffmpeg.loop_video(video_path, output_path, shot_duration, fps=target_fps)
        return output_path

    def _assemble_shots(
        self,
        script: Script,
        subtitle_path: Path,
        bgm_path: Path | None,
        output_path: Path,
    ) -> Path:
        """Shot-based video assembly."""
        if self.config is None:
            raise ValueError("Config is required")
        audio_dir = Path(self.config.AUDIO_DIR)
        shot_durations = self._compute_shot_durations(script)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Prepare each shot video to exact duration
            prepared_shot_files: list[Path] = []
            for shot in sorted(script.shots, key=lambda s: s.shot_id):
                dest = tmpdir_path / f"shot_{shot.shot_id}_prepared.mp4"
                self._prepare_shot_video(shot, shot_durations[shot.shot_id], dest)
                prepared_shot_files.append(dest)

            # Concatenate shot videos
            video_only_path = tmpdir_path / "video_only.mp4"
            ffmpeg.concat_media(prepared_shot_files, video_only_path)

            # Concatenate subtitle audios
            audio_files: list[Path] = []
            for subtitle in script.subtitles:
                audio_path = audio_dir / f"subtitle_{subtitle.subtitle_id}.mp3"
                if not audio_path.exists():
                    raise FileNotFoundError(f"Audio not found: {audio_path}")
                audio_files.append(audio_path)

            audio_only_path = tmpdir_path / "audio_only.mp3"
            ffmpeg.concat_media(audio_files, audio_only_path, file_type="audio")

            # Merge video and audio
            merged_path = tmpdir_path / "merged.mp4"
            ffmpeg.merge_video_audio(video_only_path, audio_only_path, merged_path)

            # Add subtitles and/or BGM
            self._add_post_effects(merged_path, output_path, subtitle_path, bgm_path, script)

        return output_path

    def _assemble_legacy(
        self,
        script: Script,
        subtitle_path: Path,
        bgm_path: Path | None,
        output_path: Path,
    ) -> Path:
        """Legacy image-based assembly."""
        if self.config is None:
            raise ValueError("Config is required")
        images_dir = Path(self.config.IMAGES_DIR)
        audio_dir = Path(self.config.AUDIO_DIR)

        with tempfile.TemporaryDirectory() as tmpdir:
            scene_files: list[Path] = []
            for subtitle in script.subtitles:
                image_path = images_dir / f"subtitle_{subtitle.subtitle_id}.png"
                audio_path = audio_dir / f"subtitle_{subtitle.subtitle_id}.mp3"
                scene_output = Path(tmpdir) / f"subtitle_{subtitle.subtitle_id}.mp4"

                if not image_path.exists():
                    raise FileNotFoundError(f"Image not found: {image_path}")
                if not audio_path.exists():
                    raise FileNotFoundError(f"Audio not found: {audio_path}")

                duration = subtitle.duration or 3.0
                ffmpeg.render_image_clip(
                    image_path,
                    audio_path,
                    scene_output,
                    duration=duration,
                    width=script.metadata.width,
                    height=script.metadata.height,
                    fps=self.config.SEEDANCE_FPS,
                )
                scene_files.append(scene_output)

            assembled_path = Path(tmpdir) / "assembled.mp4"
            ffmpeg.concat_media(scene_files, assembled_path)
            self._add_post_effects(assembled_path, output_path, subtitle_path, bgm_path, script)

        return output_path

    def _add_post_effects(
        self,
        video_path: Path,
        output_path: Path,
        subtitle_path: Path,
        bgm_path: Path | None,
        script: Script,
    ) -> None:
        """Add subtitles and/or BGM to video."""
        has_bgm = bgm_path is not None and bgm_path.exists()
        has_subs = script.metadata.burn_subtitles

        if has_bgm and has_subs:
            ffmpeg.add_bgm_and_subtitles(
                video_path,
                output_path,
                bgm_path,  # type: ignore[arg-type]
                subtitle_path,
                script.metadata.subtitle_style,
            )
        elif has_bgm:
            ffmpeg.add_bgm(video_path, output_path, bgm_path)  # type: ignore[arg-type]
        elif has_subs:
            ffmpeg.burn_subtitles(
                video_path,
                output_path,
                subtitle_path,
                script.metadata.subtitle_style,
            )
        else:
            ffmpeg.copy_file(video_path, output_path)

    def assemble(
        self,
        script: Script,
        subtitle_path: Path,
        bgm_path: Path | None = None,
        output_path: Path | None = None,
    ) -> Path:
        """Assemble the final video."""
        if self.config is None:
            raise ValueError("Config is required")
        output_path = output_path or Path(self.config.OUTPUT_DIR) / "final.mp4"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if script.shots:
            logger.info("Assembling shot-based video")
            self._assemble_shots(script, subtitle_path, bgm_path, output_path)
        else:
            logger.info("Assembling legacy image-based video")
            self._assemble_legacy(script, subtitle_path, bgm_path, output_path)

        logger.info("Final video saved to %s", output_path)
        return output_path
