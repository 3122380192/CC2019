"""Thanh theo dõi gọn: Wilcom · BN weather · FPS/CPU · đơn ngày."""

from __future__ import annotations

import os
import socket
import subprocess
import threading
import time
import tkinter as tk

try:
    import psutil
except ImportError:
    psutil = None

COLOR_BG = "#0c0c14"
COLOR_MUTED = "#82829c"
COLOR_CSV = "#a78bfa"
COLOR_SUCCESS = "#00e676"
COLOR_DANGER = "#ff5252"
COLOR_GOLD = "#fbbf24"
COLOR_WX = "#7dd3fc"

WILCOM_PROC = (
    "es.exe",
    "wilcomshellengine.exe",
    "wilcomproductservice.exe",
    "embroidery studio.exe",
)


def _wilcom_running() -> bool:
    if psutil:
        try:
            names = {n.lower() for n in WILCOM_PROC}
            for p in psutil.process_iter(["name"]):
                try:
                    nm = (p.info.get("name") or "").lower()
                    if nm in names or "wilcom" in nm:
                        return True
                except (psutil.Error, TypeError):
                    continue
        except Exception:
            pass
    try:
        r = subprocess.run(
            'tasklist /NH /FI "IMAGENAME eq ES.EXE"',
            shell=True, capture_output=True, text=True, timeout=2,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if "es.exe" in (r.stdout or "").lower():
            return True
    except Exception:
        pass
    return False


class SysMonitorBar:
    def __init__(
        self,
        parent: tk.Misc,
        root: tk.Tk,
        *,
        ping_host: str = "127.0.0.1",
        ping_port: int = 5000,
        bg: str = COLOR_BG,
    ) -> None:
        self.root = root
        self._ping_host = ping_host
        self._ping_port = ping_port
        self._running = True
        self._ping_ms: float | None = None
        self._frames = 0
        self._fps = 0
        self._last_fps_ts = time.monotonic()
        self._cpu = 0.0
        self._ram = 0.0
        self._disk = 0.0
        self._wilcom = False
        self._break_left_min: int | None = None
        self._music_now = ""
        self._weather_txt = ""
        self._daily = "—"

        wrap = tk.Frame(parent, bg=bg, bd=0, highlightthickness=0)
        wrap.pack(side=tk.RIGHT, padx=(2, 0))
        self._bg = bg

        # Một hàng gọn — mượt, ít chiếm chỗ
        row = tk.Frame(wrap, bg=bg)
        row.pack(anchor="e")

        self.wilcom_dot = tk.Label(row, text="●", font=("Segoe UI", 6), fg=COLOR_MUTED, bg=bg)
        self.wilcom_dot.pack(side=tk.LEFT)
        self.wilcom_lbl = tk.Label(row, text="W", font=("Consolas", 6), fg=COLOR_MUTED, bg=bg)
        self.wilcom_lbl.pack(side=tk.LEFT, padx=(0, 3))

        self.weather_var = tk.StringVar(value="")
        self.weather_lbl = tk.Label(
            row, textvariable=self.weather_var, font=("Segoe UI", 6),
            fg=COLOR_WX, bg=bg,
        )
        self.weather_lbl.pack(side=tk.LEFT, padx=(0, 3))

        self.var = tk.StringVar(value="")
        tk.Label(
            row, textvariable=self.var, font=("Consolas", 6),
            fg=COLOR_MUTED, bg=bg, anchor="e",
        ).pack(side=tk.LEFT)

        self.extra_var = tk.StringVar(value="")
        self.extra_lbl = tk.Label(
            row, textvariable=self.extra_var, font=("Segoe UI", 5),
            fg=COLOR_GOLD, bg=bg,
        )
        self.extra_lbl.pack(side=tk.LEFT, padx=(3, 0))

        # daily gộp vào extra — giữ API set_daily_summary
        self.daily_var = tk.StringVar(value="")

        if psutil:
            try:
                psutil.cpu_percent(interval=None)
            except Exception:
                pass

        self._tick_ui()
        threading.Thread(target=self._ping_loop, daemon=True).start()
        threading.Thread(target=self._stats_loop, daemon=True).start()
        threading.Thread(target=self._wilcom_loop, daemon=True).start()

    def set_daily_summary(self, orders: int, products: int, csv_files: int = 0) -> None:
        extra = f"·{csv_files}csv" if csv_files else ""
        self._daily = f"{orders}đ·{products}sp{extra}"
        self.daily_var.set(self._daily)
        self._update_extra()

    def set_break_remaining(self, minutes: int | None) -> None:
        self._break_left_min = minutes
        self._update_extra()

    def set_music_now(self, title: str) -> None:
        self._music_now = (title or "")[:22]
        self._update_extra()

    def set_weather_summary(self, text: str) -> None:
        self._weather_txt = (text or "")[:28]
        try:
            self.weather_var.set(self._weather_txt)
        except tk.TclError:
            pass

    def _update_extra(self) -> None:
        parts = []
        if self._daily:
            parts.append(self._daily)
        if self._break_left_min is not None:
            parts.append("☕!" if self._break_left_min <= 0 else f"☕{self._break_left_min}p")
        if self._music_now:
            parts.append(f"♪{self._music_now}")
        try:
            self.extra_var.set(" ".join(parts))
        except tk.TclError:
            pass

    def is_wilcom_alive(self) -> bool:
        return bool(self._wilcom)

    def _disk_pct(self) -> float:
        if not psutil:
            return 0.0
        drive = os.environ.get("SystemDrive", "C:") + "\\"
        try:
            return float(psutil.disk_usage(drive).percent)
        except Exception:
            return 0.0

    def _tcp_ping(self) -> float | None:
        t0 = time.perf_counter()
        try:
            with socket.create_connection((self._ping_host, self._ping_port), timeout=0.4):
                pass
            return (time.perf_counter() - t0) * 1000.0
        except OSError:
            return None

    def _ping_loop(self) -> None:
        while self._running:
            self._ping_ms = self._tcp_ping()
            time.sleep(3.0)

    def _stats_loop(self) -> None:
        while self._running:
            if psutil:
                try:
                    self._cpu = float(psutil.cpu_percent(interval=0.8))
                    self._ram = float(psutil.virtual_memory().percent)
                    self._disk = self._disk_pct()
                except Exception:
                    pass
            time.sleep(1.5)

    def _wilcom_loop(self) -> None:
        while self._running:
            try:
                self._wilcom = _wilcom_running()
            except Exception:
                self._wilcom = False
            time.sleep(4.0)

    def _apply_wilcom_ui(self) -> None:
        if self._wilcom:
            self.wilcom_dot.config(fg=COLOR_SUCCESS)
            self.wilcom_lbl.config(text="W", fg=COLOR_SUCCESS)
        else:
            self.wilcom_dot.config(fg=COLOR_DANGER)
            self.wilcom_lbl.config(text="W", fg=COLOR_MUTED)

    def _tick_ui(self) -> None:
        if not self._running:
            return
        self._frames += 1
        now = time.monotonic()
        if now - self._last_fps_ts >= 1.0:
            self._fps = self._frames
            self._frames = 0
            self._last_fps_ts = now
            ping = f"{self._ping_ms:.0f}" if self._ping_ms is not None else "—"
            self.var.set(
                f"{self._fps}f {ping}ms C{self._cpu:.0f}% R{self._ram:.0f}%"
            )
            try:
                self._apply_wilcom_ui()
            except tk.TclError:
                pass
        # ~6 FPS UI — nhẹ CPU
        self.root.after(160, self._tick_ui)

    def stop(self) -> None:
        self._running = False
