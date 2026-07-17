"""FFmpeg / FFprobe utilities."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def run_ffmpeg(args: list[str]) -> None:
    """Run an FFmpeg command."""
    cmd = ["ffmpeg", "-y"] + args
    logger.debug("Running: %s", " ".join(cmd))
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def run_ffprobe(path: Path) -> float:
    """Return media duration in seconds."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return float(result.stdout.strip())


def concat_media(file_paths: list[Path], output_path: Path, file_type: str = "video") -> None:
    """Concatenate media files using FFmpeg concat demuxer."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
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
        run_ffmpeg(args)
    finally:
        Path(concat_list).unlink(missing_ok=True)


def trim_video(
    input_path: Path, output_path: Path, duration: float, fps: int | None = None
) -> None:
    """Trim video to exact duration without audio, optionally re-encoding to fps."""
    args = [
        "-i", str(input_path),
        "-t", str(duration),
        "-an",
    ]
    if fps is not None:
        args.extend(["-r", str(fps), "-c:v", "libx264", "-pix_fmt", "yuv420p"])
    else:
        args.append("-c")
        args.append("copy")
    args.append(str(output_path))
    run_ffmpeg(args)


def loop_video(
    input_path: Path, output_path: Path, duration: float, fps: int | None = None
) -> None:
    """Loop video to reach target duration, optionally re-encoding to fps."""
    fps_filter = f"fps={fps}," if fps is not None else ""
    filter_complex = (
        f"[0:v]{fps_filter}loop=loop=-1:size=1:start=0[looped];"
        f"[looped]trim=duration={duration}[trimmed]"
    )
    args = [
        "-i", str(input_path),
        "-filter_complex", filter_complex,
        "-map", "[trimmed]",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-an",
        str(output_path),
    ]
    run_ffmpeg(args)


def merge_video_audio(video_path: Path, audio_path: Path, output_path: Path) -> None:
    """Merge video and audio streams."""
    args = [
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(output_path),
    ]
    run_ffmpeg(args)


def burn_subtitles(
    video_path: Path,
    output_path: Path,
    subtitle_path: Path,
    style: dict[str, Any] | None = None,
) -> None:
    """Burn subtitles into video using ASS style."""
    style_str = _build_subtitle_style(style)
    sub_path_escaped = str(subtitle_path).replace("\\", "/").replace(":", "\\:")
    vf = f"subtitles={sub_path_escaped}:force_style='{style_str}'"
    args = [
        "-i", str(video_path),
        "-vf", vf,
        "-c:a", "copy",
        "-c:v", "libx264",
        str(output_path),
    ]
    run_ffmpeg(args)


def add_bgm(video_path: Path, output_path: Path, bgm_path: Path) -> None:
    """Mix background music into video audio."""
    filter_complex = "[1:a]volume=0.25[bg];[0:a][bg]amix=inputs=2:duration=first"
    args = [
        "-i", str(video_path),
        "-i", str(bgm_path),
        "-filter_complex", filter_complex,
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        str(output_path),
    ]
    run_ffmpeg(args)


def add_bgm_and_subtitles(
    video_path: Path,
    output_path: Path,
    bgm_path: Path,
    subtitle_path: Path,
    style: dict[str, Any] | None = None,
) -> None:
    """Add background music and burn subtitles in one pass."""
    style_str = _build_subtitle_style(style)
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
    run_ffmpeg(args)


def render_image_clip(
    image_path: Path,
    audio_path: Path,
    output_path: Path,
    duration: float,
    width: int,
    height: int,
    fps: int,
) -> None:
    """Render a static-image scene clip with Ken Burns zoom."""
    frames = int(duration * fps)
    end_zoom = 1.15
    zoom_step = (end_zoom - 1.0) / max(frames, 1)
    vf = (
        f"scale={width * 2}:{height * 2},"
        f"zoompan=z='min(pzoom+{zoom_step:.6f},{end_zoom})':"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={frames}:s={width}x{height}:fps={fps}"
    )
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
    run_ffmpeg(args)


def create_placeholder_image(output_path: Path, width: int, height: int) -> Path:
    """Create a simple black placeholder image."""
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i", f"color=c=black:s={width}x{height}",
        "-frames:v", "1",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path


DEFAULT_SUBTITLE_STYLE: dict[str, Any] = {
    "FontName": "Noto Sans CJK SC",
    "FontSize": 32,
    "PrimaryColour": "&HFFFFFF&",
    "OutlineColour": "&H000000&",
    "Outline": 2,
    "Alignment": 2,
    "MarginV": 40,
}


def _build_subtitle_style(style: dict[str, Any] | None) -> str:
    """Build FFmpeg subtitles force_style string from metadata style."""
    final_style = {**DEFAULT_SUBTITLE_STYLE, **(style or {})}
    return ",".join(f"{k}={v}" for k, v in final_style.items())


def copy_file(src: Path, dst: Path) -> None:
    """Copy a file."""
    shutil.copy2(str(src), str(dst))
