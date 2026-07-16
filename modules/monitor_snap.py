"""Multi-monitor snap — căn cửa sổ nửa trái/phải/góc trên từng màn hình."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Any


def list_monitors() -> list[dict[str, int]]:
    """Danh sách monitor Windows: [{x,y,w,h}, …]. Primary thường index 0."""
    monitors: list[dict[str, int]] = []

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    def _cb(hmon, hdc, lprc, data):
        r = lprc.contents
        monitors.append({
            "x": int(r.left),
            "y": int(r.top),
            "w": int(r.right - r.left),
            "h": int(r.bottom - r.top),
        })
        return 1

    try:
        MonitorEnumProc = ctypes.WINFUNCTYPE(
            ctypes.c_int,
            wintypes.HMONITOR,
            wintypes.HDC,
            ctypes.POINTER(RECT),
            wintypes.LPARAM,
        )
        ctypes.windll.user32.EnumDisplayMonitors(None, None, MonitorEnumProc(_cb), 0)
    except Exception:
        pass

    if not monitors:
        try:
            user32 = ctypes.windll.user32
            monitors.append({
                "x": 0, "y": 0,
                "w": int(user32.GetSystemMetrics(0)),
                "h": int(user32.GetSystemMetrics(1)),
            })
        except Exception:
            monitors.append({"x": 0, "y": 0, "w": 1920, "h": 1080})
    return monitors


def monitor_at_point(x: int, y: int, monitors: list[dict[str, int]] | None = None) -> dict[str, int]:
    mons = monitors or list_monitors()
    for m in mons:
        if m["x"] <= x < m["x"] + m["w"] and m["y"] <= y < m["y"] + m["h"]:
            return m
    return mons[0]


def snap_geometry(
    side: str,
    *,
    root_x: int = 0,
    root_y: int = 0,
    width: int | None = None,
    height: int | None = None,
    monitor_index: int | None = None,
    gap: int = 0,
) -> tuple[int, int, int, int]:
    """
    side: left | right | top | bottom | tl | tr | bl | br | center | full
    Trả về (w, h, x, y).
    """
    mons = list_monitors()
    if monitor_index is not None and 0 <= monitor_index < len(mons):
        m = mons[monitor_index]
    else:
        m = monitor_at_point(root_x + 20, root_y + 20, mons)

    mx, my, mw, mh = m["x"], m["y"], m["w"], m["h"]
    half_w = max(320, mw // 2 - gap)
    half_h = max(240, mh // 2 - gap)
    side = (side or "right").lower()

    if side == "left":
        return half_w, mh - gap * 2, mx + gap, my + gap
    if side == "right":
        return half_w, mh - gap * 2, mx + mw - half_w - gap, my + gap
    if side == "top":
        return mw - gap * 2, half_h, mx + gap, my + gap
    if side == "bottom":
        return mw - gap * 2, half_h, mx + gap, my + mh - half_h - gap
    if side == "tl":
        return half_w, half_h, mx + gap, my + gap
    if side == "tr":
        return half_w, half_h, mx + mw - half_w - gap, my + gap
    if side == "bl":
        return half_w, half_h, mx + gap, my + mh - half_h - gap
    if side == "br":
        return half_w, half_h, mx + mw - half_w - gap, my + mh - half_h - gap
    if side == "center":
        w = width or min(480, mw - 40)
        h = height or min(520, mh - 40)
        return w, h, mx + (mw - w) // 2, my + (mh - h) // 2
    if side == "full":
        return mw - gap * 2, mh - gap * 2, mx + gap, my + gap
    # default right half
    return half_w, mh - gap * 2, mx + mw - half_w - gap, my + gap


def apply_snap(root: Any, side: str, monitor_index: int | None = None) -> str:
    """Snap root window. Trả về mô tả ngắn."""
    try:
        root.update_idletasks()
        rx, ry = root.winfo_x(), root.winfo_y()
        w, h, x, y = snap_geometry(
            side, root_x=rx, root_y=ry,
            width=root.winfo_width(), height=root.winfo_height(),
            monitor_index=monitor_index,
        )
        root.geometry(f"{w}x{h}+{x}+{y}")
        mons = list_monitors()
        idx = monitor_index
        if idx is None:
            m = monitor_at_point(x + 10, y + 10, mons)
            idx = mons.index(m) if m in mons else 0
        return f"Snap {side} · màn {idx + 1}/{len(mons)}"
    except Exception as exc:
        return f"Snap lỗi: {exc}"


def cycle_monitor(root: Any, direction: int = 1) -> str:
    """Chuyển cửa sổ sang monitor kế (giữ kích thước tương đối)."""
    mons = list_monitors()
    if len(mons) < 2:
        return "Chỉ có 1 màn hình"
    try:
        root.update_idletasks()
        cx = root.winfo_x() + root.winfo_width() // 2
        cy = root.winfo_y() + root.winfo_height() // 2
        cur = monitor_at_point(cx, cy, mons)
        idx = mons.index(cur) if cur in mons else 0
        nxt = (idx + direction) % len(mons)
        m = mons[nxt]
        # map relative position
        rel_x = (root.winfo_x() - cur["x"]) / max(1, cur["w"])
        rel_y = (root.winfo_y() - cur["y"]) / max(1, cur["h"])
        nw = min(root.winfo_width(), m["w"] - 20)
        nh = min(root.winfo_height(), m["h"] - 20)
        nx = int(m["x"] + rel_x * m["w"])
        ny = int(m["y"] + rel_y * m["h"])
        nx = max(m["x"], min(nx, m["x"] + m["w"] - nw))
        ny = max(m["y"], min(ny, m["y"] + m["h"] - nh))
        root.geometry(f"{nw}x{nh}+{nx}+{ny}")
        return f"Chuyển màn {idx + 1} → {nxt + 1}"
    except Exception as exc:
        return f"Cycle monitor lỗi: {exc}"
