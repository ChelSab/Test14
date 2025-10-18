"""PyQt6 widgets implementing the PDF study experience."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import fitz
from PyQt6.QtCore import QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QComboBox,
)

from .highlight import HighlightItem, HighlightRecord
from .statistics import summarize
from .storage import HighlightStorage
from .utils import iter_page_words, load_page_pixmap


@dataclass
class PageResources:
    page: fitz.Page
    pixmap: QPixmap
    words: List[tuple[str, fitz.Rect]]


class PageView(QGraphicsView):
    """Displays a single PDF page with interactive highlight management."""

    highlightCreated = pyqtSignal(HighlightRecord)
    highlightDeleted = pyqtSignal(HighlightRecord)
    highlightUpdated = pyqtSignal(HighlightRecord)
    highlightSelected = pyqtSignal(HighlightRecord)

    def __init__(self, resources: PageResources, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.resources = resources
        self.learning_mode = False
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self.background_item = self.scene.addPixmap(self.resources.pixmap)
        self.background_item.setZValue(0)

        self._highlights: List[HighlightItem] = []
        self._active_resize_item: Optional[HighlightItem] = None

        self._populate_word_cache()

    # ------------------------------------------------------------------
    def _populate_word_cache(self) -> None:
        self.word_rects: List[tuple[str, fitz.Rect]] = self.resources.words

    # ------------------------------------------------------------------
    def add_highlight_from_rect(self, rect: fitz.Rect, text: str, tag: str = "General") -> HighlightItem:
        page_rect = self.resources.page.rect
        relative_rect = (
            (rect.x0 - page_rect.x0) / page_rect.width,
            (rect.y0 - page_rect.y0) / page_rect.height,
            rect.width / page_rect.width,
            rect.height / page_rect.height,
        )
        record = HighlightRecord(
            page_number=self.resources.page.number,
            relative_rect=relative_rect,
            text=text,
            tag=tag,
        )
        item = HighlightItem(record, self.background_item.boundingRect(), self.learning_mode)
        item.requestDeletion.connect(self._on_item_delete)
        item.requestSelection.connect(self._on_item_select)
        item.geometryChanged.connect(self._on_item_geometry_changed)
        item.hoverStateChanged.connect(lambda _, it=item: self.highlightUpdated.emit(it.record))
        self.scene.addItem(item)
        self._highlights.append(item)
        self.highlightCreated.emit(record)
        return item

    # ------------------------------------------------------------------
    def clear_highlights(self) -> None:
        for item in list(self._highlights):
            self.scene.removeItem(item)
        self._highlights.clear()

    def load_highlight_records(self, records: List[HighlightRecord]) -> None:
        self.clear_highlights()
        for record in records:
            item = HighlightItem(record, self.background_item.boundingRect(), self.learning_mode)
            item.requestDeletion.connect(self._on_item_delete)
            item.requestSelection.connect(self._on_item_select)
            item.geometryChanged.connect(self._on_item_geometry_changed)
            item.hoverStateChanged.connect(lambda _, it=item: self.highlightUpdated.emit(it.record))
            self.scene.addItem(item)
            self._highlights.append(item)

    def iter_records(self) -> List[HighlightRecord]:
        return [item.serialize() for item in self._highlights]

    def record_by_uid(self, uid: str) -> Optional[HighlightRecord]:
        for item in self._highlights:
            if item.record.uid == uid:
                return item.serialize()
        return None

    def update_tag(self, uid: str, tag: str) -> Optional[HighlightRecord]:
        for item in self._highlights:
            if item.record.uid == uid:
                item.set_tag(tag)
                record = item.serialize()
                self.highlightUpdated.emit(record)
                return record
        return None

    # ------------------------------------------------------------------
    def set_learning_mode(self, enabled: bool) -> None:
        self.learning_mode = enabled
        for item in self._highlights:
            item.set_learning_mode(enabled)

    # ------------------------------------------------------------------
    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            graphics_item = self.itemAt(event.position().toPoint())
            if graphics_item and graphics_item is not self.background_item:
                super().mousePressEvent(event)
                return
            scene_pos = self.mapToScene(event.position().toPoint())
            page_point = self._map_scene_to_page(scene_pos)
            rect, text = self._word_rect_at(page_point)
            if rect is not None:
                item = self.add_highlight_from_rect(rect, text)
                self.highlightSelected.emit(item.record)
                return
        super().mousePressEvent(event)

    # ------------------------------------------------------------------
    def _map_scene_to_page(self, point: QPointF) -> fitz.Point:
        rect = self.background_item.boundingRect()
        x = self.resources.page.rect.x0 + (point.x() - rect.left()) / rect.width() * self.resources.page.rect.width
        y = self.resources.page.rect.y0 + (point.y() - rect.top()) / rect.height() * self.resources.page.rect.height
        return fitz.Point(x, y)

    def _word_rect_at(self, point: fitz.Point) -> tuple[Optional[fitz.Rect], str]:
        for text, rect in self.word_rects:
            if rect.contains(point):
                return rect, text
        return None, ""

    # ------------------------------------------------------------------
    def _on_item_delete(self, item: HighlightItem) -> None:
        if item in self._highlights:
            self._highlights.remove(item)
            self.scene.removeItem(item)
            self.highlightDeleted.emit(item.record)

    def _on_item_select(self, item: HighlightItem) -> None:
        self.highlightSelected.emit(item.record)

    def _on_item_geometry_changed(self, record: HighlightRecord) -> None:
        self.highlightUpdated.emit(record)


class HighlightListWidget(QListWidget):
    """Sidebar list showing the highlights on the current page."""

    highlightActivated = pyqtSignal(HighlightRecord)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.itemActivated.connect(self._handle_activation)

    def refresh(self, records: List[HighlightRecord]) -> None:
        self.clear()
        for record in records:
            item = QListWidgetItem(f"p{record.page_number + 1}: {record.text[:40]}")
            item.setData(Qt.ItemDataRole.UserRole, record)
            item.setToolTip(f"Tag: {record.tag}\nHovered: {record.total_hover_time:.1f}s")
            self.addItem(item)

    def _handle_activation(self, item: QListWidgetItem) -> None:
        record = item.data(Qt.ItemDataRole.UserRole)
        if record:
            self.highlightActivated.emit(record)


class PdfStudyWindow(QMainWindow):
    """Main window that hosts the PDF study application."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Active Recall PDF Studio")
        self.resize(1280, 800)
        self.storage = HighlightStorage()

        self.document: Optional[fitz.Document] = None
        self.page_views: Dict[int, PageView] = {}
        self.current_page_index: int = 0
        self._highlight_focus_uid: Optional[str] = None

        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        open_action = QAction("Open PDF", self)
        open_action.triggered.connect(self._open_pdf)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        toolbar.addAction(open_action)

        self.learning_action = QAction("Learning Mode", self)
        self.learning_action.setCheckable(True)
        self.learning_action.toggled.connect(self._set_learning_mode)
        toolbar.addAction(self.learning_action)

        toolbar.addSeparator()
        prev_action = QAction("Previous", self)
        next_action = QAction("Next", self)
        prev_action.triggered.connect(lambda: self._navigate(-1))
        next_action.triggered.connect(lambda: self._navigate(1))
        toolbar.addAction(prev_action)
        toolbar.addAction(next_action)

        toolbar.addSeparator()
        export_action = QAction("Export Annotated", self)
        export_clean_action = QAction("Export Clean", self)
        export_action.triggered.connect(self._export_with_highlights)
        export_clean_action.triggered.connect(self._export_without_highlights)
        toolbar.addAction(export_action)
        toolbar.addAction(export_clean_action)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        self.page_container = QScrollArea()
        self.page_container.setWidgetResizable(True)
        splitter.addWidget(self.page_container)

        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(6, 6, 6, 6)

        self.highlight_list = HighlightListWidget()
        sidebar_layout.addWidget(QLabel("Highlights"))
        sidebar_layout.addWidget(self.highlight_list, 2)
        self.highlight_list.highlightActivated.connect(self._focus_highlight)

        sidebar_layout.addWidget(QLabel("Edit Tag"))
        self.tag_editor = QComboBox()
        self.tag_options = ["General", "Definition", "Important", "Process"]
        self.tag_editor.addItems(self.tag_options)
        self.tag_editor.currentTextChanged.connect(self._on_tag_editor_changed)
        self.tag_editor.setEnabled(False)
        sidebar_layout.addWidget(self.tag_editor)

        self.tag_filter = QComboBox()
        self.tag_filter.addItems(["All"] + self.tag_options)
        self.tag_filter.currentTextChanged.connect(self._refresh_sidebar)
        sidebar_layout.addWidget(QLabel("Filter by Tag"))
        sidebar_layout.addWidget(self.tag_filter)

        self.stats_label = QLabel("No statistics yet")
        self.stats_label.setFrameShape(QFrame.Shape.StyledPanel)
        self.stats_label.setWordWrap(True)
        sidebar_layout.addWidget(QLabel("Session Statistics"))
        sidebar_layout.addWidget(self.stats_label)

        splitter.addWidget(sidebar)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)

    # ------------------------------------------------------------------
    def _open_pdf(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Open PDF", str(Path.home()), "PDF Files (*.pdf)")
        if not file_path:
            return
        try:
            self._load_document(Path(file_path))
        except Exception as exc:
            QMessageBox.critical(self, "Unable to open PDF", str(exc))

    def _load_document(self, path: Path) -> None:
        self.document = fitz.open(path)
        self.document_path = path
        self.page_views.clear()
        self.current_page_index = 0
        self._highlight_focus_uid = None

        if self.page_container.widget():
            self.page_container.widget().deleteLater()

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(12, 12, 12, 12)
        container_layout.setSpacing(24)

        for index in range(len(self.document)):
            page, pixmap = load_page_pixmap(self.document, index, zoom=1.5)
            words = iter_page_words(page)
            resources = PageResources(page=page, pixmap=pixmap, words=words)
            page_view = PageView(resources)
            page_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            page_view.setMinimumHeight(pixmap.height() + 32)
            page_view.highlightCreated.connect(self._on_highlight_added)
            page_view.highlightDeleted.connect(self._on_highlight_deleted)
            page_view.highlightUpdated.connect(self._on_highlight_updated)
            page_view.highlightSelected.connect(self._on_highlight_selected)
            self.page_views[index] = page_view
            container_layout.addWidget(page_view)

        container_layout.addStretch(1)
        self.page_container.setWidget(container)

        records = self.storage.load(path)
        page_map: Dict[int, List[HighlightRecord]] = {}
        for record in records:
            page_map.setdefault(record.page_number, []).append(record)
        for index, view in self.page_views.items():
            view.load_highlight_records(page_map.get(index, []))

        self._refresh_sidebar()

    # ------------------------------------------------------------------
    def _navigate(self, delta: int) -> None:
        if not self.page_views:
            return
        target = min(max(self.current_page_index + delta, 0), len(self.page_views) - 1)
        self.current_page_index = target
        view = self.page_views[target]
        widget = view.parentWidget()
        if widget:
            self.page_container.ensureWidgetVisible(view)

    # ------------------------------------------------------------------
    def _set_learning_mode(self, enabled: bool) -> None:
        for view in self.page_views.values():
            view.set_learning_mode(enabled)
        self._refresh_sidebar()

    # ------------------------------------------------------------------
    def _on_highlight_added(self, record: HighlightRecord) -> None:
        self._save_state()
        self._refresh_sidebar()

    def _on_highlight_deleted(self, record: HighlightRecord) -> None:
        self._save_state()
        self._refresh_sidebar()

    def _on_highlight_updated(self, record: HighlightRecord) -> None:
        self._save_state()
        self._refresh_sidebar()

    def _on_highlight_selected(self, record: HighlightRecord) -> None:
        self._select_highlight(record)

    # ------------------------------------------------------------------
    def _focus_highlight(self, record: HighlightRecord) -> None:
        view = self.page_views.get(record.page_number)
        if not view:
            return
        self.page_container.ensureWidgetVisible(view)
        self.current_page_index = record.page_number
        self._select_highlight(record)

    def _select_highlight(self, record: HighlightRecord) -> None:
        self._highlight_focus_uid = record.uid
        self.tag_editor.blockSignals(True)
        self.tag_editor.setEnabled(True)
        if record.tag in self.tag_options:
            index = self.tag_options.index(record.tag)
            self.tag_editor.setCurrentIndex(index)
        else:
            if record.tag not in self.tag_options:
                self.tag_options.append(record.tag)
                self.tag_editor.addItem(record.tag)
                self.tag_filter.addItem(record.tag)
            self.tag_editor.setCurrentText(record.tag)
        self.tag_editor.blockSignals(False)

    # ------------------------------------------------------------------
    def _refresh_sidebar(self) -> None:
        if not self.document:
            self.highlight_list.clear()
            return
        tag_filter = self.tag_filter.currentText()
        records: List[HighlightRecord] = []
        for view in self.page_views.values():
            for record in view.iter_records():
                if tag_filter != "All" and record.tag != tag_filter:
                    continue
                records.append(record)
        self.highlight_list.refresh(records)
        stats = summarize(records)
        if not stats:
            self.stats_label.setText("No highlights yet")
        else:
            lines = []
            for tag, stat in stats.items():
                lines.append(f"{tag}: {stat.highlight_count} items, {stat.formatted_duration} in hover")
            self.stats_label.setText("\n".join(lines))
        self._restore_tag_selection()

    def _restore_tag_selection(self) -> None:
        if not self._highlight_focus_uid:
            self.tag_editor.setEnabled(False)
            return
        record = self._record_by_uid(self._highlight_focus_uid)
        if not record:
            self.tag_editor.setEnabled(False)
            return
        self.tag_editor.blockSignals(True)
        if record.tag in self.tag_options:
            self.tag_editor.setCurrentIndex(self.tag_options.index(record.tag))
        else:
            self.tag_editor.setCurrentText(record.tag)
        self.tag_editor.blockSignals(False)

    def _record_by_uid(self, uid: str) -> Optional[HighlightRecord]:
        for view in self.page_views.values():
            record = view.record_by_uid(uid)
            if record:
                return record
        return None

    def _on_tag_editor_changed(self, tag: str) -> None:
        if not self._highlight_focus_uid:
            return
        for view in self.page_views.values():
            record = view.update_tag(self._highlight_focus_uid, tag)
            if record:
                self._highlight_focus_uid = record.uid
                break
        self._save_state()
        self._refresh_sidebar()

    # ------------------------------------------------------------------
    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._save_state()
        super().closeEvent(event)

    # ------------------------------------------------------------------
    def _collect_records(self) -> List[HighlightRecord]:
        records: List[HighlightRecord] = []
        for view in self.page_views.values():
            records.extend(view.iter_records())
        return records

    def _save_state(self) -> None:
        if not getattr(self, "document_path", None):
            return
        records = self._collect_records()
        self.storage.save(self.document_path, records)

    # ------------------------------------------------------------------
    def _export_with_highlights(self) -> None:
        if not getattr(self, "document_path", None):
            return
        output, _ = QFileDialog.getSaveFileName(self, "Export Annotated PDF", str(self.document_path.with_suffix("_study.pdf")), "PDF Files (*.pdf)")
        if not output:
            return
        records = self._collect_records()
        self.storage.export_with_highlights(self.document_path, records, Path(output))
        QMessageBox.information(self, "Export Complete", "Annotated PDF exported successfully")

    def _export_without_highlights(self) -> None:
        if not getattr(self, "document_path", None):
            return
        output, _ = QFileDialog.getSaveFileName(self, "Export Clean PDF", str(self.document_path.with_suffix("_clean.pdf")), "PDF Files (*.pdf)")
        if not output:
            return
        self.storage.export_without_highlights(self.document_path, Path(output))
        QMessageBox.information(self, "Export Complete", "Original PDF copied without highlights")


def run() -> None:
    app = QApplication.instance() or QApplication([])
    window = PdfStudyWindow()
    window.show()
    app.exec()


__all__ = ["PdfStudyWindow", "run"]
