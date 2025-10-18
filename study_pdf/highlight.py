"""Highlight item definitions for the study PDF application."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, Optional, Tuple
import time
import uuid

from PyQt6.QtCore import (
    QEasingCurve,
    QPointF,
    QRectF,
    QVariantAnimation,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QBrush, QPen, QPainter
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGraphicsObject


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
    color: RGBAColor = (255, 215, 0, 0.3)

    def to_dict(self) -> Dict[str, object]:
        return {
            "page_number": self.page_number,
            "relative_rect": list(self.relative_rect),
            "text": self.text,
            "tag": self.tag,
            "created_ts": self.created_ts,
            "total_hover_time": self.total_hover_time,
            "uid": self.uid,
            "color": list(self.color),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, object]) -> "HighlightRecord":
        color_data = payload.get("color")
        if isinstance(color_data, (list, tuple)) and len(color_data) == 4:
            color = (
                int(color_data[0]),
                int(color_data[1]),
                int(color_data[2]),
                float(color_data[3]),
            )
        else:
            color = (255, 215, 0, 0.3)
        return cls(
            page_number=int(payload["page_number"]),
            relative_rect=tuple(payload["relative_rect"]),
            text=str(payload["text"]),
            tag=str(payload.get("tag", "General")),
            created_ts=float(payload.get("created_ts", time.time())),
            total_hover_time=float(payload.get("total_hover_time", 0.0)),
            uid=str(payload.get("uid", uuid.uuid4().hex)),
            color=color,
        )


class HighlightItem(QGraphicsObject):
    """Interactive highlight rectangle used on the PDF scene."""

    requestDeletion = pyqtSignal("PyQt_PyObject")
    requestSelection = pyqtSignal("PyQt_PyObject")
    hoverStateChanged = pyqtSignal(bool)
    geometryChanged = pyqtSignal("PyQt_PyObject")

    def __init__(
        self,
        record: HighlightRecord,
        page_rect: QRectF,
        learning_mode: bool = False,
    ) -> None:
        super().__init__()
        self.setAcceptHoverEvents(True)
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.setZValue(2)
        self.record = record
        self.page_rect = page_rect
        self.learning_mode = learning_mode
        self._hover_timer: Optional[float] = None
        self._rect = QRectF()
        self._initial_rect = QRectF()

        self._animation = QVariantAnimation(self)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setDuration(250)
        self._animation.valueChanged.connect(self._on_animation_step)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutQuad)

        base_color = record.color
        self._base_color = QColor(int(base_color[0]), int(base_color[1]), int(base_color[2]))
        self._normal_alpha = float(base_color[3])
        self._target_alpha = self._normal_alpha
        self._current_alpha = self._target_alpha

        self._pen = QPen(QColor(255, 215, 0), 1.5)
        self._pen.setCosmetic(True)
        self._brush = QBrush()
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
        self._set_rect(rect)

    def _set_rect(self, rect: QRectF) -> None:
        if rect == self._rect:
            return
        self.prepareGeometryChange()
        self._rect = QRectF(rect)
        self.update()

    def rect(self) -> QRectF:
        return QRectF(self._rect)

    def setRect(self, rect: QRectF) -> None:
        self._set_rect(rect)

    def update_record_geometry(self) -> None:
        rect = self._rect
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
        self._target_alpha = 1.0 if self.learning_mode else self._normal_alpha
        self._set_brush_alpha(self._target_alpha)

    def _set_brush_alpha(self, alpha: float) -> None:
        color = QColor(self._base_color)
        color.setAlphaF(max(0.0, min(1.0, alpha)))
        self._brush = QBrush(color)
        self._current_alpha = alpha
        self.update()

    def set_learning_mode(self, value: bool) -> None:
        self.learning_mode = value
        self._apply_mode()

    def set_color(self, rgb: Tuple[int, int, int], alpha: float) -> None:
        self._base_color = QColor(*rgb)
        self._normal_alpha = alpha
        self._apply_mode()
        self.record = replace(
            self.record,
            color=(rgb[0], rgb[1], rgb[2], alpha),
        )

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
            self._animate_to_alpha(1.0)
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
        self._initial_rect = QRectF(self._rect)

    def _perform_resize(self, pos: QPointF) -> None:
        if self._resize_origin is None:
            return
        delta = pos - self._resize_origin
        rect = QRectF(self._initial_rect)
        rect.setWidth(max(8.0, rect.width() + delta.x()))
        rect.setHeight(max(8.0, rect.height() + delta.y()))
        rect = rect.intersected(self.page_rect)
        self._set_rect(rect)

    # ------------------------------------------------------------------
    def serialize(self) -> HighlightRecord:
        self.update_record_geometry()
        return self.record

    def set_tag(self, tag: str) -> None:
        self.record = replace(self.record, tag=tag)

    # ------------------------------------------------------------------
    # QGraphicsObject API
    def boundingRect(self) -> QRectF:  # type: ignore[override]
        return QRectF(self._rect)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # type: ignore[override]
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(self._pen)
        painter.setBrush(self._brush)
        painter.drawRoundedRect(self._rect, 3.0, 3.0)


__all__ = ["HighlightRecord", "HighlightItem", "RGBAColor"]
