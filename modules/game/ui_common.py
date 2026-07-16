"""UI helpers — animation canvas, bet bar, sounds."""

from __future__ import annotations

import math
import random
import threading
import tkinter as tk
from typing import Callable

try:
    import winsound
    HAS_SND = True
except ImportError:
    HAS_SND = False

BET_PRESETS = (100, 500, 1000, 5000, 10000, 50000)


def beep(kind: str = "click") -> None:
    if not HAS_SND:
        return

    def run():
        try:
            if kind == "win":
                winsound.Beep(880, 80)
                winsound.Beep(1175, 120)
            elif kind == "lose":
                winsound.Beep(300, 200)
            elif kind == "roll":
                winsound.Beep(600, 30)
            else:
                winsound.Beep(700, 40)
        except Exception:
            pass

    threading.Thread(target=run, daemon=True).start()


class BetBar(tk.Frame):
    """Chọn mức cược + Tất tay."""

    def __init__(
        self,
        parent,
        get_points: Callable[[], int],
        *,
        bg="#0c0c14",
        card="#141424",
        accent="#00d2ff",
        danger="#ff1744",
        text="#fff",
        muted="#888",
    ) -> None:
        super().__init__(parent, bg=bg)
        self.get_points = get_points
        self.amount = tk.IntVar(value=1000)
        self.bg, self.card, self.accent = bg, card, accent
        tk.Label(self, text="Cược", font=("Segoe UI", 8), fg=muted, bg=bg).pack(side=tk.LEFT)
        for n in BET_PRESETS:
            tk.Button(
                self, text=self._fmt(n), font=("Segoe UI", 7, "bold"),
                bg=card, fg=accent, bd=0, padx=4, pady=1, cursor="hand2",
                command=lambda v=n: self._set(v),
            ).pack(side=tk.LEFT, padx=1)
        tk.Button(
            self, text="TẤT TAY", font=("Segoe UI", 7, "bold"),
            bg=danger, fg="#fff", bd=0, padx=6, pady=1, cursor="hand2",
            command=self.all_in,
        ).pack(side=tk.LEFT, padx=(4, 2))
        self.lbl = tk.Label(self, textvariable=self.amount, font=("Consolas", 9, "bold"), fg=accent, bg=bg)
        self.lbl.pack(side=tk.LEFT, padx=4)

    @staticmethod
    def _fmt(n: int) -> str:
        if n >= 1000:
            return f"{n // 1000}k"
        return str(n)

    def _set(self, v: int) -> None:
        pts = max(0, self.get_points())
        self.amount.set(min(v, pts) if pts else 0)
        beep("click")

    def all_in(self) -> None:
        self.amount.set(max(0, self.get_points()))
        beep("click")

    def value(self) -> int:
        pts = max(0, self.get_points())
        return max(0, min(int(self.amount.get()), pts))


class DiceCanvas(tk.Canvas):
    """Xúc xắc 3D-ish animation."""

    def __init__(self, parent, **kw):
        super().__init__(parent, width=kw.pop("width", 200), height=kw.pop("height", 70),
                         bg=kw.pop("bg", "#0a0a12"), highlightthickness=0, **kw)
        self._vals = [1, 1, 1]
        self._job = None
        self._on_done = None

    def show(self, vals: list[int]) -> None:
        self._vals = list(vals)
        self._draw_static()

    def animate(self, final: list[int], duration_ms: int = 1200, on_done=None) -> None:
        self._on_done = on_done
        self._final = list(final)
        self._frames = max(6, duration_ms // 55)
        self._i = 0
        self._tick()

    def _tick(self) -> None:
        if self._i >= self._frames:
            self._vals = self._final
            self._draw_static()
            if self._on_done:
                self._on_done(self._vals)
            return
        self._vals = [random.randint(1, 6) for _ in self._final]
        self._draw_static(shake=True)
        self._i += 1
        if self._i % 3 == 0:
            beep("roll")
        self._job = self.after(55, self._tick)

    def _draw_static(self, shake: bool = False) -> None:
        self.delete("all")
        w = int(self["width"])
        h = int(self["height"])
        n = len(self._vals)
        gap = 8
        size = min(56, (w - gap * (n + 1)) // n, h - 10)
        for i, v in enumerate(self._vals):
            x0 = gap + i * (size + gap) + (random.randint(-2, 2) if shake else 0)
            y0 = (h - size) // 2 + (random.randint(-2, 2) if shake else 0)
            self._die(x0, y0, size, v)

    def _die(self, x, y, s, val) -> None:
        self.create_rectangle(x, y, x + s, y + s, fill="#f5f5f5", outline="#333", width=2)
        # dots
        m = {
            1: [(0.5, 0.5)],
            2: [(0.28, 0.28), (0.72, 0.72)],
            3: [(0.28, 0.28), (0.5, 0.5), (0.72, 0.72)],
            4: [(0.28, 0.28), (0.72, 0.28), (0.28, 0.72), (0.72, 0.72)],
            5: [(0.28, 0.28), (0.72, 0.28), (0.5, 0.5), (0.28, 0.72), (0.72, 0.72)],
            6: [(0.28, 0.28), (0.72, 0.28), (0.28, 0.5), (0.72, 0.5), (0.28, 0.72), (0.72, 0.72)],
        }
        r = s * 0.08
        for px, py in m.get(val, m[1]):
            cx, cy = x + px * s, y + py * s
            self.create_oval(cx - r, cy - r, cx + r, cy + r, fill="#111", outline="")


class PulseLabel(tk.Label):
    def pulse(self, color="#00e676", times: int = 4) -> None:
        orig = self.cget("fg")

        def step(i=0):
            if i >= times * 2:
                self.configure(fg=orig)
                return
            self.configure(fg=color if i % 2 == 0 else orig)
            self.after(90, lambda: step(i + 1))

        step()


class ConfettiCanvas(tk.Canvas):
    def __init__(self, parent, **kw):
        super().__init__(parent, highlightthickness=0, **kw)
        self._parts = []
        self._job = None

    def burst(self, frames: int = 22) -> None:
        self.delete("all")
        w = self.winfo_width() or 200
        h = self.winfo_height() or 80
        self._parts = [
            {
                "x": random.random() * w,
                "y": -10,
                "vx": random.uniform(-1.2, 1.2),
                "vy": random.uniform(1.5, 3.5),
                "c": random.choice(["#ff0", "#0ff", "#f0f", "#0f0", "#ff6600", "#fff"]),
                "s": random.randint(3, 6),
            }
            for _ in range(16)
        ]
        self._frames = frames
        self._tick()

    def _tick(self) -> None:
        if self._frames <= 0:
            self.delete("all")
            return
        self.delete("all")
        for p in self._parts:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["vy"] += 0.15
            self.create_rectangle(p["x"], p["y"], p["x"] + p["s"], p["y"] + p["s"], fill=p["c"], outline="")
        self._frames -= 1
        self.after(40, self._tick)
