"""DXF preview — xem ảnh gốc & đường cắt trước khi lưu."""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import messagebox

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageTk

from dxf_convert import (
    build_cut_mask,
    build_silhouette_mask,
    compute_match_score,
    physical_size_mm,
)

COLOR_BG = "#0c0c14"
COLOR_CARD = "#141424"
COLOR_TEXT = "#ffffff"
COLOR_MUTED = "#82829c"
COLOR_ACCENT = "#00d2ff"
COLOR_CUT = "#00e676"
COLOR_WARN = "#ff1744"
MAX_PREVIEW = 300


def _bgra_to_pil(img_bgra: np.ndarray) -> Image.Image:
    rgba = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2RGBA)
    return Image.fromarray(rgba)


def _fit_thumbnail(pil_img: Image.Image, max_size: int = MAX_PREVIEW) -> Image.Image:
    img = pil_img.copy()
    img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    return img


def _mm_to_px(
    points: list[tuple[float, float]],
    height_px: int,
    mm_per_px: float,
) -> list[tuple[float, float]]:
    return [
        (x / mm_per_px, height_px - y / mm_per_px)
        for x, y in points
    ]


def render_source_preview(img_bgra: np.ndarray, max_size: int = MAX_PREVIEW) -> Image.Image:
    """Ảnh gốc thu nhỏ."""
    pil = _bgra_to_pil(img_bgra)
    bg = Image.new("RGBA", pil.size, (20, 20, 30, 255))
    bg.paste(pil, mask=pil.split()[3] if pil.mode == "RGBA" else None)
    return _fit_thumbnail(bg.convert("RGB"))


def _draw_mismatch_contours(
    draw: ImageDraw.ImageDraw,
    mismatch_mask: np.ndarray,
    line_w: int,
    min_area: float = 6.0,
) -> None:
    """Vẽ contour đỏ quanh vùng silhouette ≠ đường cắt."""
    contours, _ = cv2.findContours(mismatch_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for cnt in contours:
        if cv2.contourArea(cnt) < min_area:
            continue
        pts = [(float(p[0]), float(p[1])) for p in cnt.reshape(-1, 2)]
        if len(pts) >= 2:
            draw.line(pts + [pts[0]], fill=(255, 23, 68), width=line_w)


def render_cut_preview(
    img_bgra: np.ndarray,
    polylines: list[list[tuple[float, float]]],
    width_px: int,
    height_px: int,
    mm_per_px: float,
    max_size: int = MAX_PREVIEW,
) -> tuple[Image.Image, float]:
    """Ảnh gốc mờ + đường cắt xanh + đường đỏ vùng không khớp."""
    silhouette = build_silhouette_mask(img_bgra)
    cut_mask = build_cut_mask(polylines, width_px, height_px, mm_per_px)
    match_pct, mismatch_mask = compute_match_score(silhouette, cut_mask)

    line_w = max(2, int(max(width_px, height_px) / 400))
    bgra_bg = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)
    dim = cv2.addWeighted(bgra_bg, 0.45, np.full_like(bgra_bg, 30), 0.55, 0)
    dim_pil = Image.fromarray(cv2.cvtColor(dim, cv2.COLOR_BGR2RGB))

    cut_only = Image.new("RGB", dim_pil.size, (20, 20, 30))
    cut_draw = ImageDraw.Draw(cut_only)
    for pts_mm in polylines:
        pts_px = _mm_to_px(pts_mm, height_px, mm_per_px)
        if len(pts_px) >= 2:
            cut_draw.line(pts_px + [pts_px[0]], fill=(0, 230, 118), width=line_w)

    _draw_mismatch_contours(cut_draw, mismatch_mask, line_w)

    result = Image.blend(dim_pil, cut_only, 0.55)
    return _fit_thumbnail(result), match_pct


def save_polylines_dxf(polylines: list, output_path: str) -> int:
    import ezdxf
    from dxf_convert import add_curve_to_modelspace

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for points in polylines:
        add_curve_to_modelspace(msp, points)
    doc.saveas(output_path)
    return len(polylines)


class DxfPreviewDialog(tk.Toplevel):
    """Modal xem trước trước khi lưu DXF."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        file_path: str,
        img_bgra: np.ndarray,
        polylines: list,
        width_px: int,
        height_px: int,
        dpi: tuple[float, float],
    ) -> None:
        super().__init__(parent)
        self.title("Xem trước DXF")
        self.configure(bg=COLOR_BG)
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)

        self._confirmed = False
        self._photos: list[ImageTk.PhotoImage] = []

        mm_per_px, w_mm, h_mm = physical_size_mm(width_px, height_px, dpi)
        n_pts = sum(len(p) for p in polylines)

        pad = 12
        hdr = tk.Frame(self, bg=COLOR_BG, padx=pad, pady=8)
        hdr.pack(fill=tk.X)
        tk.Label(
            hdr,
            text=f"Review: {os.path.basename(file_path)}",
            font=("Segoe UI", 10, "bold"),
            fg=COLOR_ACCENT,
            bg=COLOR_BG,
        ).pack(anchor="w")
        tk.Label(
            hdr,
            text=f"{width_px}×{height_px} px  ·  {w_mm:.1f}×{h_mm:.1f} mm  ·  "
                 f"{len(polylines)} contour  ·  {n_pts} điểm",
            font=("Segoe UI", 8),
            fg=COLOR_MUTED,
            bg=COLOR_BG,
        ).pack(anchor="w", pady=(2, 0))

        grid = tk.Frame(self, bg=COLOR_BG, padx=pad)
        grid.pack()

        src_img = render_source_preview(img_bgra)
        cut_img, match_pct = render_cut_preview(img_bgra, polylines, width_px, height_px, mm_per_px)
        match_color = COLOR_CUT if match_pct >= 98.0 else COLOR_WARN

        for col, (title, pil_img) in enumerate((
            ("Ảnh gốc", src_img),
            (f"Đường cắt DXF · {match_pct:.1f}% khớp", cut_img),
        )):
            frame = tk.Frame(grid, bg=COLOR_CARD, highlightbackground="#252538", highlightthickness=1)
            frame.grid(row=0, column=col, padx=(0 if col == 0 else 6, 0), pady=4)
            title_fg = match_color if col == 1 else COLOR_TEXT
            tk.Label(frame, text=title, font=("Segoe UI", 8, "bold"), fg=title_fg, bg=COLOR_CARD).pack(
                padx=8, pady=(6, 4),
            )
            photo = ImageTk.PhotoImage(pil_img)
            self._photos.append(photo)
            lbl = tk.Label(frame, image=photo, bg=COLOR_CARD)
            lbl.pack(padx=8, pady=(0, 8))

        tip = tk.Label(
            self,
            text="Xanh = đường cắt DXF · Đỏ = vùng không khớp silhouette. Hủy nếu méo hoặc thiếu chi tiết.",
            font=("Segoe UI", 7),
            fg=COLOR_WARN,
            bg=COLOR_BG,
            wraplength=420,
            justify=tk.LEFT,
            padx=pad,
        )
        tip.pack(anchor="w", pady=(4, 0))

        btns = tk.Frame(self, bg=COLOR_BG, padx=pad, pady=10)
        btns.pack(fill=tk.X)
        tk.Button(
            btns, text="Hủy", font=("Segoe UI", 8), bg=COLOR_CARD, fg=COLOR_MUTED,
            bd=0, padx=14, pady=5, cursor="hand2", command=self._cancel,
        ).pack(side=tk.RIGHT, padx=(6, 0))
        tk.Button(
            btns, text="Lưu DXF ✓", font=("Segoe UI", 8, "bold"), bg=COLOR_ACCENT, fg="#000",
            bd=0, padx=14, pady=5, cursor="hand2", command=self._confirm,
        ).pack(side=tk.RIGHT)

        self.update_idletasks()
        px = parent.winfo_rootx() + max(0, (parent.winfo_width() - self.winfo_width()) // 2)
        py = parent.winfo_rooty() + max(0, (parent.winfo_height() - self.winfo_height()) // 2)
        self.geometry(f"+{px}+{py}")

    def _confirm(self) -> None:
        self._confirmed = True
        self.destroy()

    def _cancel(self) -> None:
        self._confirmed = False
        self.destroy()

    @property
    def confirmed(self) -> bool:
        return self._confirmed


def confirm_dxf_preview(
    parent: tk.Misc,
    file_path: str,
    img_bgra: np.ndarray,
    polylines: list,
    width_px: int,
    height_px: int,
    dpi: tuple[float, float],
) -> bool:
    if not polylines:
        messagebox.showerror("DXF", "Không tìm thấy đường biên trong ảnh.", parent=parent)
        return False
    dlg = DxfPreviewDialog(
        parent,
        file_path=file_path,
        img_bgra=img_bgra,
        polylines=polylines,
        width_px=width_px,
        height_px=height_px,
        dpi=dpi,
    )
    parent.wait_window(dlg)
    return dlg.confirmed


def _dxf_filename(source_path: str) -> str:
    """Tên DXF — bỏ hậu tố _1/_2 từ ảnh patch (vd. stem_2.png → stem.dxf)."""
    stem = os.path.splitext(os.path.basename(source_path))[0]
    if stem.endswith("_1") or stem.endswith("_2"):
        stem = stem[:-2]
    return f"{stem}.dxf"


def desktop_dxf_path(source_path: str) -> str:
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    if not os.path.isdir(desktop):
        desktop = os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop")
    if not os.path.isdir(desktop):
        desktop = os.path.expanduser("~")
    return os.path.join(desktop, _dxf_filename(source_path))


def resolve_dxf_path(source_path: str, output_dir: str | None = None) -> str:
    """Lưu DXF vào folder đơn nếu có, không thì Desktop."""
    name = _dxf_filename(source_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        return os.path.join(output_dir, name)
    return desktop_dxf_path(source_path)