"""Apply spot channel W1 and export RGB TIFF matching Photoshop reference."""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime

import numpy as np
import tifffile
from PIL import Image

SPOT_CHANNEL_NAME = "W1"
SPOT_CMYK = (0, 100, 100, 0)
SPOT_SOLIDITY = 70
SPOT_CHANNEL_INDEX = 4

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".psd"}

def _bundle_dir() -> str:
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


_REFERENCE_CANDIDATES = (
    os.path.join(os.path.expanduser("~"), "Desktop", "1.tif"),
    os.path.join(_bundle_dir(), "agent-tools", "test_out", "1.tif"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent-tools", "test_out", "1.tif"),
)


def _desktop_dir() -> str:
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    if os.path.isdir(desktop):
        return desktop
    onedrive = os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop")
    if os.path.isdir(onedrive):
        return onedrive
    return os.path.expanduser("~")


def _reference_tiff_path() -> str | None:
    for path in _REFERENCE_CANDIDATES:
        if os.path.isfile(path):
            return path
    return None


def _output_path(input_path: str, output_dir: str | None = None) -> str:
    base_name = os.path.splitext(os.path.basename(input_path))[0]
    folder = output_dir or _desktop_dir()
    return os.path.join(folder, f"{base_name}.tif")


def is_photoshop_installed() -> bool:
    return False


def is_supported_image(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in _IMAGE_EXTS


def _parse_dpi(dpi_info) -> tuple[float, float]:
    if not dpi_info:
        return 300.0, 300.0
    if isinstance(dpi_info, tuple):
        if len(dpi_info) >= 2:
            return float(dpi_info[0]), float(dpi_info[1])
        if len(dpi_info) == 1:
            return float(dpi_info[0]), float(dpi_info[0])
    return float(dpi_info), float(dpi_info)


def _load_rgba_image(input_path: str) -> tuple[np.ndarray, tuple[float, float]]:
    with Image.open(input_path) as img:
        dpi = _parse_dpi(img.info.get("dpi"))
        original_size = img.size
        rgba = img.convert("RGBA")
        if rgba.size != original_size:
            raise ValueError("Không được thay đổi kích thước ảnh khi đọc file.")
        return np.array(rgba, dtype=np.uint8), dpi


def _load_reference_tag(tag_id: int) -> bytes | None:
    ref_path = _reference_tiff_path()
    if not ref_path:
        return None
    try:
        with tifffile.TiffFile(ref_path) as tif:
            tag = tif.pages[0].tags.get(tag_id)
            if tag is not None:
                return tag.value
    except Exception:
        return None
    return None


def _build_w1_spot_mask(alpha: np.ndarray) -> np.ndarray:
    """Match Photoshop reference: W1 on transparent + soft edge only."""
    spot = np.zeros_like(alpha, dtype=np.uint8)
    spot[alpha == 0] = 255
    fringe = (alpha > 0) & (alpha < 255)
    spot[fringe] = (255 - alpha[fringe]).astype(np.uint8)
    return spot


def _premultiply_rgb_alpha(rgba: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Associated-alpha TIFF stores premultiplied RGB (same as Photoshop)."""
    alpha = rgba[:, :, 3]
    rgb = np.round(
        rgba[:, :, :3].astype(np.float32) * alpha[:, :, None].astype(np.float32) / 255.0
    ).astype(np.uint8)
    return rgb, alpha


def _load_rgb_spot_tiff(input_path: str) -> tuple[np.ndarray, tuple[float, float]] | None:
    with tifffile.TiffFile(input_path) as tif:
        page = tif.pages[0]
        if page.photometric != tifffile.PHOTOMETRIC.RGB or page.samplesperpixel < 5:
            return None
        dpi = _parse_dpi(page.tags.get("XResolution"))
        return page.asarray().astype(np.uint8), dpi


def _write_spot_tiff(
    output_path: str,
    rgba: np.ndarray,
    spot_mask: np.ndarray,
    dpi_x: float,
    dpi_y: float,
) -> None:
    if rgba.ndim != 3 or rgba.shape[2] != 4:
        raise ValueError("RGBA array phải có shape (H, W, 4).")
    if spot_mask.shape != rgba.shape[:2]:
        raise ValueError("Spot mask phải cùng kích thước với ảnh.")

    rgb, alpha = _premultiply_rgb_alpha(rgba)
    image = np.dstack([rgb, alpha, spot_mask]).astype(np.uint8)
    image_resources = _load_reference_tag(34377)
    if not image_resources:
        raise RuntimeError("Không tìm thấy file mẫu 1.tif (ImageResources).")

    extratags = [
        (34377, 7, len(image_resources), image_resources, True),
    ]

    icc_profile = _load_reference_tag(34675)
    if icc_profile:
        extratags.append((34675, 7, len(icc_profile), icc_profile, True))

    tifffile.imwrite(
        output_path,
        image,
        photometric="rgb",
        compression=None,
        resolution=(dpi_x, dpi_y),
        resolutionunit="INCH",
        extrasamples=[1, 0],
        extratags=extratags,
        metadata={
            "Software": "ACC2019 Spot W1",
            "DateTime": datetime.now().strftime("%Y:%m:%d %H:%M:%S"),
        },
    )


def apply_spot_color_w1(
    input_path: str,
    output_path: str | None = None,
    *,
    base_dir: str | None = None,
    timeout_sec: int = 180,
) -> dict:
    """Export RGB+Alpha+W1 TIFF giống Photoshop (mẫu Desktop/1.tif)."""
    del base_dir, timeout_sec

    input_path = os.path.abspath(input_path)
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Không tìm thấy file ảnh: {input_path}")
    if not is_supported_image(input_path):
        raise ValueError("Định dạng ảnh không được hỗ trợ.")
    if _reference_tiff_path() is None:
        raise FileNotFoundError("Không tìm thấy file mẫu: Desktop\\1.tif")

    if output_path:
        output_path = os.path.abspath(output_path)
    else:
        output_path = _output_path(input_path)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    before = time.time()
    ext = os.path.splitext(input_path)[1].lower()

    if ext in {".tif", ".tiff"}:
        loaded = _load_rgb_spot_tiff(input_path)
        if loaded is not None:
            data, dpi = loaded
            rgba = np.dstack([data[:, :, :3], data[:, :, 3]])
            spot_mask = data[:, :, 4]
        else:
            rgba, dpi = _load_rgba_image(input_path)
            spot_mask = _build_w1_spot_mask(rgba[:, :, 3])
    else:
        rgba, dpi = _load_rgba_image(input_path)
        spot_mask = _build_w1_spot_mask(rgba[:, :, 3])

    input_size = Image.open(input_path).size
    if (rgba.shape[1], rgba.shape[0]) != input_size:
        raise ValueError("Kích thước ảnh bị thay đổi — dừng xuất file.")

    if spot_mask.max() == 0 and rgba[:, :, 3].max() == 255:
        raise ValueError("Không tạo được kênh W1 từ ảnh đầu vào.")

    _write_spot_tiff(output_path, rgba, spot_mask, dpi[0], dpi[1])
    elapsed = time.time() - before

    if not os.path.isfile(output_path):
        raise RuntimeError("Không tạo được file .tif.")

    alpha = rgba[:, :, 3]
    opaque = alpha == 255
    fringe = (alpha > 0) & (alpha < 255)
    transparent = alpha == 0

    return {
        "input": input_path,
        "output": output_path,
        "channel": SPOT_CHANNEL_NAME,
        "cmyk": SPOT_CMYK,
        "solidity": SPOT_SOLIDITY,
        "size": (rgba.shape[1], rgba.shape[0]),
        "dpi": dpi,
        "object_coverage_pct": round(100.0 * np.count_nonzero(opaque) / alpha.size, 1),
        "transparent_background_pct": round(100.0 * np.count_nonzero(transparent) / alpha.size, 1),
        "w1_fringe_pct": round(100.0 * np.count_nonzero(fringe) / alpha.size, 1),
        "w1_spot_pct": round(100.0 * np.count_nonzero(spot_mask) / spot_mask.size, 1),
        "elapsed_sec": round(elapsed, 1),
    }