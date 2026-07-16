"""Xem ảnh tab Sản xuất — không viền, không nền, zoom/pan mượt."""

from __future__ import annotations

import io
import os
import tkinter as tk
from typing import Sequence

# Màu chroma-key: vùng trống trong suốt trên Windows (hiếm gặp trong ảnh)
_KEY = "#010203"
_ZOOM_MIN = 0.05
_ZOOM_MAX = 12.0
_ZOOM_STEP = 1.15


class ImageLightbox:
    """Cửa sổ xem ảnh: borderless, chỉ hiện pixel ảnh, lăn zoom · kéo pan · Esc tắt."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.win: tk.Toplevel | None = None
        self._photo = None
        self._pil = None          # ảnh gốc (RGB)
        self._zoom = 1.0
        self._paths: list[str] = []
        self._idx = 0
        self._canvas: tk.Canvas | None = None
        self._img_id = None
        self._drag = None
        self._ox = 0.0
        self._oy = 0.0
        self._redraw_job: str | None = None
        self._title = "Ảnh"
        self._sw = 1920
        self._sh = 1080
        self._hint_id = None
        self._hint_job: str | None = None
        self._win_x: int | None = None
        self._win_y: int | None = None
        self._last_ww = 0
        self._last_wh = 0
        # Tk PhotoImage an toàn dưới ~8k/cạnh
        self._max_px = 8000

    # ── public API ──────────────────────────────────────────────
    def show_bytes(self, data: bytes, title: str = "Ảnh") -> None:
        try:
            from PIL import Image

            img = Image.open(io.BytesIO(data)).convert("RGB")
            img.load()
        except Exception:
            return
        self._paths = []
        self._idx = 0
        self._title = title or "Ảnh"
        self._present(img, recenter=True)

    def show_path(self, path: str) -> None:
        if not path or not os.path.isfile(path):
            return
        self.show_paths([path], 0)

    def show_paths(self, paths: Sequence[str], index: int = 0) -> None:
        paths = [p for p in paths if p and os.path.isfile(p)]
        if not paths:
            return
        self._paths = list(paths)
        self._idx = max(0, min(index, len(paths) - 1))
        self._load_index(recenter=True)

    def close(self) -> None:
        self._cancel_jobs()
        if self.win:
            try:
                self.win.destroy()
            except tk.TclError:
                pass
        self.win = None
        self._canvas = None
        self._photo = None
        self._pil = None
        self._img_id = None
        self._hint_id = None
        self._win_x = None
        self._win_y = None
        self._last_ww = 0
        self._last_wh = 0

    # ── load / present ──────────────────────────────────────────
    def _load_index(self, *, recenter: bool = False) -> None:
        if not self._paths:
            return
        path = self._paths[self._idx]
        try:
            from PIL import Image

            img = Image.open(path).convert("RGB")
            img.load()
        except Exception:
            return
        name = os.path.basename(path)
        if len(self._paths) > 1:
            self._title = f"{name}  ({self._idx + 1}/{len(self._paths)})"
        else:
            self._title = name
        self._present(img, recenter=recenter)

    def _present(self, pil_img, *, recenter: bool = False) -> None:
        self._pil = pil_img
        self._ox = 0.0
        self._oy = 0.0
        if recenter:
            self._win_x = None
            self._win_y = None
        self._ensure_window()
        self._fit_to_screen()
        self._redraw(hq=True)
        self._flash_hint()
        try:
            if self.win:
                self.win.lift()
                self.win.focus_force()
        except tk.TclError:
            pass

    def _ensure_window(self) -> None:
        if self.win is not None:
            try:
                if self.win.winfo_exists():
                    return
            except tk.TclError:
                self.win = None

        win = tk.Toplevel(self.root)
        self.win = win
        win.withdraw()
        win.overrideredirect(True)  # không title bar / viền
        win.attributes("-topmost", True)
        try:
            self._sw = win.winfo_screenwidth()
            self._sh = win.winfo_screenheight()
        except tk.TclError:
            pass

        # Nền trong suốt (chỉ ảnh hiện) — Windows transparentcolor
        win.configure(bg=_KEY)
        try:
            win.wm_attributes("-transparentcolor", _KEY)
        except tk.TclError:
            win.configure(bg="#000000")

        self._canvas = tk.Canvas(
            win,
            bg=_KEY,
            highlightthickness=0,
            bd=0,
            cursor="fleur",
        )
        self._canvas.pack(fill=tk.BOTH, expand=True)

        c = self._canvas
        c.bind("<Button-1>", self._on_press)
        c.bind("<B1-Motion>", self._on_drag)
        c.bind("<ButtonRelease-1>", self._on_release)
        c.bind("<Double-Button-1>", lambda _e: self.close())
        c.bind("<Button-3>", lambda _e: self.close())
        c.bind("<MouseWheel>", self._on_wheel)
        c.bind("<Button-4>", lambda e: self._zoom_at(e.x, e.y, +1))
        c.bind("<Button-5>", lambda e: self._zoom_at(e.x, e.y, -1))
        win.bind("<Escape>", lambda _e: self.close())
        win.bind("<Left>", lambda _e: self._nav(-1))
        win.bind("<Right>", lambda _e: self._nav(1))
        win.bind("<plus>", lambda _e: self._zoom_center(+1))
        win.bind("<minus>", lambda _e: self._zoom_center(-1))
        win.bind("<equal>", lambda _e: self._zoom_center(+1))
        win.bind("<KP_Add>", lambda _e: self._zoom_center(+1))
        win.bind("<KP_Subtract>", lambda _e: self._zoom_center(-1))
        win.bind("<Home>", lambda _e: self._reset_view())
        win.bind("<r>", lambda _e: self._reset_view())
        win.bind("<R>", lambda _e: self._reset_view())
        win.protocol("WM_DELETE_WINDOW", self.close)

        win.deiconify()

    def _max_view(self) -> tuple[int, int]:
        return max(200, int(self._sw * 0.96)), max(200, int(self._sh * 0.94))

    def _fit_to_screen(self) -> None:
        if not self._pil:
            return
        iw, ih = self._pil.size
        mw, mh = self._max_view()
        fit = min(mw / iw, mh / ih, 1.0)
        # không vượt giới hạn PhotoImage
        if iw * fit > self._max_px or ih * fit > self._max_px:
            fit = min(fit, self._max_px / max(iw, 1), self._max_px / max(ih, 1))
        self._zoom = max(_ZOOM_MIN, fit)
        self._ox = 0.0
        self._oy = 0.0

    def _reset_view(self) -> None:
        self._fit_to_screen()
        self._redraw(hq=True)
        self._flash_hint("fit")

    # ── draw ────────────────────────────────────────────────────
    def _display_size(self) -> tuple[int, int]:
        if not self._pil:
            return 1, 1
        iw, ih = self._pil.size
        nw = max(1, int(iw * self._zoom))
        nh = max(1, int(ih * self._zoom))
        if nw > self._max_px or nh > self._max_px:
            s = min(self._max_px / nw, self._max_px / nh)
            nw = max(1, int(nw * s))
            nh = max(1, int(nh * s))
            self._zoom = nw / max(iw, 1)
        return nw, nh

    def _apply_geometry(self, nw: int, nh: int) -> tuple[int, int]:
        """Đặt size cửa sổ = kích thước ảnh (clamp màn hình). Trả (ww, wh)."""
        mw, mh = self._max_view()
        ww = min(nw, mw)
        wh = min(nh, mh)

        if self._win_x is None or self._win_y is None:
            x = max(0, (self._sw - ww) // 2)
            y = max(0, (self._sh - wh) // 2)
        else:
            # giữ tâm cửa sổ cũ khi zoom đổi size
            old_cx = self._win_x + max(self._last_ww, 1) // 2
            old_cy = self._win_y + max(self._last_wh, 1) // 2
            x = max(0, min(self._sw - ww, old_cx - ww // 2))
            y = max(0, min(self._sh - wh, old_cy - wh // 2))

        self._win_x, self._win_y = x, y
        self._last_ww, self._last_wh = ww, wh
        try:
            if self.win:
                self.win.geometry(f"{ww}x{wh}+{x}+{y}")
                if self._canvas:
                    self._canvas.configure(width=ww, height=wh)
        except tk.TclError:
            pass
        return ww, wh

    def _cancel_jobs(self) -> None:
        if self._redraw_job and self.win:
            try:
                self.win.after_cancel(self._redraw_job)
            except (tk.TclError, ValueError):
                pass
        self._redraw_job = None
        if self._hint_job and self.win:
            try:
                self.win.after_cancel(self._hint_job)
            except (tk.TclError, ValueError):
                pass
        self._hint_job = None

    def _clamp_pan(self, nw: int, nh: int, ww: int, wh: int) -> None:
        if nw > ww:
            max_ox = (nw - ww) / 2
            self._ox = max(-max_ox, min(max_ox, self._ox))
        else:
            self._ox = 0.0
        if nh > wh:
            max_oy = (nh - wh) / 2
            self._oy = max(-max_oy, min(max_oy, self._oy))
        else:
            self._oy = 0.0

    def _redraw(self, *, hq: bool = False) -> None:
        if not self._pil or not self._canvas or not self.win:
            return
        from PIL import Image, ImageTk

        nw, nh = self._display_size()
        ww, wh = self._apply_geometry(nw, nh)
        self._clamp_pan(nw, nh, ww, wh)

        try:
            resample = Image.Resampling.LANCZOS if hq else Image.Resampling.BILINEAR
        except AttributeError:
            resample = Image.LANCZOS if hq else Image.BILINEAR

        try:
            resized = self._pil.resize((nw, nh), resample)
        except Exception:
            try:
                resized = self._pil.resize((nw, nh))
            except Exception:
                return

        try:
            self._photo = ImageTk.PhotoImage(resized)
        except Exception:
            # ảnh quá lớn cho Tk — hạ cấp
            s = 0.5
            try:
                resized = self._pil.resize(
                    (max(1, int(nw * s)), max(1, int(nh * s))), resample
                )
                self._photo = ImageTk.PhotoImage(resized)
                nw, nh = resized.size
                self._zoom = nw / max(self._pil.size[0], 1)
                ww, wh = self._apply_geometry(nw, nh)
            except Exception:
                return

        cx = ww / 2 + self._ox
        cy = wh / 2 + self._oy

        self._canvas.delete("img")
        self._img_id = self._canvas.create_image(
            cx, cy, image=self._photo, anchor="center", tags=("img",),
        )
        if self._hint_id:
            try:
                self._canvas.tag_raise(self._hint_id)
            except tk.TclError:
                pass

    def _schedule_hq(self) -> None:
        """Sau khi zoom/pan xong, vẽ lại LANCZOS."""
        if not self.win:
            return
        if self._redraw_job:
            try:
                self.win.after_cancel(self._redraw_job)
            except (tk.TclError, ValueError):
                pass
        self._redraw_job = self.win.after(80, lambda: self._redraw(hq=True))

    def _flash_hint(self, text: str | None = None) -> None:
        if not self._canvas:
            return
        if text is None:
            parts = ["lăn = zoom", "kéo = pan", "dbl·RMB·Esc = tắt"]
            if len(self._paths) > 1:
                parts.append("←→ = ảnh")
            text = " · ".join(parts)
        try:
            self._canvas.delete("hint")
        except tk.TclError:
            pass
        self._hint_id = self._canvas.create_text(
            8, 8,
            text=text,
            fill="#bbbbbb",
            font=("Segoe UI", 8),
            anchor="nw",
            tags=("hint",),
        )
        if self._hint_job and self.win:
            try:
                self.win.after_cancel(self._hint_job)
            except (tk.TclError, ValueError):
                pass

        def _hide():
            if self._canvas:
                try:
                    self._canvas.delete("hint")
                except tk.TclError:
                    pass
            self._hint_id = None
            self._hint_job = None

        if self.win:
            self._hint_job = self.win.after(1400, _hide)

    # ── zoom / pan ──────────────────────────────────────────────
    def _zoom_center(self, direction: int) -> None:
        if not self._canvas:
            return
        try:
            w = max(1, self._canvas.winfo_width())
            h = max(1, self._canvas.winfo_height())
        except tk.TclError:
            return
        self._zoom_at(w // 2, h // 2, direction)

    def _zoom_at(self, cx: int, cy: int, direction: int) -> None:
        if not self._pil or not self._canvas:
            return
        old = self._zoom
        factor = _ZOOM_STEP if direction > 0 else 1.0 / _ZOOM_STEP
        new = max(_ZOOM_MIN, min(_ZOOM_MAX, old * factor))
        if abs(new - old) < 1e-9:
            return

        try:
            ww = max(1, self._canvas.winfo_width())
            wh = max(1, self._canvas.winfo_height())
        except tk.TclError:
            ww = wh = 1
        dx = cx - (ww / 2 + self._ox)
        dy = cy - (wh / 2 + self._oy)
        scale = new / old
        self._ox = self._ox - dx * (scale - 1)
        self._oy = self._oy - dy * (scale - 1)
        self._zoom = new
        self._redraw(hq=False)
        self._schedule_hq()
        self._flash_hint(f"{self._zoom:.0%}")

    def _on_wheel(self, event) -> None:
        direction = 1 if event.delta > 0 else -1
        self._zoom_at(event.x, event.y, direction)

    def _on_press(self, event) -> None:
        self._drag = (event.x, event.y, self._ox, self._oy, False)

    def _on_drag(self, event) -> None:
        if not self._drag:
            return
        x0, y0, ox, oy, _ = self._drag
        dx, dy = event.x - x0, event.y - y0
        if abs(dx) + abs(dy) > 2:
            self._ox = ox + dx
            self._oy = oy + dy
            self._drag = (x0, y0, ox, oy, True)
            # pan: chỉ dịch image, không resize cửa sổ → nhanh
            self._pan_move()

    def _pan_move(self) -> None:
        if not self._pil or not self._canvas or not self._img_id:
            return
        nw, nh = self._display_size()
        ww = self._last_ww or max(1, self._canvas.winfo_width())
        wh = self._last_wh or max(1, self._canvas.winfo_height())
        self._clamp_pan(nw, nh, ww, wh)
        try:
            self._canvas.coords(self._img_id, ww / 2 + self._ox, wh / 2 + self._oy)
        except tk.TclError:
            self._redraw(hq=False)

    def _on_release(self, event) -> None:
        if self._drag and self._drag[4]:
            self._schedule_hq()
        self._drag = None

    def _nav(self, d: int) -> None:
        if len(self._paths) < 2:
            return
        self._idx = (self._idx + d) % len(self._paths)
        self._load_index(recenter=False)


def collect_images_in_folder(folder: str) -> list[str]:
    if not folder or not os.path.isdir(folder):
        return []
    exts = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff"}
    out = []
    try:
        for name in sorted(os.listdir(folder)):
            p = os.path.join(folder, name)
            if os.path.isfile(p) and os.path.splitext(name)[1].lower() in exts:
                out.append(p)
    except OSError:
        pass
    return out
