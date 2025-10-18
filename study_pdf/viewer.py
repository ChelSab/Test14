"""PyQt6 widgets implementing the PDF study experience."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import fitz
from PyQt6.QtCore import QPointF, Qt, QSize, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence, QPainter, QPixmap, QIcon
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
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QComboBox,
    QStackedWidget,
    QListView,
    QStatusBar,
    QStyle,
    QSizePolicy,
    QLineEdit,
)

from .highlight import HighlightItem, HighlightRecord
from .statistics import summarize
from .storage import HighlightStorage
from .utils import iter_page_words, load_page_pixmap


def _make_color_icon(rgb: tuple[int, int, int]) -> QIcon:
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    color = QColor(*rgb)
    painter.setBrush(color)
    painter.setPen(QColor(40, 40, 40))
    painter.drawRoundedRect(2, 2, 20, 20, 4, 4)
    painter.end()
    return QIcon(pixmap)


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
        self.highlight_tool_enabled = False
        self._highlight_rgb: tuple[int, int, int] = (255, 215, 0)
        self._highlight_alpha: float = 0.3
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFrameShape(QFrame.Shape.NoFrame)

        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self.background_item = self.scene.addPixmap(self.resources.pixmap)
        self.background_item.setZValue(0)
        self.setSceneRect(self.background_item.boundingRect())
        self.setBackgroundBrush(Qt.GlobalColor.white)

        self._highlights: List[HighlightItem] = []
        self._active_resize_item: Optional[HighlightItem] = None
        self._zoom = 1.0

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
        color = (
            int(self._highlight_rgb[0]),
            int(self._highlight_rgb[1]),
            int(self._highlight_rgb[2]),
            float(self._highlight_alpha),
        )
        record = HighlightRecord(
            page_number=self.resources.page.number,
            relative_rect=relative_rect,
            text=text,
            tag=tag,
            color=color,
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

    def set_zoom(self, factor: float) -> None:
        self._zoom = factor
        self.resetTransform()
        self.scale(factor, factor)

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

    def set_highlight_tool(self, enabled: bool) -> None:
        self.highlight_tool_enabled = enabled
        self.setDragMode(QGraphicsView.DragMode.NoDrag if enabled else QGraphicsView.DragMode.ScrollHandDrag)
        cursor = Qt.CursorShape.IBeamCursor if enabled else Qt.CursorShape.ArrowCursor
        self.viewport().setCursor(cursor)

    def set_highlight_color(self, rgb: tuple[int, int, int], alpha: float) -> None:
        self._highlight_rgb = rgb
        self._highlight_alpha = alpha

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

    def update_highlight_color(
        self, uid: str, rgb: tuple[int, int, int], alpha: float
    ) -> Optional[HighlightRecord]:
        for item in self._highlights:
            if item.record.uid == uid:
                item.set_color(rgb, alpha)
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
            if self.highlight_tool_enabled:
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

    def _page_rect_to_scene(self, rect: fitz.Rect) -> QRectF:
        base = self.background_item.boundingRect()
        page_rect = self.resources.page.rect
        left = base.left() + (rect.x0 - page_rect.x0) / page_rect.width * base.width()
        top = base.top() + (rect.y0 - page_rect.y0) / page_rect.height * base.height()
        width = rect.width / page_rect.width * base.width()
        height = rect.height / page_rect.height * base.height()
        return QRectF(left, top, width, height)

    def focus_on_record(self, record: HighlightRecord) -> None:
        for item in self._highlights:
            if item.record.uid == record.uid:
                self.centerOn(item.sceneBoundingRect().center())
                item.setSelected(True)
                break

    def focus_on_search_hit(self, rect: fitz.Rect) -> None:
        scene_rect = self._page_rect_to_scene(rect)
        self.centerOn(scene_rect.center())

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
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)

    def refresh(self, records: List[HighlightRecord]) -> None:
        self.clear()
        for record in records:
            preview = record.text.strip().replace("\n", " ")
            if len(preview) > 60:
                preview = preview[:57] + "..."
            item = QListWidgetItem(f"Page {record.page_number + 1}\n{preview}")
            item.setData(Qt.ItemDataRole.UserRole, record)
            rgb = tuple(int(v) for v in record.color[:3])
            icon = _make_color_icon((rgb[0], rgb[1], rgb[2]))
            item.setIcon(icon)
            item.setToolTip(
                f"Tag: {record.tag}\nColor: RGB{rgb}\nHovered: {record.total_hover_time:.1f}s"
            )
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
        self._highlight_alpha: float = 0.3
        self.highlight_palette: Dict[str, tuple[int, int, int]] = {
            "Yellow": (255, 213, 0),
            "Green": (102, 187, 106),
            "Blue": (66, 165, 245),
            "Pink": (240, 98, 146),
            "Orange": (255, 167, 38),
        }
        self._current_highlight_rgb: tuple[int, int, int] = next(iter(self.highlight_palette.values()))

        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        toolbar = QToolBar("Document")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(22, 22))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toolbar.setStyleSheet(
            "QToolBar { background: #2b2b2b; border-bottom: 1px solid #1f1f1f; spacing: 10px; padding: 6px 12px; }"
            "QToolButton { color: #f0f0f0; padding: 4px 10px; }"
            "QToolButton:checked { background: #355fe6; border-radius: 4px; }"
            "QLabel#toolbarLabel { color: #f0f0f0; font-weight: 600; }"
            "QComboBox { background: #3a3a3a; color: #f0f0f0; border: 1px solid #555; padding: 2px 8px; }"
            "QLineEdit { background: #3a3a3a; color: #f0f0f0; border: 1px solid #555; padding: 4px 8px; border-radius: 4px; }"
        )
        self.addToolBar(toolbar)

        open_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton), "Open", self)
        open_action.triggered.connect(self._open_pdf)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        toolbar.addAction(open_action)

        self.learning_action = QAction(QIcon.fromTheme("view-preview"), "Learning Mode", self)
        self.learning_action.setCheckable(True)
        self.learning_action.toggled.connect(self._set_learning_mode)
        toolbar.addAction(self.learning_action)

        self.highlight_action = QAction(_make_color_icon(self._current_highlight_rgb), "Highlight", self)
        self.highlight_action.setCheckable(True)
        self.highlight_action.toggled.connect(self._toggle_highlight_tool)
        toolbar.addAction(self.highlight_action)

        highlight_label = QLabel("Highlight:")
        highlight_label.setObjectName("toolbarLabel")
        toolbar.addWidget(highlight_label)

        self.highlight_color_box = QComboBox()
        for name, rgb in self.highlight_palette.items():
            self.highlight_color_box.addItem(name, rgb)
            index = self.highlight_color_box.count() - 1
            self.highlight_color_box.setItemIcon(index, _make_color_icon(rgb))
        self.highlight_color_box.setCurrentIndex(0)
        self.highlight_color_box.currentIndexChanged.connect(self._on_highlight_color_changed)
        toolbar.addWidget(self.highlight_color_box)

        toolbar.addSeparator()
        prev_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack), "Previous", self)
        next_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward), "Next", self)
        prev_action.triggered.connect(lambda: self._navigate(-1))
        next_action.triggered.connect(lambda: self._navigate(1))
        toolbar.addAction(prev_action)
        toolbar.addAction(next_action)

        self.page_indicator = QLabel("Page 0 of 0")
        self.page_indicator.setStyleSheet("QLabel { font-weight: 600; color: #f0f0f0; }")
        toolbar.addWidget(self.page_indicator)

        toolbar.addSeparator()

        self.zoom_levels = [50, 75, 100, 125, 150, 200]
        self.current_zoom = 1.0
        self.zoom_box = QComboBox()
        for value in self.zoom_levels:
            self.zoom_box.addItem(f"{value}%", value)
        self.zoom_box.setCurrentText("100%")
        self.zoom_box.currentTextChanged.connect(self._handle_zoom_changed)
        zoom_label = QLabel("Zoom:")
        zoom_label.setObjectName("toolbarLabel")
        toolbar.addWidget(zoom_label)
        toolbar.addWidget(self.zoom_box)

        toolbar.addSeparator()
        export_action = QAction(QIcon.fromTheme("document-save"), "Export Annotated", self)
        export_clean_action = QAction(QIcon.fromTheme("document-save-as"), "Export Clean", self)
        export_action.triggered.connect(self._export_with_highlights)
        export_clean_action.triggered.connect(self._export_without_highlights)
        toolbar.addAction(export_action)
        toolbar.addAction(export_clean_action)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        search_label = QLabel("Find:")
        search_label.setObjectName("toolbarLabel")
        toolbar.addWidget(search_label)

        self.search_field = QLineEdit()
        self.search_field.setPlaceholderText("Search in document")
        self.search_field.returnPressed.connect(self._perform_search)
        toolbar.addWidget(self.search_field)

        central = QWidget()
        central_layout = QHBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(central)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        central_layout.addWidget(splitter)

        nav_panel = QFrame()
        nav_panel.setObjectName("navPanel")
        nav_panel.setStyleSheet(
            "#navPanel { background: #fafafa; border-right: 1px solid #d0d0d0; }"
            "QListWidget { border: none; }"
            "QListWidget::item { padding: 6px 10px; }"
            "QListWidget::item:selected { background: #0078d4; color: white; border-radius: 4px; }"
        )
        nav_layout = QVBoxLayout(nav_panel)
        nav_layout.setContentsMargins(12, 12, 12, 12)
        nav_layout.setSpacing(8)
        nav_header = QLabel("Pages")
        nav_header.setStyleSheet("font-weight: 600; color: #444;")
        nav_layout.addWidget(nav_header)
        self.thumbnail_list = QListWidget()
        self.thumbnail_list.setViewMode(QListView.ViewMode.ListMode)
        self.thumbnail_list.setUniformItemSizes(True)
        self.thumbnail_list.currentRowChanged.connect(self._on_thumbnail_changed)
        nav_layout.addWidget(self.thumbnail_list, 1)
        splitter.addWidget(nav_panel)

        viewer_frame = QFrame()
        viewer_frame.setObjectName("viewerFrame")
        viewer_frame.setStyleSheet(
            "#viewerFrame { background: #d6d6d6; }"
            "QStackedWidget { background: white; border-radius: 6px; }")
        viewer_layout = QVBoxLayout(viewer_frame)
        viewer_layout.setContentsMargins(24, 24, 24, 24)
        viewer_layout.setSpacing(12)

        self.page_stack = QStackedWidget()
        viewer_layout.addWidget(self.page_stack, 1)
        splitter.addWidget(viewer_frame)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setStyleSheet(
            "#sidebar { background: #f4f4f4; border-left: 1px solid #d0d0d0; }"
            "QLabel { color: #333; }"
            "QLabel.section { font-weight: 600; margin-top: 12px; }"
        )
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(16, 16, 16, 16)
        sidebar_layout.setSpacing(10)

        highlights_label = QLabel("Highlights")
        highlights_label.setObjectName("section")
        highlights_label.setProperty("class", "section")
        highlights_label.setStyleSheet("font-weight: 600; text-transform: uppercase; letter-spacing: 1px; font-size: 11px;")
        sidebar_layout.addWidget(highlights_label)

        self.highlight_list = HighlightListWidget()
        self.highlight_list.setAlternatingRowColors(True)
        self.highlight_list.setStyleSheet(
            "QListWidget { background: white; border: 1px solid #d0d0d0; border-radius: 4px; }"
            "QListWidget::item { padding: 6px; }"
            "QListWidget::item:selected { background: #0078d4; color: white; }"
        )
        sidebar_layout.addWidget(self.highlight_list, 2)
        self.highlight_list.highlightActivated.connect(self._focus_highlight)

        tag_label = QLabel("Edit Tag")
        tag_label.setStyleSheet("font-weight: 600; color: #555;")
        sidebar_layout.addWidget(tag_label)
        self.tag_editor = QComboBox()
        self.tag_options = ["General", "Definition", "Important", "Process"]
        self.tag_editor.addItems(self.tag_options)
        self.tag_editor.currentTextChanged.connect(self._on_tag_editor_changed)
        self.tag_editor.setEnabled(False)
        sidebar_layout.addWidget(self.tag_editor)

        filter_label = QLabel("Filter by Tag")
        filter_label.setStyleSheet("font-weight: 600; color: #555;")
        sidebar_layout.addWidget(filter_label)
        self.tag_filter = QComboBox()
        self.tag_filter.addItems(["All"] + self.tag_options)
        self.tag_filter.currentTextChanged.connect(self._refresh_sidebar)
        sidebar_layout.addWidget(self.tag_filter)

        stats_header = QLabel("Session Statistics")
        stats_header.setStyleSheet("font-weight: 600; color: #555;")
        sidebar_layout.addWidget(stats_header)
        self.stats_label = QLabel("No statistics yet")
        self.stats_label.setWordWrap(True)
        self.stats_label.setFrameShape(QFrame.Shape.StyledPanel)
        self.stats_label.setStyleSheet(
            "QLabel { background: white; border: 1px solid #d0d0d0; border-radius: 4px; padding: 6px; }"
        )
        sidebar_layout.addWidget(self.stats_label)

        sidebar_layout.addStretch(1)
        splitter.addWidget(sidebar)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 2)

        self.status = QStatusBar()
        self.status.setStyleSheet("QStatusBar { background: #f5f5f5; border-top: 1px solid #d0d0d0; }")
        self.setStatusBar(self.status)

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

        while self.page_stack.count():
            widget = self.page_stack.widget(0)
            self.page_stack.removeWidget(widget)
            widget.deleteLater()
        self.thumbnail_list.blockSignals(True)
        self.thumbnail_list.clear()
        self.thumbnail_list.blockSignals(False)
        self.tag_editor.setEnabled(False)
        self.tag_filter.blockSignals(True)
        self.tag_filter.setCurrentIndex(0)
        self.tag_filter.blockSignals(False)

        for index in range(len(self.document)):
            page, pixmap = load_page_pixmap(self.document, index, zoom=1.5)
            words = iter_page_words(page)
            resources = PageResources(page=page, pixmap=pixmap, words=words)
            page_view = PageView(resources)
            page_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            page_view.set_zoom(self.current_zoom)
            page_view.set_highlight_color(self._current_highlight_rgb, self._highlight_alpha)
            page_view.set_highlight_tool(self.highlight_action.isChecked())
            page_view.highlightCreated.connect(self._on_highlight_added)
            page_view.highlightDeleted.connect(self._on_highlight_deleted)
            page_view.highlightUpdated.connect(self._on_highlight_updated)
            page_view.highlightSelected.connect(self._on_highlight_selected)
            self.page_views[index] = page_view
            self.page_stack.addWidget(page_view)
            item = QListWidgetItem(f"Page {index + 1}")
            self.thumbnail_list.addItem(item)

        records = self.storage.load(path)
        page_map: Dict[int, List[HighlightRecord]] = {}
        for record in records:
            page_map.setdefault(record.page_number, []).append(record)
        for index, view in self.page_views.items():
            view.load_highlight_records(page_map.get(index, []))

        if self.page_views:
            self.page_stack.setCurrentIndex(0)
            self.thumbnail_list.blockSignals(True)
            self.thumbnail_list.setCurrentRow(0)
            self.thumbnail_list.blockSignals(False)

        self._refresh_sidebar()
        self._update_page_indicator()
        self.status.showMessage(f"Loaded {path.name}", 3000)

    # ------------------------------------------------------------------
    def _navigate(self, delta: int) -> None:
        if not self.page_views:
            return
        target = min(max(self.current_page_index + delta, 0), len(self.page_views) - 1)
        self.current_page_index = target
        self.page_stack.setCurrentIndex(target)
        self.thumbnail_list.blockSignals(True)
        self.thumbnail_list.setCurrentRow(target)
        self.thumbnail_list.blockSignals(False)
        self._apply_zoom_to_current()
        self._update_page_indicator()

    # ------------------------------------------------------------------
    def _set_learning_mode(self, enabled: bool) -> None:
        for view in self.page_views.values():
            view.set_learning_mode(enabled)
        self._refresh_sidebar()
        state = "on" if enabled else "off"
        self.status.showMessage(f"Learning mode {state}", 2000)

    def _toggle_highlight_tool(self, enabled: bool) -> None:
        for view in self.page_views.values():
            view.set_highlight_tool(enabled)
        state = "enabled" if enabled else "disabled"
        self.status.showMessage(f"Highlight tool {state}", 2000)

    def _apply_highlight_color_to_views(self) -> None:
        for view in self.page_views.values():
            view.set_highlight_color(self._current_highlight_rgb, self._highlight_alpha)

    def _on_highlight_color_changed(self, index: int) -> None:
        data = self.highlight_color_box.itemData(index)
        if data is None:
            return
        rgb = tuple(int(v) for v in data)
        self._current_highlight_rgb = (rgb[0], rgb[1], rgb[2])
        self.highlight_action.setIcon(_make_color_icon(self._current_highlight_rgb))
        self._apply_highlight_color_to_views()
        if self._highlight_focus_uid:
            for view in self.page_views.values():
                record = view.update_highlight_color(
                    self._highlight_focus_uid,
                    self._current_highlight_rgb,
                    self._highlight_alpha,
                )
                if record:
                    self._highlight_focus_uid = record.uid
                    break
        color_name = self.highlight_color_box.itemText(index)
        self.status.showMessage(f"Highlight color set to {color_name}", 2000)

    def _handle_zoom_changed(self, text: str) -> None:
        if not text.endswith("%"):
            return
        try:
            value = int(text.rstrip("%"))
        except ValueError:
            return
        self.current_zoom = max(25, min(value, 400)) / 100.0
        self._apply_zoom_to_current()

    def _apply_zoom_to_current(self) -> None:
        view = self.page_views.get(self.page_stack.currentIndex())
        if view:
            view.set_zoom(self.current_zoom)
        self.status.showMessage(f"Zoom {int(self.current_zoom * 100)}%", 1500)

    def _perform_search(self) -> None:
        if not self.document:
            self.status.showMessage("Load a document to search", 2000)
            return
        term = self.search_field.text().strip()
        if not term:
            self.status.showMessage("Enter text to search", 2000)
            return
        total_pages = len(self.page_views)
        if total_pages == 0:
            self.status.showMessage("No pages available", 2000)
            return
        start_index = self.current_page_index if self.page_views else 0
        term_lower = term.lower()
        for offset in range(total_pages):
            index = (start_index + offset) % total_pages
            view = self.page_views.get(index)
            if not view:
                continue
            hit_rect: Optional[fitz.Rect] = None
            for text, rect in view.word_rects:
                if term_lower in text.lower():
                    hit_rect = rect
                    break
            if hit_rect is not None:
                self.current_page_index = index
                self.page_stack.setCurrentIndex(index)
                self.thumbnail_list.blockSignals(True)
                self.thumbnail_list.setCurrentRow(index)
                self.thumbnail_list.blockSignals(False)
                view.focus_on_search_hit(hit_rect)
                self._update_page_indicator()
                self.status.showMessage(f"Found '{term}' on page {index + 1}", 3000)
                return
        self.status.showMessage(f"'{term}' not found", 3000)

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
        self.current_page_index = record.page_number
        self.page_stack.setCurrentIndex(record.page_number)
        self.thumbnail_list.blockSignals(True)
        self.thumbnail_list.setCurrentRow(record.page_number)
        self.thumbnail_list.blockSignals(False)
        self._apply_zoom_to_current()
        self._update_page_indicator()
        view.focus_on_record(record)
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
        self._sync_highlight_color_selector(record)

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
        self._sync_highlight_color_selector(record)

    def _record_by_uid(self, uid: str) -> Optional[HighlightRecord]:
        for view in self.page_views.values():
            record = view.record_by_uid(uid)
            if record:
                return record
        return None

    def _sync_highlight_color_selector(self, record: HighlightRecord) -> None:
        rgb = tuple(int(v) for v in record.color[:3])
        for index in range(self.highlight_color_box.count()):
            data = self.highlight_color_box.itemData(index)
            if data is None:
                continue
            palette_rgb = tuple(int(v) for v in data)
            if palette_rgb == rgb:
                self.highlight_color_box.blockSignals(True)
                self.highlight_color_box.setCurrentIndex(index)
                self.highlight_color_box.blockSignals(False)
                self._current_highlight_rgb = rgb
                self.highlight_action.setIcon(_make_color_icon(self._current_highlight_rgb))
                self._apply_highlight_color_to_views()
                return

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
        self.status.showMessage("Highlights saved", 1500)

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
        self.status.showMessage("Annotated export created", 3000)

    def _export_without_highlights(self) -> None:
        if not getattr(self, "document_path", None):
            return
        output, _ = QFileDialog.getSaveFileName(self, "Export Clean PDF", str(self.document_path.with_suffix("_clean.pdf")), "PDF Files (*.pdf)")
        if not output:
            return
        self.storage.export_without_highlights(self.document_path, Path(output))
        QMessageBox.information(self, "Export Complete", "Original PDF copied without highlights")
        self.status.showMessage("Clean export created", 3000)

    def _on_thumbnail_changed(self, index: int) -> None:
        if index < 0 or index >= len(self.page_views):
            return
        self.current_page_index = index
        self.page_stack.setCurrentIndex(index)
        self._apply_zoom_to_current()
        self._update_page_indicator()

    def _update_page_indicator(self) -> None:
        total = len(self.page_views)
        if total == 0:
            self.page_indicator.setText("Page 0 of 0")
            return
        self.page_indicator.setText(f"Page {self.current_page_index + 1} of {total}")


def run() -> None:
    app = QApplication.instance() or QApplication([])
    window = PdfStudyWindow()
    window.show()
    app.exec()


__all__ = ["PdfStudyWindow", "run"]
