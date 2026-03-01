#!/usr/bin/env python3
"""GUI-first Basketball scoreboard OCR app.

This module provides a desktop app that lets users configure source/API/ROIs and
run OCR without command-line usage.
"""

from __future__ import annotations

import json
import re
import sys
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable, Dict, Optional
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

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


@dataclass
class OCRField:
    whitelist: str
    psm: int = 7


OCR_FIELDS: Dict[str, OCRField] = {
    "homeScore": OCRField("0123456789", 8),
    "awayScore": OCRField("0123456789", 8),
    "gameClock": OCRField("0123456789:", 7),
    "shotClock": OCRField("0123456789", 8),
    "period": OCRField("QOT123456789", 8),
    "homeFouls": OCRField("0123456789", 8),
    "awayFouls": OCRField("0123456789", 8),
    "homeTimeouts": OCRField("0123456789", 8),
    "awayTimeouts": OCRField("0123456789", 8),
}


def load_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"rois": DEFAULT_ROIS}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("rois", DEFAULT_ROIS)
    return data


def save_config(path: Path, rois: Dict[str, list[float]]) -> None:
    path.write_text(json.dumps({"rois": rois}, indent=2) + "\n", encoding="utf-8")


def create_capture(source: str) -> cv2.VideoCapture:
    if source.isdigit():
        return cv2.VideoCapture(int(source))
    return cv2.VideoCapture(source)


def read_sample_frame(source: str) -> Optional[np.ndarray]:
    path = Path(source)
    if path.exists() and path.suffix.lower() in IMAGE_SUFFIXES:
        return cv2.imread(str(path))

    cap = create_capture(source)
    if not cap.isOpened():
        return None
    ok, frame = cap.read()
    cap.release()
    if not ok:
        return None
    return frame


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
    cfg = f"--oem 3 --psm {field.psm} -c tessedit_char_whitelist={field.whitelist}"
    text = pytesseract.image_to_string(img, config=cfg)
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


def parse_int(text: str, low: int, high: int) -> Optional[int]:
    m = re.search(r"\d+", text)
    if not m:
        return None
    val = int(m.group(0))
    if val < low or val > high:
        return None
    return val


def parse_period(text: str) -> Optional[str]:
    t = text.replace("0", "O")
    if t in {"Q1", "Q2", "Q3", "Q4", "OT", "2OT"}:
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
        field = OCR_FIELDS.get(key)
        if field is None:
            continue
        roi = roi_pixels(frame, roi_norm)
        if roi.size == 0:
            continue
        text = ocr_text(preprocess(roi), field)
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


class OCRRunner:
    def __init__(
        self,
        source: str,
        api_url: str,
        rois: Dict[str, list[float]],
        interval: float,
        http_timeout: float,
        on_update: Callable[[Dict[str, Any]], None],
        on_status: Callable[[str], None],
    ) -> None:
        self.source = source
        self.api_url = api_url
        self.rois = rois
        self.interval = interval
        self.http_timeout = http_timeout
        self.on_update = on_update
        self.on_status = on_status

        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)

    def _run(self) -> None:
        source_path = Path(self.source)
        is_image = source_path.exists() and source_path.suffix.lower() in IMAGE_SUFFIXES

        if is_image:
            frame = cv2.imread(str(source_path))
            if frame is None:
                self.on_status("Failed to read image source.")
                return
            self._process_frame(frame, {})
            self.on_status("Processed single image.")
            return

        cap = create_capture(self.source)
        if not cap.isOpened():
            self.on_status(f"Unable to open source: {self.source}")
            return

        last_sent: Dict[str, Any] = {}
        self.on_status("OCR running...")
        next_run = 0.0
        try:
            while not self.stop_event.is_set():
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.05)
                    continue
                now = time.time()
                if now < next_run:
                    continue
                next_run = now + self.interval
                self._process_frame(frame, last_sent)
        finally:
            cap.release()
            self.on_status("OCR stopped.")

    def _process_frame(self, frame: np.ndarray, last_sent: Dict[str, Any]) -> None:
        extracted = extract_state(frame, self.rois)
        changed = {k: v for k, v in extracted.items() if last_sent.get(k) != v}
        if changed:
            last_sent.update(changed)
            post_json(self.api_url, changed, self.http_timeout)
            self.on_update(changed)


class ScoreboardOCRApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Scoreboard OCR - GUI")
        self.root.geometry("760x560")

        self.config_path = Path("config.example.json")
        self.rois: Dict[str, list[float]] = DEFAULT_ROIS.copy()
        self.runner: Optional[OCRRunner] = None

        self.source_var = tk.StringVar(value="0")
        self.api_var = tk.StringVar(value="http://localhost:3000/api/state")
        self.interval_var = tk.StringVar(value="0.15")
        self.timeout_var = tk.StringVar(value="0.25")
        self.config_var = tk.StringVar(value=str(self.config_path))
        self.status_var = tk.StringVar(value="Ready")

        self._build_ui()
        self._load_config_if_exists()

    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 6}

        frm = ttk.Frame(self.root)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Video/Image Source (camera index, file path, or URL):").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.source_var, width=62).grid(row=1, column=0, sticky="we", **pad)
        ttk.Button(frm, text="Browse File", command=self._browse_source).grid(row=1, column=1, sticky="e", **pad)

        ttk.Label(frm, text="BasketballScoreboard API URL:").grid(row=2, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.api_var, width=62).grid(row=3, column=0, columnspan=2, sticky="we", **pad)

        opts = ttk.Frame(frm)
        opts.grid(row=4, column=0, columnspan=2, sticky="we", **pad)
        ttk.Label(opts, text="OCR Interval (sec):").grid(row=0, column=0, sticky="w")
        ttk.Entry(opts, textvariable=self.interval_var, width=10).grid(row=0, column=1, padx=(6, 20))
        ttk.Label(opts, text="HTTP Timeout (sec):").grid(row=0, column=2, sticky="w")
        ttk.Entry(opts, textvariable=self.timeout_var, width=10).grid(row=0, column=3, padx=(6, 0))

        cfg = ttk.LabelFrame(frm, text="ROI Configuration")
        cfg.grid(row=5, column=0, columnspan=2, sticky="we", **pad)
        ttk.Entry(cfg, textvariable=self.config_var, width=58).grid(row=0, column=0, sticky="we", padx=8, pady=8)
        ttk.Button(cfg, text="Browse", command=self._browse_config).grid(row=0, column=1, padx=6)
        ttk.Button(cfg, text="Load", command=self._load_config).grid(row=0, column=2, padx=6)
        ttk.Button(cfg, text="Save", command=self._save_config).grid(row=0, column=3, padx=6)
        ttk.Button(cfg, text="Edit ROIs", command=self._edit_rois).grid(row=0, column=4, padx=6)

        controls = ttk.Frame(frm)
        controls.grid(row=6, column=0, columnspan=2, sticky="we", **pad)
        ttk.Button(controls, text="Start OCR", command=self._start).pack(side="left", padx=6)
        ttk.Button(controls, text="Stop OCR", command=self._stop).pack(side="left", padx=6)

        output = ttk.LabelFrame(frm, text="Live Updates")
        output.grid(row=7, column=0, columnspan=2, sticky="nsew", **pad)
        self.log = tk.Text(output, height=14, wrap="word")
        self.log.pack(fill="both", expand=True, padx=8, pady=8)

        ttk.Label(frm, textvariable=self.status_var).grid(row=8, column=0, columnspan=2, sticky="w", **pad)

        frm.columnconfigure(0, weight=1)
        frm.rowconfigure(7, weight=1)

    def _append_log(self, message: str) -> None:
        self.log.insert("end", message + "\n")
        self.log.see("end")

    def _set_status(self, message: str) -> None:
        self.root.after(0, lambda: self.status_var.set(message))

    def _on_update(self, changed: Dict[str, Any]) -> None:
        self.root.after(0, lambda: self._append_log(json.dumps(changed)))

    def _load_config_if_exists(self) -> None:
        if Path(self.config_var.get()).exists():
            self._load_config()

    def _browse_source(self) -> None:
        path = filedialog.askopenfilename(title="Choose video/image source")
        if path:
            self.source_var.set(path)

    def _browse_config(self) -> None:
        path = filedialog.askopenfilename(title="Choose ROI config JSON", filetypes=[("JSON files", "*.json")])
        if path:
            self.config_var.set(path)

    def _load_config(self) -> None:
        try:
            cfg = load_config(Path(self.config_var.get()))
            self.rois = cfg.get("rois", DEFAULT_ROIS)
            self._set_status(f"Loaded ROI config: {self.config_var.get()}")
        except Exception as exc:
            messagebox.showerror("Config Error", f"Could not load config:\n{exc}")

    def _save_config(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save ROI config",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
            initialfile=Path(self.config_var.get()).name,
        )
        if not path:
            return
        try:
            save_config(Path(path), self.rois)
            self.config_var.set(path)
            self._set_status(f"Saved ROI config: {path}")
        except Exception as exc:
            messagebox.showerror("Save Error", f"Could not save config:\n{exc}")

    def _edit_rois(self) -> None:
        frame = read_sample_frame(self.source_var.get())
        if frame is None:
            messagebox.showerror("Source Error", "Could not read a frame from the selected source.")
            return

        temp = Path(".roi_editor_sample.png")
        cv2.imwrite(str(temp), frame)
        out_path = Path(self.config_var.get())
        try:
            launch_roi_selector(temp, out_path, self.rois)
            if out_path.exists():
                self.rois = load_config(out_path).get("rois", DEFAULT_ROIS)
                self._set_status(f"ROI updated: {out_path}")
        except Exception as exc:
            messagebox.showerror("ROI GUI Error", f"Failed to open ROI editor:\n{exc}")
        finally:
            if temp.exists():
                temp.unlink()

    def _start(self) -> None:
        if self.runner is not None:
            messagebox.showinfo("OCR", "OCR is already running.")
            return

        try:
            interval = float(self.interval_var.get())
            timeout = float(self.timeout_var.get())
        except ValueError:
            messagebox.showerror("Input Error", "Interval and timeout must be numeric values.")
            return

        try:
            _ = pytesseract.get_tesseract_version()
        except TesseractNotFoundError:
            messagebox.showerror("Missing Dependency", "Tesseract binary not found. Install Tesseract OCR.")
            return

        self.runner = OCRRunner(
            source=self.source_var.get(),
            api_url=self.api_var.get(),
            rois=self.rois,
            interval=max(0.02, interval),
            http_timeout=max(0.05, timeout),
            on_update=self._on_update,
            on_status=self._set_status,
        )
        self.runner.start()
        self._set_status("Starting OCR...")

    def _stop(self) -> None:
        if self.runner is None:
            return
        self.runner.stop()
        self.runner = None
        self._set_status("Stopped")

    def run(self) -> None:
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self) -> None:
        self._stop()
        self.root.destroy()


def main() -> int:
    try:
        app = ScoreboardOCRApp()
    except tk.TclError as exc:
        print(f"GUI could not start: {exc}", file=sys.stderr)
        return 2
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
