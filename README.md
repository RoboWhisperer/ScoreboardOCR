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
- Delta updates only: only changed fields are POSTed.
- Configurable normalized ROI regions via JSON (`config.example.json`).
- Supports camera index, video file, and single image mode.

## Requirements

- Python 3.10+
- Tesseract OCR installed on your machine (binary `tesseract` must be available)
- Python packages:

```bash
pip install -r requirements.txt
```

## Usage

Start the BasketballScoreboard server first (default: `http://localhost:3000`).

### 1) Camera source

```bash
python ocr_scoreboard.py --source 0 --api http://localhost:3000/api/state --debug
```

### 2) Video file source

```bash
python ocr_scoreboard.py --source ./game_feed.mp4 --config ./config.example.json --interval 0.2
```

### 3) Single image source

```bash
python ocr_scoreboard.py --source ./frame.png --config ./config.example.json --debug
```

## ROI configuration

Use `config.example.json` as a starting point. ROIs are normalized fractions:

```json
"field": [x, y, width, height]
```

All values are relative to frame size (0.0-1.0).

Tune these boxes to your scoreboard position/layout for best OCR accuracy.

## Notes

- `--interval` controls OCR rate (default `0.15s`).
- `--http-timeout` controls POST timeout (default `0.25s`).
- On network/API errors, the script keeps running and retries on next update.
