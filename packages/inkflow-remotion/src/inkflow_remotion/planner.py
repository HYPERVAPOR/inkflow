"""Translate declarative shot descriptions into Remotion composition elements."""

from __future__ import annotations

import logging
import re
from typing import Any

from inkflow_core.models import Script, Shot

from .assets import FetchedAsset

logger = logging.getLogger(__name__)


def _parse_resolution(resolution: str) -> tuple[int, int]:
    """Parse WIDTHxHEIGHT from metadata resolution."""
    parts = resolution.split("x")
    return int(parts[0]), int(parts[1])


class VisualPlanner:
    """Build Remotion composition elements from a declarative shot."""

    def __init__(self, script: Script, width: int, height: int, fps: int) -> None:
        self.script = script
        self.width = width
        self.height = height
        self.fps = fps

    def _text_elements(self, shot: Shot) -> list[dict[str, Any]]:
        """Create subtitle text elements for a shot."""
        subtitles = self.script.subtitles_for_shot(shot)
        if not subtitles:
            return []

        # Stack subtitles near the bottom, one per paragraph.
        line_height = 80
        total_height = len(subtitles) * line_height
        start_y = self.height - 200 - total_height

        elements: list[dict[str, Any]] = []
        for index, text in enumerate(subtitles):
            elements.append({
                "id": f"text_{shot.shot_id}_{index}",
                "type": "text",
                "props": {
                    "text": text,
                    "fontSize": 48,
                    "color": "#ffffff",
                    "textAlign": "center",
                    "fontFamily": "Noto Sans SC",
                },
                "layout": {
                    "x": 0,
                    "y": start_y + index * line_height,
                    "width": "100%",
                    "height": line_height,
                },
                "animation": {
                    "type": "fade_in",
                    "duration": 0.4,
                    "delay": index * 0.3,
                },
            })
        return elements

    def _chart_elements(self, description: str) -> list[dict[str, Any]]:
        """Create chart elements based on keywords in the description."""
        elements: list[dict[str, Any]] = []
        if re.search(r"柱状图|bar chart|条形图", description):
            elements.append({
                "id": "chart_bar",
                "type": "chart_bar",
                "props": {
                    "data": [12, 19, 8, 15, 22],
                    "options": {"labels": ["A", "B", "C", "D", "E"]},
                },
                "layout": {
                    "x": self.width * 0.1,
                    "y": self.height * 0.25,
                    "width": self.width * 0.8,
                    "height": self.height * 0.4,
                },
                "animation": {"type": "grow", "duration": 1.0},
            })
        if re.search(r"折线图|line chart|曲线图|趋势图", description):
            elements.append({
                "id": "chart_line",
                "type": "chart_line",
                "props": {
                    "data": [10, 25, 18, 30, 45],
                    "options": {"labels": ["1", "2", "3", "4", "5"]},
                },
                "layout": {
                    "x": self.width * 0.1,
                    "y": self.height * 0.25,
                    "width": self.width * 0.8,
                    "height": self.height * 0.4,
                },
                "animation": {"type": "draw", "duration": 1.2},
            })
        if re.search(r"饼图|pie chart|扇形图", description):
            elements.append({
                "id": "chart_pie",
                "type": "chart_pie",
                "props": {
                    "data": [35, 25, 20, 20],
                    "options": {"labels": ["A", "B", "C", "D"]},
                },
                "layout": {
                    "x": self.width * 0.2,
                    "y": self.height * 0.25,
                    "width": self.width * 0.6,
                    "height": self.height * 0.4,
                },
                "animation": {"type": "grow", "duration": 1.0},
            })
        return elements

    def _map_elements(self, description: str) -> list[dict[str, Any]]:
        """Create a map element if the description asks for one."""
        if not re.search(r"地图|map|地理位置", description):
            return []
        return [{
            "id": "map",
            "type": "map",
            "props": {"src": "world-map-placeholder.png"},
            "layout": {
                "x": 0,
                "y": self.height * 0.1,
                "width": "100%",
                "height": self.height * 0.6,
            },
            "animation": {"type": "fade_in", "duration": 0.8},
        }]

    def _image_elements(self, assets: list[FetchedAsset]) -> list[dict[str, Any]]:
        """Create image elements from fetched Seedream/local/remote images."""
        elements: list[dict[str, Any]] = []
        for idx, fetched in enumerate(assets):
            if fetched.asset.type not in {"seedream_image", "image_url", "local_image"}:
                continue
            # First image fills the frame; later images are centered cards.
            if idx == 0:
                layout = {
                    "x": 0,
                    "y": 0,
                    "width": "100%",
                    "height": "100%",
                }
            else:
                layout = {
                    "x": self.width * 0.15,
                    "y": self.height * 0.15,
                    "width": self.width * 0.7,
                    "height": self.height * 0.5,
                }
            elements.append({
                "id": f"image_{fetched.asset.id}",
                "type": "seedream_image",
                "props": {"src": fetched.filename},
                "layout": layout,
                "animation": {"type": "fade_in", "duration": 0.6, "delay": idx * 0.2},
            })
        return elements

    def _video_elements(self, assets: list[FetchedAsset]) -> list[dict[str, Any]]:
        """Create video elements from fetched video assets."""
        elements: list[dict[str, Any]] = []
        for fetched in assets:
            if fetched.asset.type not in {"video_url", "local_video", "seedance_video"}:
                continue
            elements.append({
                "id": f"video_{fetched.asset.id}",
                "type": "video",
                "props": {"src": fetched.filename},
                "layout": {
                    "x": 0,
                    "y": 0,
                    "width": "100%",
                    "height": "100%",
                },
                "animation": {"type": "fade_in", "duration": 0.5},
            })
        return elements

    def plan(self, shot: Shot, fetched_assets: list[FetchedAsset]) -> list[dict[str, Any]]:
        """Return composition elements for a shot."""
        elements: list[dict[str, Any]] = []

        # Background image/video first, then charts/maps, then text on top.
        elements.extend(self._video_elements(fetched_assets))
        elements.extend(self._image_elements(fetched_assets))
        elements.extend(self._chart_elements(shot.visual.description))
        elements.extend(self._map_elements(shot.visual.description))
        elements.extend(self._text_elements(shot))

        return elements
