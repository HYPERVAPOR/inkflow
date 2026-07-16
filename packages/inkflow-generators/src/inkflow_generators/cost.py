"""Cost tracking for API calls."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from inkflow_core.config import Config

logger = logging.getLogger(__name__)

# Seedream pricing in CNY per image.
# <= 2.36 megapixels: 0.30 CNY
# >  2.36 megapixels: 0.60 CNY
MEGAPIXEL_THRESHOLD = 2.36
PRICE_LOW_RES_CNY = 0.30
PRICE_HIGH_RES_CNY = 0.60

# Seedance token pricing in CNY per million tokens (online inference, silent/video generation).
# Source: model-prices / 火山方舟官方文档
SEEDANCE_TOKENS_PER_MILLION_CNY: dict[str, float] = {
    "doubao-seedance-1-5-pro-251215": 8.0,
    "doubao-seedance-1-0-pro-250528": 15.0,
    "doubao-seedance-1-0-pro-fast-251015": 4.2,
    "doubao-seedance-2-0-260128": 46.0,
    "doubao-seedance-2-0-fast-260128": 37.0,
    "doubao-seedance-2-0-mini-260615": 23.0,
}

# Fallback per-second estimates for Seedance silent video (CNY/s) when token usage is missing.
# Derived from official 5-second examples where available.
SEEDANCE_SILENT_CNY_PER_SECOND = {
    "480p": 0.40 / 5,
    "720p": 0.86 / 5,
    "1080p": 1.94 / 5,
}

# Approximate exchange rate for display purposes.
USD_TO_CNY_RATE = 7.2


@dataclass
class CostEntry:
    """A single cost entry."""

    timestamp: str
    operation: str
    model: str
    unit_price: float
    quantity: int
    cost: float
    currency: str = "CNY"
    usage: dict[str, Any] = field(default_factory=dict)
    note: str = ""


class CostTracker:
    """Track and persist API costs for a project."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.entries: list[CostEntry] = []

    @staticmethod
    def _image_unit_price(width: int, height: int) -> float:
        """Compute Seedream price per image based on resolution."""
        megapixels = (width * height) / 1_000_000
        if megapixels <= MEGAPIXEL_THRESHOLD:
            return PRICE_LOW_RES_CNY
        return PRICE_HIGH_RES_CNY

    def log_image_generation(
        self,
        model: str,
        quantity: int = 1,
        width: int = 1080,
        height: int = 1920,
        cost: float | None = None,
        usage: dict[str, Any] | None = None,
        note: str = "",
    ) -> CostEntry:
        """Log cost for image generation."""
        unit_price = self._image_unit_price(width, height)
        calculated_cost = unit_price * quantity

        # Try to extract actual cost from usage if provided
        if cost is None and usage:
            actual_cost = usage.get("cost") or usage.get("total_cost")
            if actual_cost is not None:
                try:
                    cost = float(actual_cost)
                except (ValueError, TypeError):
                    pass

        final_cost = cost if cost is not None else calculated_cost

        megapixels = (width * height) / 1_000_000
        entry = CostEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            operation="image_generation",
            model=model,
            unit_price=unit_price,
            quantity=quantity,
            cost=final_cost,
            currency="CNY",
            usage=usage or {},
            note=f"{note}, resolution={width}x{height} ({megapixels:.2f}MP)",
        )
        self.entries.append(entry)
        logger.info(
            "Cost: image_generation model=%s resolution=%dx%d quantity=%d cost=%.2f CNY",
            model, width, height, quantity, final_cost,
        )
        return entry

    def log_video_generation(
        self,
        model: str,
        ratio: str,
        resolution: str,
        duration: int,
        usage: dict[str, Any] | None = None,
        note: str = "",
    ) -> CostEntry:
        """Log cost for Seedance video generation."""
        usage = usage or {}

        # Prefer actual token usage if API returns it
        completion_tokens = usage.get("completion_tokens") or usage.get("total_tokens")
        if completion_tokens is not None:
            try:
                tokens = int(completion_tokens)
                unit_price = SEEDANCE_TOKENS_PER_MILLION_CNY.get(model, 8.0)
                cost = tokens / 1_000_000 * unit_price
                unit_price_for_entry = unit_price
                quantity = tokens
            except (ValueError, TypeError):
                completion_tokens = None
        else:
            completion_tokens = None

        if completion_tokens is None:
            # Fallback: estimate from resolution and duration
            unit_price_for_entry = SEEDANCE_SILENT_CNY_PER_SECOND.get(resolution, 0.172)
            cost = unit_price_for_entry * duration
            quantity = duration

        entry = CostEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            operation="video_generation",
            model=model,
            unit_price=round(unit_price_for_entry, 6),
            quantity=quantity,
            cost=round(cost, 4),
            currency="CNY",
            usage=usage,
            note=f"{note}, ratio={ratio}, resolution={resolution}, duration={duration}s",
        )
        self.entries.append(entry)
        logger.info(
            "Cost: video_generation model=%s ratio=%s resolution=%s duration=%ds cost=%.4f CNY",
            model, ratio, resolution, duration, cost,
        )
        return entry

    def log_tts(
        self,
        model: str,
        text: str,
        usage: dict[str, Any] | None = None,
        note: str = "Edge TTS is free",
    ) -> CostEntry:
        """Log cost for TTS. Edge TTS is free."""
        entry = CostEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            operation="tts",
            model=model,
            unit_price=0.0,
            quantity=len(text),
            cost=0.0,
            currency="CNY",
            usage=usage or {},
            note=note,
        )
        self.entries.append(entry)
        logger.info("Cost: tts model=%s chars=%d cost=0.00 CNY (free)", model, len(text))
        return entry

    @property
    def total_cost(self) -> float:
        """Return total cost across all entries."""
        return sum(entry.cost for entry in self.entries)

    def summary(self) -> dict[str, Any]:
        """Return a cost summary."""
        by_operation: dict[str, float] = {}
        for entry in self.entries:
            by_operation[entry.operation] = by_operation.get(entry.operation, 0.0) + entry.cost

        total_cny = self.total_cost
        total_usd = total_cny / USD_TO_CNY_RATE

        return {
            "total_cost_cny": round(total_cny, 4),
            "total_cost_usd": round(total_usd, 6),
            "total_cost_cny_approx": round(total_cny, 4),
            "by_operation": by_operation,
            "entry_count": len(self.entries),
        }

    def save(self) -> Path:
        """Save cost entries and summary to project logs.

        Merges with existing cost.json instead of overwriting, so that
        costs from separate pipeline steps or re-runs are preserved.
        """
        output_path = Path(self.config.LOGS_DIR) / "cost.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        existing_entries: list[dict[str, Any]] = []
        if output_path.exists():
            try:
                with open(output_path, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
                existing_entries = existing_data.get("entries", [])
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Could not load existing cost.json: %s", e)

        new_entries = [asdict(entry) for entry in self.entries]

        # Deduplicate by a stable key that ignores timestamp, so that
        # re-running the same operation for the same shot replaces the
        # previous entry rather than creating a duplicate.
        def _entry_key(entry: dict[str, Any]) -> tuple[Any, ...]:
            return (
                entry.get("operation"),
                entry.get("model"),
                entry.get("quantity"),
                entry.get("note"),
            )

        merged: dict[tuple[Any, ...], dict[str, Any]] = {}
        for entry in existing_entries + new_entries:
            merged[_entry_key(entry)] = entry

        merged_entries = list(merged.values())
        merged_entries.sort(key=lambda e: e.get("timestamp", ""))

        # Recompute summary from merged entries
        by_operation: dict[str, float] = {}
        total_cny = 0.0
        for entry in merged_entries:
            cost = float(entry.get("cost") or 0.0)
            op = entry.get("operation", "unknown")
            by_operation[op] = by_operation.get(op, 0.0) + cost
            total_cny += cost

        data = {
            "summary": {
                "total_cost_cny": round(total_cny, 4),
                "total_cost_usd": round(total_cny / USD_TO_CNY_RATE, 6),
                "total_cost_cny_approx": round(total_cny, 4),
                "by_operation": by_operation,
                "entry_count": len(merged_entries),
            },
            "entries": merged_entries,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info("Cost summary saved to %s", output_path)
        return output_path
