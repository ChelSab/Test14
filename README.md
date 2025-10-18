# Active Recall PDF Studio

This project delivers a Windows 11–ready PDF learning workstation featuring an interactive **Learning Mode** designed for active recall study sessions. The application is implemented with **PyQt6** for the GUI and **PyMuPDF** for all PDF rendering and export capabilities.

## Key Features

- Full PDF viewing with smooth zooming, scrolling, and multi-page support.
- Click-to-highlight using semantic word detection, with drag-to-move, middle-drag resize, and right-click delete operations.
- Learning Mode toggle that increases highlight opacity for memory drills while revealing text on hover through animated fades.
- Persistent highlight storage per document, including tag assignments and hover-time metrics.
- Sidebar highlight manager with filtering, tag editing, and session statistics grouped by tag.
- Export PDFs with or without translucent study highlights directly from the toolbar.

## Running the Application

1. Ensure Python 3.10+ is installed on Windows 11 along with the required dependencies:
   ```bash
   pip install pyqt6 pymupdf
   ```
2. Launch the interface:
   ```bash
   python -m study_pdf.main
   ```
3. Use the **Open PDF** toolbar button to load a document, then begin adding and managing study highlights.

## Building a Windows Executable

Generate a standalone `.exe` using PyInstaller:

```bash
pyinstaller --noconfirm --windowed --name ActiveRecallPDF study_pdf/main.py
```

The compiled binary will be placed in the `dist/ActiveRecallPDF/` directory.

## Documentation

Consult [`GUIDE.md`](GUIDE.md) for a step-by-step breakdown covering PyQt6 integration, event handling, persistence format, and demo preparation tips.
