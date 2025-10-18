"""Session statistics tracking for study highlights."""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Dict, Iterable

from .highlight import HighlightRecord


@dataclass
class HighlightStatistics:
    """Aggregated statistics per highlight tag."""

    tag: str
    total_hover_time: float = 0.0
    highlight_count: int = 0

    def register(self, record: HighlightRecord) -> None:
        self.total_hover_time += record.total_hover_time
        self.highlight_count += 1

    @property
    def formatted_duration(self) -> str:
        seconds = int(self.total_hover_time)
        return str(_dt.timedelta(seconds=seconds))


def summarize(records: Iterable[HighlightRecord]) -> Dict[str, HighlightStatistics]:
    result: Dict[str, HighlightStatistics] = {}
    for record in records:
        stats = result.setdefault(record.tag, HighlightStatistics(tag=record.tag))
        stats.register(record)
    return result


__all__ = ["HighlightStatistics", "summarize"]
