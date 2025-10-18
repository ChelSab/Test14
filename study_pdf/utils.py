"""Utility helpers for the study PDF application."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Tuple

import fitz
from PyQt6.QtGui import QImage, QPixmap


def load_page_pixmap(document: fitz.Document, page_number: int, zoom: float = 1.5) -> Tuple[fitz.Page, QPixmap]:
    """Render a page to a QPixmap."""
    page = document.load_page(page_number)
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
    qpix = QPixmap.fromImage(image.copy())
    return page, qpix


def iter_page_words(page: fitz.Page) -> List[Tuple[str, fitz.Rect]]:
    """Return a list of words and their rectangles for the page."""
    words = page.get_text("words")
    return [(w[4], fitz.Rect(w[:4])) for w in words]


def ensure_exists(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


__all__ = ["load_page_pixmap", "iter_page_words", "ensure_exists"]
