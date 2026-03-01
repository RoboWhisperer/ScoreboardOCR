# Building `ScoreboardOCR.exe`

This guide explains how to build a Windows executable for ScoreboardOCR.

## 1) Prerequisites

- **Windows 10/11** (recommended for the final build output)
- **Python 3.10+** installed
- **Tesseract OCR** installed on the target machine (the app requires it at runtime)
- Project source code checked out locally

> Note: PyInstaller builds are platform-specific. To produce a real `ScoreboardOCR.exe`, build on Windows.

## 2) Create and activate a virtual environment

Open PowerShell in the project folder and run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If script execution is blocked, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## 3) Install dependencies

```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

This installs:
- OCR/runtime dependencies (`opencv-python-headless`, `pytesseract`, `numpy`, `Pillow`)
- packaging dependency (`pyinstaller`)

## 4) Optional: set an app icon

If you want a custom icon:
- Place an `.ico` file in the project root named `app.ico`

The build script automatically uses it if present.

## 5) Build the executable

Run:

```powershell
python build_exe.py
```

The script calls PyInstaller in one-file, windowed mode.

## 6) Find the output

After a successful build, your executable will be at:

```text
dist\ScoreboardOCR.exe
```

## 7) First-run checklist on a target PC

1. Install **Tesseract OCR** (if not already installed)
2. Launch `ScoreboardOCR.exe`
3. Configure source/API/ROIs in the GUI
4. Start OCR

## 8) Troubleshooting

### `ModuleNotFoundError` during build
- Re-activate `.venv`
- Re-run `pip install -r requirements.txt`

### EXE starts but OCR won’t run
- Usually Tesseract is missing from PATH
- Install Tesseract and restart the app

### Windows SmartScreen warning
- Unsigned executables may trigger this
- Choose **More info** → **Run anyway** for local/internal use

### Antivirus false positives
- One-file PyInstaller apps can trigger heuristics
- Add an exclusion or sign the executable for distribution

## 9) Clean rebuild

If you need a fresh package:

```powershell
Remove-Item -Recurse -Force build, dist
Remove-Item -Force ScoreboardOCR.spec
python build_exe.py
```
