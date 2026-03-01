#!/usr/bin/env python3
"""Basketball scoreboard OCR bridge for RoboWhisperer/BasketballScoreboard.

Reads frames from an image, video file, or camera, OCRs configured regions, and
POSTs merged state updates to the Scorebug API (/api/state).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
from urllib import error, request

import cv2  # type: ignore
import numpy as np
import pytesseract  # type: ignore
from pytesseract import TesseractNotFoundError

from roi_selector_gui import launch_roi_selector


DEFAULT_ROIS: Dict[str, list[float]] = {
    "homeScore": [0.28, 0.71, 0.08, 0.16],
    "awayScore": [0.64, 0.71, 0.08, 0.16],
    "gameClock": [0.42, 0.70, 0.16, 0.16],
    "shotClock": [0.46, 0.83, 0.08, 0.11],
    "period": [0.44, 0.60, 0.12, 0.08],
    "homeFouls": [0.22, 0.83, 0.05, 0.09],
    "awayFouls": [0.73, 0.83, 0.05, 0.09],
    "homeTimeouts": [0.18, 0.90, 0.08, 0.05],
    "awayTimeouts": [0.74, 0.90, 0.08, 0.05],
}


@dataclass
class OCRField:
    key: str
    whitelist: str
    psm: int = 7


OCR_FIELDS = {
    "homeScore": OCRField("homeScore", "0123456789", 8),
    "awayScore": OCRField("awayScore", "0123456789", 8),
    "gameClock": OCRField("gameClock", "0123456789:", 7),
    "shotClock": OCRField("shotClock", "0123456789", 8),
    "period": OCRField("period", "QOT123456789", 8),
    "homeFouls": OCRField("homeFouls", "0123456789", 8),
    "awayFouls": OCRField("awayFouls", "0123456789", 8),
    "homeTimeouts": OCRField("homeTimeouts", "0123456789", 8),
    "awayTimeouts": OCRField("awayTimeouts", "0123456789", 8),
}


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


def load_config(path: Optional[Path]) -> Dict[str, Any]:
    if not path or not path.exists():
        return {"rois": DEFAULT_ROIS}
    with path.open("r", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("rois", DEFAULT_ROIS)
    return cfg


def roi_pixels(frame: np.ndarray, roi_norm: list[float]) -> np.ndarray:
    h, w = frame.shape[:2]
    x1 = max(0, int(roi_norm[0] * w))
    y1 = max(0, int(roi_norm[1] * h))
    x2 = min(w, int((roi_norm[0] + roi_norm[2]) * w))
    y2 = min(h, int((roi_norm[1] + roi_norm[3]) * h))
    return frame[y1:y2, x1:x2]


def preprocess(roi: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return cv2.resize(bw, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)


def ocr_text(img: np.ndarray, field: OCRField) -> str:
    config = f"--oem 3 --psm {field.psm} -c tessedit_char_whitelist={field.whitelist}"
    text = pytesseract.image_to_string(img, config=config)
    return re.sub(r"\s+", "", text).upper()


def parse_clock(text: str) -> Optional[str]:
    cleaned = text.replace(";", ":").replace(".", ":")
    m = re.search(r"(\d{1,2}):(\d{2})", cleaned)
    if not m:
        return None
    mm, ss = int(m.group(1)), int(m.group(2))
    if ss > 59:
        return None
    return f"{mm}:{ss:02d}"


def parse_int(text: str, min_v: int = 0, max_v: int = 999) -> Optional[int]:
    m = re.search(r"\d+", text)
    if not m:
        return None
    value = int(m.group(0))
    if value < min_v or value > max_v:
        return None
    return value


def parse_period(text: str) -> Optional[str]:
    t = text.replace("0", "O")
    valid = {"Q1", "Q2", "Q3", "Q4", "OT", "2OT"}
    if t in valid:
        return t
    if t in {"1", "2", "3", "4"}:
        return f"Q{t}"
    if t in {"O", "OT1"}:
        return "OT"
    if t in {"20T", "2OТ"}:
        return "2OT"
    return None


def extract_state(frame: np.ndarray, rois: Dict[str, list[float]]) -> Dict[str, Any]:
    state: Dict[str, Any] = {}
    for key, roi_norm in rois.items():
        if key not in OCR_FIELDS:
            continue
        roi = roi_pixels(frame, roi_norm)
        if roi.size == 0:
            continue
        text = ocr_text(preprocess(roi), OCR_FIELDS[key])
        if key in {"homeScore", "awayScore"}:
            val = parse_int(text, 0, 300)
        elif key in {"homeFouls", "awayFouls"}:
            val = parse_int(text, 0, 20)
        elif key in {"homeTimeouts", "awayTimeouts"}:
            val = parse_int(text, 0, 7)
        elif key == "shotClock":
            val = parse_int(text, 0, 24)
        elif key == "gameClock":
            val = parse_clock(text)
        elif key == "period":
            val = parse_period(text)
        else:
            val = None

        if val is not None:
            state[key] = val
    return state


def post_json(url: str, payload: Dict[str, Any], timeout: float) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with request.urlopen(req, timeout=timeout):
            return
    except error.URLError:
        return


def create_capture(source: str) -> cv2.VideoCapture:
    if source.isdigit():
        return cv2.VideoCapture(int(source))
    return cv2.VideoCapture(source)


def should_push(new_state: Dict[str, Any], old_state: Dict[str, Any]) -> Dict[str, Any]:
    changed = {k: v for k, v in new_state.items() if old_state.get(k) != v}
    old_state.update(changed)
    return changed


def read_sample_frame(source: str) -> Optional[np.ndarray]:
    source_path = Path(source)
    if source_path.exists() and source_path.suffix.lower() in IMAGE_SUFFIXES:
        return cv2.imread(str(source_path))

    cap = create_capture(source)
    if not cap.isOpened():
        return None
    ok, frame = cap.read()
    cap.release()
    if not ok:
        return None
    return frame


def run_roi_gui(source: str, output_path: Path, rois: Dict[str, list[float]]) -> int:
    frame = read_sample_frame(source)
    if frame is None:
        print(f"Unable to open source for ROI selection: {source}", file=sys.stderr)
        return 2

    temp_image = output_path.parent / ".roi_selector_frame.png"
    cv2.imwrite(str(temp_image), frame)
    try:
        launch_roi_selector(temp_image, output_path, initial_rois=rois)
    except Exception as exc:
        print(f"Failed to launch ROI GUI: {exc}", file=sys.stderr)
        return 4
    finally:
        if temp_image.exists():
            temp_image.unlink()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="OCR basketball scoreboard and push /api/state updates")
    parser.add_argument("--source", default="0", help="Video source: camera index (e.g. 0), video file, or image")
    parser.add_argument("--api", default="http://localhost:3000/api/state", help="Scoreboard API endpoint")
    parser.add_argument("--config", type=Path, help="Path to JSON config with normalized rois")
    parser.add_argument("--interval", type=float, default=0.15, help="Seconds between OCR reads")
    parser.add_argument("--http-timeout", type=float, default=0.25, help="POST timeout in seconds")
    parser.add_argument("--debug", action="store_true", help="Print extracted fields each iteration")
    parser.add_argument(
        "--roi-gui",
        action="store_true",
        help="Open interactive GUI to draw/select ROIs and save a config JSON",
    )
    parser.add_argument(
        "--roi-output",
        type=Path,
        default=Path("config.generated.json"),
        help="Output JSON path for --roi-gui mode",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    rois = cfg.get("rois", DEFAULT_ROIS)

    if args.roi_gui:
        return run_roi_gui(args.source, args.roi_output, rois)

    try:
        _ = pytesseract.get_tesseract_version()
    except TesseractNotFoundError:
        print("tesseract binary not found. Install Tesseract OCR and ensure it is on PATH.", file=sys.stderr)
        return 3

    source_path = Path(args.source)
    if source_path.exists() and source_path.suffix.lower() in IMAGE_SUFFIXES:
        frame = cv2.imread(str(source_path))
        if frame is None:
            print("Failed to read image", file=sys.stderr)
            return 1
        state = extract_state(frame, rois)
        if args.debug:
            print(state)
        if state:
            post_json(args.api, state, args.http_timeout)
        return 0

    cap = create_capture(args.source)
    if not cap.isOpened():
        print(f"Unable to open source: {args.source}", file=sys.stderr)
        return 2

    last_sent: Dict[str, Any] = {}
    next_run = 0.0

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                if source_path.exists():
                    break
                time.sleep(0.05)
                continue

            now = time.time()
            if now < next_run:
                continue
            next_run = now + args.interval

            extracted = extract_state(frame, rois)
            changed = should_push(extracted, last_sent)
            if args.debug and extracted:
                print(extracted)
            if changed:
                post_json(args.api, changed, args.http_timeout)
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
