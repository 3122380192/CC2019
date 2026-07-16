"""Nhắc nghỉ mắt / đứng dậy — ca dài thân thiện Night mode."""

from __future__ import annotations

import time
import tkinter as tk
from typing import Callable


class BreakReminder:
    """Đếm phút làm việc; popup dịu khi đến giờ nghỉ."""

    def __init__(
        self,
        root: tk.Tk,
        *,
        interval_min: int = 50,
        break_min: int = 5,
        enabled: bool = True,
        on_tick: Callable[[int | None], None] | None = None,
        night_colors: bool = False,
    ) -> None:
        self.root = root
        self.interval_min = max(5, int(interval_min))
        self.break_min = max(1, int(break_min))
        self.enabled = bool(enabled)
        self.on_tick = on_tick
        self.night_colors = night_colors
        self._work_start = time.monotonic()
        self._paused = False
        self._popup: tk.Toplevel | None = None
        self._running = True
        self._snooze_until = 0.0
        self.root.after(30_000, self._loop)

    def configure(
        self,
        *,
        interval_min: int | None = None,
        break_min: int | None = None,
        enabled: bool | None = None,
    ) -> None:
        if interval_min is not None:
            self.interval_min = max(5, int(interval_min))
        if break_min is not None:
            self.break_min = max(1, int(break_min))
        if enabled is not None:
            self.enabled = bool(enabled)
            if self.enabled:
                self.reset()
            elif self.on_tick:
                self.on_tick(None)

    def reset(self) -> None:
        self._work_start = time.monotonic()
        self._snooze_until = 0.0
        self._close_popup()

    def remaining_minutes(self) -> int | None:
        if not self.enabled:
            return None
        if time.monotonic() < self._snooze_until:
            left = int((self._snooze_until - time.monotonic()) / 60) + 1
            return max(0, left)
        elapsed = (time.monotonic() - self._work_start) / 60.0
        left = int(self.interval_min - elapsed)
        return max(0, left)

    def _loop(self) -> None:
        if not self._running:
            return
        try:
            if self.enabled and not self._paused:
                rem = self.remaining_minutes()
                if self.on_tick:
                    self.on_tick(rem)
                if rem is not None and rem <= 0 and time.monotonic() >= self._snooze_until:
                    if self._popup is None:
                        self._show_popup()
            elif self.on_tick:
                self.on_tick(None)
        except Exception:
            pass
        self.root.after(30_000, self._loop)

    def _show_popup(self) -> None:
        if self._popup is not None:
            return
        bg = "#12121a" if self.night_colors else "#141424"
        card = "#1a1a28"
        accent = "#a78bfa" if self.night_colors else "#00d2ff"
        text = "#e8ecf4"
        muted = "#9aa0b0"

        win = tk.Toplevel(self.root)
        self._popup = win
        win.title("Nhắc nghỉ")
        win.configure(bg=bg)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        try:
            win.overrideredirect(True)
        except tk.TclError:
            pass

        frm = tk.Frame(win, bg=card, bd=1, highlightthickness=1, highlightbackground=accent)
        frm.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        tk.Label(
            frm, text="☕  Nghỉ mắt một chút",
            font=("Segoe UI", 11, "bold"), fg=accent, bg=card, padx=16, pady=10,
        ).pack()
        tk.Label(
            frm,
            text=f"Đã làm ~{self.interval_min} phút.\n"
                 f"Đứng dậy · nhìn xa · uống nước · nghỉ {self.break_min} phút.",
            font=("Segoe UI", 9), fg=text, bg=card, justify="center", padx=16,
        ).pack()
        tk.Label(
            frm, text="Ca đêm: giữ ánh sáng dịu, giảm mỏi mắt",
            font=("Segoe UI", 7), fg=muted, bg=card, pady=4,
        ).pack()

        btns = tk.Frame(frm, bg=card)
        btns.pack(pady=10)

        def done():
            self.reset()
            self._close_popup()

        def snooze5():
            self._snooze_until = time.monotonic() + 5 * 60
            self._close_popup()

        def skip_session():
            # lùi thêm 1 chu kỳ
            self._work_start = time.monotonic()
            self._close_popup()

        tk.Button(
            btns, text=f"✓ Đã nghỉ {self.break_min}p", font=("Segoe UI", 8, "bold"),
            bg=accent, fg="#000", bd=0, padx=10, pady=4, cursor="hand2", command=done,
        ).pack(side=tk.LEFT, padx=4)
        tk.Button(
            btns, text="Snooze 5p", font=("Segoe UI", 8),
            bg=bg, fg=text, bd=0, padx=8, pady=4, cursor="hand2", command=snooze5,
        ).pack(side=tk.LEFT, padx=4)
        tk.Button(
            btns, text="Làm tiếp", font=("Segoe UI", 8),
            bg=bg, fg=muted, bd=0, padx=8, pady=4, cursor="hand2", command=skip_session,
        ).pack(side=tk.LEFT, padx=4)

        win.update_idletasks()
        try:
            rw = self.root.winfo_rootx()
            rh = self.root.winfo_rooty()
            ww, wh = win.winfo_reqwidth(), win.winfo_reqheight()
            # góc dưới phải gần app
            x = rw + max(0, self.root.winfo_width() - ww - 12)
            y = rh + max(0, self.root.winfo_height() - wh - 12)
            win.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass

    def _close_popup(self) -> None:
        if self._popup is not None:
            try:
                self._popup.destroy()
            except tk.TclError:
                pass
            self._popup = None

    def stop(self) -> None:
        self._running = False
        self._close_popup()
