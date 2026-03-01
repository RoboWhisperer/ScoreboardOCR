# ScoreboardOCR (GUI App)

Desktop GUI OCR tool for [RoboWhisperer/BasketballScoreboard](https://github.com/RoboWhisperer/BasketballScoreboard).

This project is now **GUI-first** so all configuration is done in the application window (no runtime CLI usage required).

## What the app does

- Reads a camera/video/image source.
- Uses OCR to detect scoreboard values.
- Sends recognized field updates to BasketballScoreboard API (`/api/state`).
- Lets you graphically configure ROIs (drawing boxes for each field).

Supported fields:
- `homeScore`, `awayScore`
- `gameClock` (`MM:SS`)
- `shotClock`
- `period` (`Q1`-`Q4`, `OT`, `2OT`)
- `homeFouls`, `awayFouls`
- `homeTimeouts`, `awayTimeouts`

## GUI workflow

1. Open the `ScoreboardOCR` app executable.
2. Set the source in the GUI:
   - camera index (for example `0`), or
   - video/image file path.
3. Set the API URL (default is `http://localhost:3000/api/state`).
4. Click **Edit ROIs** and draw boxes for each field.
5. Save ROI config in the GUI.
6. Click **Start OCR**.
7. Watch recognized updates in the live log panel.

## Executable packaging

The repository includes a GUI executable build script (`build_exe.py`) configured for PyInstaller one-file windowed output.

Build output is generated in the `dist` directory as `ScoreboardOCR.exe` on Windows.

## Dependency note

- Tesseract OCR must still be installed on the machine running the app.
- The app checks for Tesseract when OCR is started and shows a GUI error if missing.
## Build guide

For step-by-step Windows executable packaging instructions, see [BUILDING_EXE.md](./BUILDING_EXE.md).

