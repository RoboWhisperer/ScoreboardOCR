# ScoreboardOCR

Python OCR bridge for [RoboWhisperer/BasketballScoreboard](https://github.com/RoboWhisperer/BasketballScoreboard).

This program reads scoreboard values from a camera/video/image and pushes recognized fields to the scoreboard app API (`POST /api/state`).

## Features

- Compatible with BasketballScoreboard state fields:
  - `homeScore`, `awayScore`
  - `gameClock` (`MM:SS`)
  - `shotClock`
  - `period` (`Q1`-`Q4`, `OT`, `2OT`)
  - `homeFouls`, `awayFouls`
  - `homeTimeouts`, `awayTimeouts`
- **Interactive ROI GUI** to draw boxes for each field and export JSON config.
- Delta updates only: only changed fields are POSTed.
- Supports camera index, video file, and single image mode.

## Requirements

- Python 3.10+
- Tesseract OCR installed on your machine (binary `tesseract` must be available)
- Python packages:

```bash
pip install -r requirements.txt
```

## Quick start

1) Create/tune ROIs with GUI:

```bash
python ocr_scoreboard.py --source ./frame_or_video.mp4 --roi-gui --roi-output ./config.generated.json
```

Notes:
- If `--source` is a camera/video, the GUI uses the first readable frame.
- Draw a rectangle per field, switch fields in dropdown, then click **Save**.

2) Run OCR and push updates to BasketballScoreboard API:

```bash
python ocr_scoreboard.py --source 0 --api http://localhost:3000/api/state --config ./config.generated.json --debug
```

## Usage examples

### Camera source

```bash
python ocr_scoreboard.py --source 0 --api http://localhost:3000/api/state --config ./config.example.json
```

### Video file source

```bash
python ocr_scoreboard.py --source ./game_feed.mp4 --config ./config.example.json --interval 0.2
```

### Single image source

```bash
python ocr_scoreboard.py --source ./frame.png --config ./config.example.json --debug
```

## ROI configuration format

ROIs are normalized fractions:

```json
"field": [x, y, width, height]
```

All values are relative to frame size (0.0-1.0).

## Notes

- `--interval` controls OCR rate (default `0.15s`).
- `--http-timeout` controls POST timeout (default `0.25s`).
- On network/API errors, the script keeps running and retries on next update.
- `--roi-gui` mode does **not** require Tesseract installed; OCR mode does.
