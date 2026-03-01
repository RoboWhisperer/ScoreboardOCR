#!/usr/bin/env python3
"""Interactive ROI selector GUI for scoreboard OCR fields."""

from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Dict, Optional

from PIL import Image, ImageTk

FIELD_ORDER = [
    "homeScore",
    "awayScore",
    "gameClock",
    "shotClock",
    "period",
    "homeFouls",
    "awayFouls",
    "homeTimeouts",
    "awayTimeouts",
]


class ROISelectorApp:
    def __init__(self, image_path: Path, output_path: Path, initial_rois: Optional[Dict[str, list[float]]] = None) -> None:
        self.image_path = image_path
        self.output_path = output_path
        self.initial_rois = initial_rois or {}

        self.root = tk.Tk()
        self.root.title("Scoreboard ROI Selector")

        self.image = Image.open(self.image_path).convert("RGB")
        self.width, self.height = self.image.size
        self.tk_image = ImageTk.PhotoImage(self.image)

        self.current_field = tk.StringVar(value=FIELD_ORDER[0])
        self.rois: Dict[str, list[float]] = dict(self.initial_rois)

        self.start_x = 0
        self.start_y = 0
        self.active_rect: Optional[int] = None

        self._build_ui()
        self._draw_saved_rois()

    def _build_ui(self) -> None:
        top = ttk.Frame(self.root)
        top.pack(fill="x", padx=10, pady=6)

        ttk.Label(top, text="Field:").pack(side="left")
        selector = ttk.Combobox(top, values=FIELD_ORDER, textvariable=self.current_field, width=16, state="readonly")
        selector.pack(side="left", padx=6)

        ttk.Button(top, text="Clear Selected", command=self._clear_selected).pack(side="left", padx=6)
        ttk.Button(top, text="Clear All", command=self._clear_all).pack(side="left", padx=6)
        ttk.Button(top, text="Save", command=self._save).pack(side="right")

        help_text = (
            "Draw a rectangle for the selected field. Existing field rectangles are shown in green; "
            "selected field is yellow."
        )
        ttk.Label(self.root, text=help_text).pack(fill="x", padx=10)

        self.canvas = tk.Canvas(self.root, width=self.width, height=self.height, cursor="crosshair")
        self.canvas.pack(padx=10, pady=8)
        self.canvas.create_image(0, 0, image=self.tk_image, anchor="nw")
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

        self.status = ttk.Label(self.root, text=self._status_text())
        self.status.pack(fill="x", padx=10, pady=(0, 8))

    def _status_text(self) -> str:
        completed = sum(1 for key in FIELD_ORDER if key in self.rois)
        return f"Configured {completed}/{len(FIELD_ORDER)} fields"

    def _norm_rect(self, x1: int, y1: int, x2: int, y2: int) -> list[float]:
        left, right = sorted((max(0, x1), min(self.width, x2)))
        top, bottom = sorted((max(0, y1), min(self.height, y2)))
        w = max(0, right - left)
        h = max(0, bottom - top)
        return [left / self.width, top / self.height, w / self.width, h / self.height]

    def _draw_saved_rois(self) -> None:
        self.canvas.delete("roi")
        for field, roi in self.rois.items():
            x = int(roi[0] * self.width)
            y = int(roi[1] * self.height)
            w = int(roi[2] * self.width)
            h = int(roi[3] * self.height)
            color = "yellow" if field == self.current_field.get() else "lime"
            self.canvas.create_rectangle(x, y, x + w, y + h, outline=color, width=2, tags="roi")
            self.canvas.create_text(x + 4, y + 4, anchor="nw", text=field, fill=color, tags="roi")
        self.status.config(text=self._status_text())

    def _on_press(self, event: tk.Event) -> None:
        self.start_x, self.start_y = event.x, event.y
        if self.active_rect:
            self.canvas.delete(self.active_rect)
            self.active_rect = None

    def _on_drag(self, event: tk.Event) -> None:
        if self.active_rect:
            self.canvas.delete(self.active_rect)
        self.active_rect = self.canvas.create_rectangle(
            self.start_x,
            self.start_y,
            event.x,
            event.y,
            outline="orange",
            width=2,
            dash=(4, 2),
        )

    def _on_release(self, event: tk.Event) -> None:
        if self.active_rect:
            self.canvas.delete(self.active_rect)
            self.active_rect = None

        roi = self._norm_rect(self.start_x, self.start_y, event.x, event.y)
        if roi[2] < 0.002 or roi[3] < 0.002:
            return
        self.rois[self.current_field.get()] = roi
        self._draw_saved_rois()

    def _clear_selected(self) -> None:
        field = self.current_field.get()
        self.rois.pop(field, None)
        self._draw_saved_rois()

    def _clear_all(self) -> None:
        self.rois.clear()
        self._draw_saved_rois()

    def _save(self) -> None:
        payload = {"rois": {k: self.rois[k] for k in FIELD_ORDER if k in self.rois}}
        self.output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        messagebox.showinfo("Saved", f"Wrote ROI config to {self.output_path}")

    def run(self) -> None:
        self.current_field.trace_add("write", lambda *_: self._draw_saved_rois())
        self.root.mainloop()


def launch_roi_selector(image_path: Path, output_path: Path, initial_rois: Optional[Dict[str, list[float]]] = None) -> None:
    app = ROISelectorApp(image_path=image_path, output_path=output_path, initial_rois=initial_rois)
    app.run()
