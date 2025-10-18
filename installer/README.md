# Windows Installer Build Guide

This directory contains assets and scripts that package **Active Recall PDF Studio** into a downloadable Windows 11
application. The workflow uses **PyInstaller** to create a standalone executable and, optionally, **Inno Setup** to wrap it
in a user-friendly installer.

## Prerequisites

- Windows 11 (64-bit)
- Python 3.10 or newer with `pip`
- [Microsoft Visual C++ Redistributable for VS 2015-2022](https://aka.ms/vs/17/release/vc_redist.x64.exe)
- (Optional) [Inno Setup 6](https://jrsoftware.org/isdl.php) if you want a single `.exe` installer

The build script installs the Python dependencies automatically, but you can also pre-install them with:

```powershell
pip install -r installer/requirements.txt
```

## Quick Start (Download from GitHub Actions)

Every push or pull request triggers the repository's automated
[`Build Windows Packages`](../.github/workflows/build-windows.yml) workflow. From the run summary you can download:

- `ActiveRecallPDF-exe` — the PyInstaller output folder containing `ActiveRecallPDF.exe`.
- `ActiveRecallPDF-installer` — the `ActiveRecallPDFInstaller.exe` produced by Inno Setup.

Use the **workflow_dispatch** button to generate a fresh build on demand, then expand the **Artifacts** section to grab the exe.

## Quick Start (Executable Only)

If you just want a portable folder containing `ActiveRecallPDF.exe`, run the PowerShell script:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
powershell -File installer/build_installer.ps1 -Mode Portable
```

The packaged application will appear under `dist/ActiveRecallPDF/`. You can zip this folder and distribute it directly.

## Full Installer Build

To generate a downloadable setup program (`ActiveRecallPDFInstaller.exe`):

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
powershell -File installer/build_installer.ps1 -Mode Installer -InnoSetupPath "C:\\Program Files (x86)\\Inno Setup 6\\ISCC.exe"
```

When the script finishes, the signed installer (not code-signed, but bundled) will be located at `dist/ActiveRecallPDFInstaller.exe`.

## Script Overview

`build_installer.ps1` performs the following steps:

1. Validates prerequisites and ensures PyInstaller is available.
2. Runs PyInstaller with the repository's [`ActiveRecallPDF.spec`](ActiveRecallPDF.spec) file so that fonts, Qt plugins,
   and the application's resources are bundled.
3. Copies documentation (`README.md`, `GUIDE.md`) into the distribution folder for end-users.
4. (Installer mode only) Invokes Inno Setup with [`ActiveRecallPDF.iss`](ActiveRecallPDF.iss) to build a guided Windows installer.
5. Produces SHA256 checksums for the generated artifacts so that you can verify integrity before publishing them.

## Customizing the Installer

- Update the metadata (publisher name, version, icons) inside `ActiveRecallPDF.spec` and `ActiveRecallPDF.iss`.
- To ship sample PDFs or study templates, add them to the `extra_files` list defined near the top of the spec file.
- Code signing can be integrated by editing the `PostBuild` section in the PowerShell script to call `signtool.exe` with your certificate.

## Publishing Tips

1. After building, upload `dist/ActiveRecallPDFInstaller.exe` (or the zipped portable folder) to your preferred hosting
   service.
2. Share the generated checksum from `dist/checksums.txt` alongside the download link.
3. Include a short README describing minimum system requirements and troubleshooting tips.

Following this guide ensures anyone can download and run the Active Recall PDF Studio application without installing
Python manually.
