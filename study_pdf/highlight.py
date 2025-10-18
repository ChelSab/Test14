"""Highlight item definitions for the study PDF application."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, Optional, Tuple
import time
import uuid

from PyQt6.QtCore import QEasingCurve, QPointF, QRectF, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QColor, QBrush, QPen
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGraphicsRectItem


RGBAColor = Tuple[int, int, int, float]


@dataclass
class HighlightRecord:
    """Serializable highlight representation used for persistence."""

    page_number: int
    relative_rect: Tuple[float, float, float, float]
    text: str
    tag: str = "General"
    created_ts: float = field(default_factory=lambda: time.time())
    total_hover_time: float = 0.0
    uid: str = field(default_factory=lambda: uuid.uuid4().hex)

    def to_dict(self) -> Dict[str, object]:
        return {
            "page_number": self.page_number,
            "relative_rect": list(self.relative_rect),
            "text": self.text,
            "tag": self.tag,
            "created_ts": self.created_ts,
            "total_hover_time": self.total_hover_time,
            "uid": self.uid,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, object]) -> "HighlightRecord":
        return cls(
            page_number=int(payload["page_number"]),
            relative_rect=tuple(payload["relative_rect"]),
            text=str(payload["text"]),
            tag=str(payload.get("tag", "General")),
            created_ts=float(payload.get("created_ts", time.time())),
            total_hover_time=float(payload.get("total_hover_time", 0.0)),
            uid=str(payload.get("uid", uuid.uuid4().hex)),
        )


class HighlightItem(QGraphicsRectItem):
    """Interactive highlight rectangle used on the PDF scene."""

    requestDeletion = pyqtSignal("PyQt_PyObject")
    requestSelection = pyqtSignal("PyQt_PyObject")
    hoverStateChanged = pyqtSignal(bool)
    geometryChanged = pyqtSignal("PyQt_PyObject")

    NORMAL_COLOR: RGBAColor = (255, 255, 0, 0.3)
    LEARNING_COLOR: RGBAColor = (255, 255, 0, 1.0)

    def __init__(
        self,
        record: HighlightRecord,
        page_rect: QRectF,
        learning_mode: bool = False,
    ) -> None:
        super().__init__()
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setZValue(2)
        self.record = record
        self.page_rect = page_rect
        self.learning_mode = learning_mode
        self._hover_timer: Optional[float] = None

        self._animation = QVariantAnimation(
            startValue=0.0,
            endValue=1.0,
            duration=250,
        )
        self._animation.valueChanged.connect(self._on_animation_step)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutQuad)

        self._target_alpha = self.NORMAL_COLOR[3]
        self._current_alpha = self._target_alpha

        self.setPen(QPen(QColor(255, 215, 0), 1.5))
        self._update_geometry_from_record()
        self._apply_mode()

    # ------------------------------------------------------------------
    # Geometry helpers
    def _update_geometry_from_record(self) -> None:
        x, y, w, h = self.record.relative_rect
        rect = QRectF(
            self.page_rect.left() + x * self.page_rect.width(),
            self.page_rect.top() + y * self.page_rect.height(),
            w * self.page_rect.width(),
            h * self.page_rect.height(),
        )
        self.setRect(rect)

    def update_record_geometry(self) -> None:
        rect = self.rect()
        rel_rect = (
            (rect.left() - self.page_rect.left()) / self.page_rect.width(),
            (rect.top() - self.page_rect.top()) / self.page_rect.height(),
            rect.width() / self.page_rect.width(),
            rect.height() / self.page_rect.height(),
        )
        self.record = replace(
            self.record,
            relative_rect=rel_rect,
        )
        self.geometryChanged.emit(self.record)

    # ------------------------------------------------------------------
    # Color handling
    def _apply_mode(self) -> None:
        rgba = self.LEARNING_COLOR if self.learning_mode else self.NORMAL_COLOR
        self._target_alpha = rgba[3]
        self._set_brush_alpha(self._target_alpha)

    def _set_brush_alpha(self, alpha: float) -> None:
        color = QColor(255, 255, 0)
        color.setAlphaF(max(0.0, min(1.0, alpha)))
        self.setBrush(QBrush(color))
        self._current_alpha = alpha

    def set_learning_mode(self, value: bool) -> None:
        self.learning_mode = value
        self._apply_mode()

    # ------------------------------------------------------------------
    # Event overrides
    def hoverEnterEvent(self, event) -> None:  # type: ignore[override]
        self.hoverStateChanged.emit(True)
        self._start_hover_timer()
        if self.learning_mode:
            self._animate_to_alpha(0.05)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:  # type: ignore[override]
        self.hoverStateChanged.emit(False)
        self._stop_hover_timer()
        if self.learning_mode:
            self._animate_to_alpha(self.LEARNING_COLOR[3])
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.RightButton:
            self.requestDeletion.emit(self)
            event.accept()
            return
        if event.button() == Qt.MouseButton.MiddleButton:
            self._start_resize(event.scenePos())
            event.accept()
            return
        self.requestSelection.emit(self)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._resize_origin is not None:
            self._perform_resize(event.scenePos())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if self._resize_origin is not None:
            self._perform_resize(event.scenePos())
            self._resize_origin = None
            self.update_record_geometry()
            event.accept()
            return
        super().mouseReleaseEvent(event)
        self.update_record_geometry()

    # ------------------------------------------------------------------
    # Hover timing
    def _start_hover_timer(self) -> None:
        if self._hover_timer is None:
            self._hover_timer = time.time()

    def _stop_hover_timer(self) -> None:
        if self._hover_timer is not None:
            delta = time.time() - self._hover_timer
            self.record.total_hover_time += delta
            self._hover_timer = None

    # ------------------------------------------------------------------
    # Animation helpers
    def _animate_to_alpha(self, target: float) -> None:
        self._animation.stop()
        self._animation.setStartValue(self._current_alpha)
        self._animation.setEndValue(target)
        self._animation.start()

    def _on_animation_step(self, value: float) -> None:
        self._set_brush_alpha(value)

    # ------------------------------------------------------------------
    # Resizing support
    _resize_origin: Optional[QPointF] = None

    def _start_resize(self, pos: QPointF) -> None:
        self._resize_origin = pos
        self._initial_rect = QRectF(self.rect())

    def _perform_resize(self, pos: QPointF) -> None:
        if self._resize_origin is None:
            return
        delta = pos - self._resize_origin
        rect = QRectF(self._initial_rect)
        rect.setWidth(max(8.0, rect.width() + delta.x()))
        rect.setHeight(max(8.0, rect.height() + delta.y()))
        rect = rect.intersected(self.page_rect)
        self.setRect(rect)

    # ------------------------------------------------------------------
    def serialize(self) -> HighlightRecord:
        self.update_record_geometry()
        return self.record

    def set_tag(self, tag: str) -> None:
        self.record = replace(self.record, tag=tag)

