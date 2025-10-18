"""Storage utilities for highlight persistence."""
from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from .highlight import HighlightRecord


DEFAULT_STORAGE_DIR = Path.home() / ".study_pdf"
DEFAULT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)


class HighlightStorage:
    """Handles persistence of highlight information on disk."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or DEFAULT_STORAGE_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _document_key(self, pdf_path: Path) -> str:
        sanitized = pdf_path.resolve().as_posix().replace("/", "_")
        return sanitized.replace(":", "_")

    def _payload_path(self, pdf_path: Path) -> Path:
        return self.base_dir / f"{self._document_key(pdf_path)}.json"

    # ------------------------------------------------------------------
    def save(self, pdf_path: Path, records: Iterable[HighlightRecord]) -> None:
        data = [rec.to_dict() for rec in records]
        payload = {"highlights": data}
        path = self._payload_path(pdf_path)
        tmp_path = path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        tmp_path.replace(path)

    def load(self, pdf_path: Path) -> List[HighlightRecord]:
        path = self._payload_path(pdf_path)
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        records: List[HighlightRecord] = []
        for item in payload.get("highlights", []):
            try:
                records.append(HighlightRecord.from_dict(item))
            except Exception:
                continue
        return records

    # ------------------------------------------------------------------
    def export_with_highlights(self, pdf_path: Path, records: Iterable[HighlightRecord], output: Path) -> None:
        import fitz

        document = fitz.open(pdf_path)
        for record in records:
            page = document.load_page(record.page_number)
            rect = record.relative_rect
            page_rect = page.rect
            box = fitz.Rect(
                page_rect.x0 + rect[0] * page_rect.width,
                page_rect.y0 + rect[1] * page_rect.height,
                page_rect.x0 + (rect[0] + rect[2]) * page_rect.width,
                page_rect.y0 + (rect[1] + rect[3]) * page_rect.height,
            )
            shape = page.new_shape()
            color = record.color
            highlight_color = (
                max(0.0, min(1.0, color[0] / 255.0)),
                max(0.0, min(1.0, color[1] / 255.0)),
                max(0.0, min(1.0, color[2] / 255.0)),
            )
            opacity = max(0.0, min(1.0, color[3]))
            shape.draw_rect(box)
            shape.finish(color=None, fill=highlight_color, fill_opacity=opacity)
            shape.commit()
        document.save(output)
        document.close()

    def export_without_highlights(self, pdf_path: Path, output: Path) -> None:
        import shutil

        shutil.copyfile(pdf_path, output)


__all__ = ["HighlightStorage", "DEFAULT_STORAGE_DIR"]
