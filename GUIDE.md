# Active Recall PDF Studio – Implementation Guide

This guide walks through the major components needed to implement the Windows 11 PyQt6/PyMuPDF PDF study application. Each step references the corresponding modules so you can extend or adapt the project easily.

## 1. Project Structure

```
study_pdf/
  __init__.py
  main.py
  viewer.py
  highlight.py
  storage.py
  statistics.py
  utils.py
GUIDE.md
```

- `highlight.py` – Data models and the interactive `HighlightItem` graphics object. Handles hover animations, resizing, and persistence conversions.
- `viewer.py` – Assembles the PyQt6 interface (toolbar, sidebar, page views) and coordinates highlight behavior across pages.
- `storage.py` – JSON-backed persistence layer and PDF export helpers using PyMuPDF.
- `statistics.py` – Aggregates study metrics (hover time per tag).
- `utils.py` – Rendering utilities that return `QPixmap` objects for each PDF page plus quick access to text/word locations.

## 2. Rendering PDFs with PyMuPDF

1. Open a PDF using `fitz.open` (see `PdfStudyWindow._load_document`).
2. For each page call `load_page_pixmap(document, index, zoom)` to obtain a `QPixmap` suitable for Qt rendering.
3. Cache page words via `iter_page_words(page)`; this yields `(text, fitz.Rect)` tuples used when locating clicked words.
4. Feed both pixmap and words into `PageView` where a `QGraphicsScene` hosts the PDF image and highlight overlays.

## 3. Building the PyQt6 GUI

- The main window uses a `QSplitter`: left side is a scrollable stack of `PageView` widgets, right side is the highlight management sidebar.
- The toolbar exposes PDF navigation (open, previous/next page), learning mode toggle, and export commands.
- The sidebar includes:
  - `HighlightListWidget` for quick navigation.
  - Tag filter (`QComboBox`) to limit visible highlights.
  - Statistics panel updating with `statistics.summarize` results.

## 4. Creating Highlights from Mouse Input

Within `PageView.mousePressEvent`:

1. Map the mouse position from scene coordinates back to PDF coordinates using `_map_scene_to_page`.
2. Use `_word_rect_at` to find the word rectangle under the cursor.
3. Instantiate `HighlightRecord` with relative coordinates and text, then create a `HighlightItem` overlay.

## 5. Editing Highlights

`HighlightItem` (a subclass of `QGraphicsRectItem`) enables editing:

- **Move:** Default drag behavior via `ItemIsMovable` flag.
- **Resize:** Middle-mouse drag triggers `_start_resize` / `_perform_resize` with bounds checking against the PDF page rectangle.
- **Delete:** Right-click dispatches `requestDeletion` back to `PageView` for removal.

Whenever geometry changes, the `HighlightItem` emits `geometryChanged`, so `PageView` updates the underlying `HighlightRecord` before persistence.

## 6. Learning Mode & Hover Reveal

- `HighlightItem` maintains two RGBA color states: normal (`0.3` alpha) and learning (`1.0` alpha).
- Learning mode toggles are propagated from `PdfStudyWindow._set_learning_mode` → `PageView.set_learning_mode` → `HighlightItem.set_learning_mode`.
- Hover events trigger `_animate_to_alpha`, leveraging `QVariantAnimation` with a 250 ms `InOutQuad` easing curve to fade to `0.05` alpha while hovered, restoring to full opacity on leave.

## 7. Highlight Persistence

- Highlights are stored per PDF path in `%USERPROFILE%\.study_pdf/<sanitized>.json` (`HighlightStorage`).
- `save(pdf_path, records)` writes JSON with each highlight’s page number, relative rectangle, tag, captured text, and accumulated hover time.
- On load, the window reconstructs highlights per page with `PageView.load_highlight_records`.

## 8. Exporting PDFs

- **Annotated export:** `HighlightStorage.export_with_highlights` iterates highlights, redraws translucent rectangles onto a copy of the PDF via `page.new_shape()`.
- **Clean export:** Direct file copy of the original.

## 9. Session Statistics

- `HighlightItem` tracks hover durations; `HighlightRecord.total_hover_time` accrues seconds whenever a highlight is revealed.
- `statistics.summarize` groups totals per tag and formats durations for display.

## 10. Packaging for Windows 11

1. Ensure Python 3.10+ with PyQt6 and PyMuPDF installed (`pip install pyqt6 pymupdf`).
2. Use PyInstaller to build the executable:
   ```
   pyinstaller --noconfirm --windowed --name ActiveRecallPDF study_pdf/main.py
   ```
3. Distribute the generated `ActiveRecallPDF.exe` from the `dist` folder alongside any resource files.

## 11. Demo Video Checklist

When preparing the demonstration:

1. Launch the app and load a sample biology PDF.
2. Highlight terms using left-clicks.
3. Toggle Learning Mode to show full-opacity boxes.
4. Hover highlights to reveal text and mention hover animations.
5. Export the annotated PDF using the toolbar button.
6. Mention persistence by closing/reopening the file.

This guide covers the critical implementation areas. Extend tags, filters, or analytics by building on the highlighted modules.
