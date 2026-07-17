"""Video assembly using FFmpeg."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from inkflow_core.config import Config
from inkflow_core.models import Script, Shot

logger = logging.getLogger(__name__)


DEFAULT_SUBTITLE_STYLE: dict[str, Any] = {
    "FontName": "Noto Sans CJK SC",
    "FontSize": 32,
    "PrimaryColour": "&HFFFFFF&",
    "OutlineColour": "&H000000&",
    "Outline": 2,
    "Alignment": 2,
    "MarginV": 40,
}


def _format_motion(motion: dict[str, Any]) -> tuple[str, str]:
    """Return (start, end) motion strings with defaults."""
    return (
        motion.get("start", "zoom_1.0_pan_0_0"),
        motion.get("end", "zoom_1.0_pan_0_0"),
    )


class VideoAssembler:
    """Assemble images/videos, audio, subtitles and BGM into final video."""

    def __init__(self, config: Config) -> None:
        self.config = config

    def _run_ffmpeg(self, args: list[str]) -> None:
        """Run an FFmpeg command."""
        cmd = ["ffmpeg", "-y"] + args
        logger.debug("Running: %s", " ".join(cmd))
        subprocess.run(cmd, check=True, capture_output=True, text=True)

    def _run_ffprobe(self, path: Path) -> float:
        """Return video duration in seconds."""
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        return float(result.stdout.strip())

    def _parse_resolution(self, resolution: str) -> tuple[int, int]:
        """Parse WIDTHxHEIGHT from metadata resolution."""
        parts = resolution.split("x")
        return int(parts[0]), int(parts[1])

    def _build_ken_burns_filter(
        self, motion: dict[str, Any], width: int, height: int, duration: float, fps: int
    ) -> str:
        """Build a simple zoompan filter for Ken Burns effect."""
        frames = int(duration * fps)
        _start, end = _format_motion(motion)

        end_zoom = 1.15
        try:
            parts = end.split("_")
            for i, part in enumerate(parts):
                if part == "zoom":
                    end_zoom = float(parts[i + 1])
        except (IndexError, ValueError):
            pass

        return (
            f"scale={width * 2}:{height * 2},"
            f"zoompan=z='min(pzoom+{(end_zoom - 1.0) / max(frames, 1):.6f},{end_zoom})':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={frames}:s={width}x{height}:fps={fps}"
        )

    def _render_legacy_subtitle(
        self,
        index: int,
        text: str,
        image_path: Path,
        audio_path: Path,
        output_path: Path,
        resolution: str,
        fps: int,
        motion: dict[str, Any] | None = None,
    ) -> None:
        """Render a single subtitle clip from a static image (legacy workflow)."""
        durations = getattr(self, "_subtitle_durations", {})
        duration = durations.get(index, 3.0)
        width, height = self._parse_resolution(resolution)

        motion = motion or {"type": "ken_burns", "end": "zoom_1.15_pan_0_0"}
        vf = self._build_ken_burns_filter(motion, width, height, duration, fps)

        args = [
            "-loop", "1",
            "-i", str(image_path),
            "-i", str(audio_path),
            "-vf", vf,
            "-t", str(duration),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            str(output_path),
        ]
        self._run_ffmpeg(args)

    def _concat_files(
        self, file_paths: list[Path], output_path: Path, file_type: str = "video"
    ) -> None:
        """Concatenate media files using FFmpeg concat demuxer."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            for path in file_paths:
                f.write(f"file '{path.resolve()}'\n")
            concat_list = f.name

        try:
            args = [
                "-f", "concat",
                "-safe", "0",
                "-i", concat_list,
                "-c", "copy",
                str(output_path),
            ]
            self._run_ffmpeg(args)
        finally:
            Path(concat_list).unlink(missing_ok=True)

    def _prepare_shot_video(self, shot: Shot, shot_duration: float, output_path: Path) -> None:
        """Trim or loop a shot video to exactly shot_duration seconds."""
        videos_dir = Path(self.config.VIDEOS_DIR)
        video_path = videos_dir / f"shot_{shot.shot_id}.mp4"
        if not video_path.exists():
            raise FileNotFoundError(f"Shot video not found: {video_path}")

        source_duration = self._run_ffprobe(video_path)
        logger.info(
            "Preparing shot %s video: source=%.2fs, target=%.2fs",
            shot.shot_id,
            source_duration,
            shot_duration,
        )

        if source_duration >= shot_duration:
            args = [
                "-i", str(video_path),
                "-t", str(shot_duration),
                "-c", "copy",
                "-an",
                str(output_path),
            ]
        else:
            filter_complex = (
                "[0:v]loop=loop=-1:size=1:start=0[looped];"
                f"[looped]trim=duration={shot_duration}[trimmed]"
            )
            args = [
                "-i", str(video_path),
                "-filter_complex", filter_complex,
                "-map", "[trimmed]",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-an",
                str(output_path),
            ]
        self._run_ffmpeg(args)

    def _compute_shot_durations(self, script: Script) -> dict[int, float]:
        """Compute total duration for each shot from subtitle durations."""
        durations = getattr(script, "_subtitle_durations", {})
        result: dict[int, float] = {}
        for shot in script.shots:
            result[shot.shot_id] = script.shot_duration(shot, durations)
        return result

    def _build_subtitle_style(self, style: dict[str, Any] | None) -> str:
        """Build FFmpeg subtitles force_style string from metadata style."""
        final_style = {**DEFAULT_SUBTITLE_STYLE, **(style or {})}
        return ",".join(f"{k}={v}" for k, v in final_style.items())

    def _add_bgm_and_subtitles(
        self,
        video_path: Path,
        subtitle_path: Path | None,
        output_path: Path,
        bgm_path: Path | None = None,
        subtitle_style: dict[str, Any] | None = None,
    ) -> None:
        """Add background music and/or burn subtitles into the final video."""
        has_bgm = bgm_path and bgm_path.exists()
        has_subs = subtitle_path is not None

        if has_bgm and has_subs:
            style_str = self._build_subtitle_style(subtitle_style)
            sub_path_escaped = str(subtitle_path).replace("\\", "/").replace(":", "\\:")
            filter_complex = (
                "[1:a]volume=0.25[bg];"
                "[0:a][bg]amix=inputs=2:duration=first[final_audio];"
                f"[0:v]subtitles={sub_path_escaped}:force_style='{style_str}'[final_video]"
            )
            args = [
                "-i", str(video_path),
                "-i", str(bgm_path),
                "-filter_complex", filter_complex,
                "-map", "[final_video]",
                "-map", "[final_audio]",
                "-c:v", "libx264",
                "-c:a", "aac",
                "-b:a", "192k",
                str(output_path),
            ]
        elif has_bgm:
            args = [
                "-i", str(video_path),
                "-i", str(bgm_path),
                "-filter_complex", "[1:a]volume=0.25[bg];[0:a][bg]amix=inputs=2:duration=first",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                str(output_path),
            ]
        elif has_subs:
            style_str = self._build_subtitle_style(subtitle_style)
            sub_path_escaped = str(subtitle_path).replace("\\", "/").replace(":", "\\:")
            vf = f"subtitles={sub_path_escaped}:force_style='{style_str}'"
            args = [
                "-i", str(video_path),
                "-vf", vf,
                "-c:a", "copy",
                "-c:v", "libx264",
                str(output_path),
            ]
        else:
            shutil.copy2(str(video_path), str(output_path))
            return

        self._run_ffmpeg(args)

    def _assemble_legacy(
        self,
        script: Script,
        subtitle_path: Path,
        bgm_path: Path | None,
        output_path: Path,
    ) -> Path:
        """Legacy image-based assembly (one image per subtitle)."""
        images_dir = Path(self.config.IMAGES_DIR)
        audio_dir = Path(self.config.AUDIO_DIR)

        clip_files: list[Path] = []
        with tempfile.TemporaryDirectory() as tmpdir:
            prev_image_path: Path | None = None
            for index, text in enumerate(script.subtitles):
                image_path = images_dir / f"scene_{index}.png"
                audio_path = audio_dir / f"subtitle_{index}.mp3"
                clip_output = Path(tmpdir) / f"subtitle_{index}.mp4"

                if not image_path.exists():
                    if prev_image_path:
                        image_path = prev_image_path
                        logger.info("Subtitle %s uses held image from %s", index, image_path.name)
                    else:
                        raise FileNotFoundError(f"Image not found: {image_path}")

                if not audio_path.exists():
                    raise FileNotFoundError(f"Audio not found: {audio_path}")

                self._render_legacy_subtitle(
                    index,
                    text,
                    image_path,
                    audio_path,
                    clip_output,
                    script.metadata.resolution,
                    script.metadata.fps,
                )
                clip_files.append(clip_output)
                prev_image_path = image_path

            assembled_path = Path(tmpdir) / "assembled.mp4"
            self._concat_files(clip_files, assembled_path)
            subtitle_for_burn = subtitle_path if script.metadata.burn_subtitles else None
            self._add_bgm_and_subtitles(
                assembled_path, subtitle_for_burn, output_path, bgm_path,
                script.metadata.subtitle_style,
            )

        return output_path

    def _assemble_shots(
        self,
        script: Script,
        subtitle_path: Path,
        bgm_path: Path | None,
        output_path: Path,
    ) -> Path:
        """Shot-based video assembly."""
        audio_dir = Path(self.config.AUDIO_DIR)
        shot_durations = self._compute_shot_durations(script)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # 1. Prepare each shot video to exact duration
            prepared_shot_files: list[Path] = []
            for shot in sorted(script.shots, key=lambda s: s.shot_id):
                prepared = tmpdir_path / f"shot_{shot.shot_id}_prepared.mp4"
                self._prepare_shot_video(shot, shot_durations[shot.shot_id], prepared)
                prepared_shot_files.append(prepared)

            # 2. Concatenate shot videos
            video_only_path = tmpdir_path / "video_only.mp4"
            self._concat_files(prepared_shot_files, video_only_path)

            # 3. Concatenate subtitle audios
            audio_files: list[Path] = []
            for index, _ in enumerate(script.subtitles):
                audio_path = audio_dir / f"subtitle_{index}.mp3"
                if not audio_path.exists():
                    raise FileNotFoundError(f"Audio not found: {audio_path}")
                audio_files.append(audio_path)

            audio_only_path = tmpdir_path / "audio_only.mp3"
            self._concat_files(audio_files, audio_only_path, file_type="audio")

            # 4. Merge video and audio
            merged_path = tmpdir_path / "merged.mp4"
            merge_args = [
                "-i", str(video_only_path),
                "-i", str(audio_only_path),
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
                str(merged_path),
            ]
            self._run_ffmpeg(merge_args)

            # 5. Add subtitles and/or BGM
            subtitle_for_burn = subtitle_path if script.metadata.burn_subtitles else None
            self._add_bgm_and_subtitles(
                merged_path, subtitle_for_burn, output_path, bgm_path,
                script.metadata.subtitle_style,
            )

        return output_path

    def _assemble_from_clips(
        self,
        clip_paths: list[Path],
        audio_path: Path,
        subtitle_path: Path,
        bgm_path: Path | None,
        output_path: Path,
        burn_subtitles: bool,
        subtitle_style: dict[str, Any] | None,
    ) -> Path:
        """Concatenate pre-rendered clips and merge with audio/subtitles."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            video_only_path = tmpdir_path / "video_only.mp4"
            self._concat_files(clip_paths, video_only_path)

            merged_path = tmpdir_path / "merged.mp4"
            merge_args = [
                "-i", str(video_only_path),
                "-i", str(audio_path),
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
                str(merged_path),
            ]
            self._run_ffmpeg(merge_args)

            subtitle_for_burn = subtitle_path if burn_subtitles else None
            self._add_bgm_and_subtitles(
                merged_path, subtitle_for_burn, output_path, bgm_path, subtitle_style
            )

        return output_path

    def _concatenate_subtitle_audios(self, script: Script) -> Path:
        """Concatenate all subtitle audio files into one MP3."""
        audio_files: list[Path] = []
        for index, _ in enumerate(script.subtitles):
            audio_path = Path(self.config.AUDIO_DIR) / f"subtitle_{index}.mp3"
            if not audio_path.exists():
                raise FileNotFoundError(f"Audio not found: {audio_path}")
            audio_files.append(audio_path)

        output_path = Path(self.config.AUDIO_DIR) / "concatenated.mp3"
        self._concat_files(audio_files, output_path, file_type="audio")
        return output_path

    def assemble(
        self,
        script: Script,
        subtitle_path: Path,
        bgm_path: Path | None = None,
        output_path: Path | None = None,
        scene_clips: list[Path] | None = None,
    ) -> Path:
        """Assemble the final video."""
        output_path = output_path or Path(self.config.OUTPUT_DIR) / "final.mp4"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if scene_clips:
            logger.info("Assembling from pre-rendered clips")
            audio_path = self._concatenate_subtitle_audios(script)
            self._assemble_from_clips(
                scene_clips,
                audio_path,
                subtitle_path,
                bgm_path,
                output_path,
                script.metadata.burn_subtitles,
                script.metadata.subtitle_style,
            )
        elif script.uses_shots:
            logger.info("Assembling shot-based video")
            self._assemble_shots(script, subtitle_path, bgm_path, output_path)
        else:
            logger.info("Assembling legacy image-based video")
            self._assemble_legacy(script, subtitle_path, bgm_path, output_path)

        logger.info("Final video saved to %s", output_path)
        return output_path
