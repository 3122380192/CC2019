"""Image-to-DXF — giữ tỉ lệ 1:1, đường cắt mượt, ít méo."""

from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

# Đơn giản hóa contour (mm) — nhỏ = giữ chi tiết, lớn = mượt hơn
SMOOTH_TOLERANCE_MM = 0.22

# Làm mượt góc nhẹ (1 lần đủ; nhiều hơn dễ méo hình)
CHAIKIN_ITERATIONS = 1

# Gom điểm thừa sau khi làm mượt
FINAL_SIMPLIFY_MM = 0.07

# Polyline đi qua đúng đỉnh đã xử lý — spline fit dễ lệch contour
EXPORT_AS_SPLINE = False

MIN_CONTOUR_AREA_PX = 20
DEFAULT_DPI = 300.0


def resolve_dpi(img: Image.Image) -> tuple[float, float]:
    """Đọc DPI từ metadata; fallback 300 (chuẩn in patch/silhouette)."""
    raw = img.info.get("dpi") or img.info.get("resolution")
    if raw:
        if isinstance(raw, tuple):
            if len(raw) >= 2:
                dx, dy = float(raw[0]), float(raw[1])
            else:
                dx = dy = float(raw[0])
        else:
            dx = dy = float(raw)
        if dx > 0 and dy > 0:
            return dx, dy
    return DEFAULT_DPI, DEFAULT_DPI


def physical_size_mm(width_px: int, height_px: int, dpi: tuple[float, float]) -> tuple[float, float, float]:
    """
    Trả về (mm_per_px đồng nhất, width_mm, height_mm).
    Dùng cùng mm_per_px cho X/Y để pixel vuông → contour không bị méo.
    """
    dx, dy = dpi
    if dx <= 0:
        dx = DEFAULT_DPI
    if dy <= 0:
        dy = DEFAULT_DPI
    # DPI lệch nhẹ trong metadata → lấy trung bình để giữ tỉ lệ hình
    dpi_u = (dx + dy) / 2.0
    if abs(dx - dy) / max(dx, dy) > 0.02:
        dpi_u = max(dx, dy)
    mm_per_px = 25.4 / dpi_u
    return mm_per_px, width_px * mm_per_px, height_px * mm_per_px


def read_image_rgba(path: str) -> tuple[np.ndarray, int, int, tuple[float, float]]:
    """Đọc ảnh qua PIL — đúng kích thước & alpha, tránh lệch khi cv2.imread."""
    with Image.open(path) as img:
        width_px, height_px = img.size
        dpi = resolve_dpi(img)
        rgba = img.convert("RGBA")
        arr = np.array(rgba, dtype=np.uint8)
    # OpenCV dùng BGRA
    bgra = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGRA)
    return bgra, width_px, height_px, dpi


def _light_denoise(channel: np.ndarray) -> np.ndarray:
    """Lọc nhiễu nhẹ, giữ biên sắc."""
    k = 3 if max(channel.shape[:2]) < 500 else 5
    if k % 2 == 0:
        k += 1
    return cv2.medianBlur(channel, k)


def build_silhouette_mask(img_bgra: np.ndarray) -> np.ndarray:
    if img_bgra is None:
        raise ValueError("Không thể đọc file ảnh.")

    if len(img_bgra.shape) == 3 and img_bgra.shape[2] >= 4:
        alpha = _light_denoise(img_bgra[:, :, 3])
        _, thresh = cv2.threshold(alpha, 12, 255, cv2.THRESH_BINARY)
    else:
        if len(img_bgra.shape) == 3:
            gray = cv2.cvtColor(img_bgra, cv2.COLOR_BGR2GRAY)
        else:
            gray = img_bgra
        gray = _light_denoise(gray)
        _, thresh = cv2.threshold(gray, 245, 255, cv2.THRESH_BINARY_INV)

    # Chỉ đóng lỗ nhỏ — tránh phình méo biên
    k = 3
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=1)
    return thresh


def _chaikin_smooth(points: list[tuple[float, float]], iterations: int = CHAIKIN_ITERATIONS) -> list[tuple[float, float]]:
    pts = list(points)
    for _ in range(iterations):
        if len(pts) < 3:
            break
        new_pts: list[tuple[float, float]] = []
        count = len(pts)
        for i in range(count):
            p0 = pts[i]
            p1 = pts[(i + 1) % count]
            new_pts.append((0.75 * p0[0] + 0.25 * p1[0], 0.75 * p0[1] + 0.25 * p1[1]))
            new_pts.append((0.25 * p0[0] + 0.75 * p1[0], 0.25 * p0[1] + 0.75 * p1[1]))
        pts = new_pts
    return pts


def _simplify_mm(points: list[tuple[float, float]], tolerance_mm: float) -> list[tuple[float, float]]:
    if len(points) < 3:
        return points
    arr = np.array(points, dtype=np.float32).reshape(-1, 1, 2)
    simplified = cv2.approxPolyDP(arr, tolerance_mm, True)
    if len(simplified) < 3:
        return points
    return [(float(p[0][0]), float(p[0][1])) for p in simplified]


def _pixel_to_mm_points(
    contour: np.ndarray,
    height_px: int,
    mm_per_px: float,
) -> list[tuple[float, float]]:
    """Chuyển contour pixel → mm; lật trục Y cho hệ DXF; cùng mm_per_px X/Y."""
    return [
        (float(pt[0][0] * mm_per_px), float((height_px - pt[0][1]) * mm_per_px))
        for pt in contour
    ]


def _smooth_contour_points(points: list[tuple[float, float]], tolerance_mm: float) -> list[tuple[float, float]]:
    if len(points) < 4:
        return points
    points = _chaikin_smooth(points, CHAIKIN_ITERATIONS)
    points = _simplify_mm(points, FINAL_SIMPLIFY_MM)
    if len(points) > 6:
        points = _simplify_mm(points, tolerance_mm * 0.4)
    return points


def extract_smooth_polylines(
    img_bgra: np.ndarray,
    width_px: int,
    height_px: int,
    dpi: tuple[float, float],
    tolerance_mm: float = SMOOTH_TOLERANCE_MM,
) -> list[list[tuple[float, float]]]:
    thresh = build_silhouette_mask(img_bgra)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)

    mm_per_px, _, _ = physical_size_mm(width_px, height_px, dpi)
    epsilon_px = max(0.8, tolerance_mm / mm_per_px)

    polylines: list[list[tuple[float, float]]] = []
    for contour in contours:
        if cv2.contourArea(contour) < MIN_CONTOUR_AREA_PX:
            continue

        # Lấy đủ điểm biên gốc rồi simplify nhẹ — giữ hình dạng
        simplified = cv2.approxPolyDP(contour, epsilon_px, True)
        if len(simplified) < 3:
            continue

        points = _pixel_to_mm_points(simplified, height_px, mm_per_px)
        points = _smooth_contour_points(points, tolerance_mm)

        if len(points) > 2:
            polylines.append(points)

    return polylines


def mm_points_to_pixels(
    points: list[tuple[float, float]],
    height_px: int,
    mm_per_px: float,
) -> np.ndarray:
    """Chuyển điểm mm → pixel (int32) cho fillPoly."""
    pts = [
        (int(round(x / mm_per_px)), int(round(height_px - y / mm_per_px)))
        for x, y in points
    ]
    return np.array(pts, dtype=np.int32)


def build_cut_mask(
    polylines: list[list[tuple[float, float]]],
    width_px: int,
    height_px: int,
    mm_per_px: float,
) -> np.ndarray:
    """Rasterize đường cắt DXF thành mask nhị phân."""
    mask = np.zeros((height_px, width_px), dtype=np.uint8)
    for pts_mm in polylines:
        pts_px = mm_points_to_pixels(pts_mm, height_px, mm_per_px)
        if len(pts_px) >= 3:
            cv2.fillPoly(mask, [pts_px], 255)
    return mask


def compute_dxf_match_pct(
    img_bgra: np.ndarray,
    polylines: list[list[tuple[float, float]]],
    width_px: int,
    height_px: int,
    dpi: tuple[float, float],
) -> float:
    """Phần trăm khớp IoU giữa silhouette ảnh và vùng fill đường cắt."""
    mm_per_px, _, _ = physical_size_mm(width_px, height_px, dpi)
    silhouette = build_silhouette_mask(img_bgra)
    cut_mask = build_cut_mask(polylines, width_px, height_px, mm_per_px)
    match_pct, _ = compute_match_score(silhouette, cut_mask)
    return match_pct


def compute_match_score(
    silhouette: np.ndarray,
    cut_mask: np.ndarray,
) -> tuple[float, np.ndarray]:
    """
    So sánh silhouette vs vùng cắt.
    Trả về (phần trăm khớp IoU, mask vùng lệch).
    """
    sil = silhouette > 0
    cut = cut_mask > 0
    union = sil | cut
    if not np.any(union):
        return 100.0, np.zeros_like(silhouette, dtype=np.uint8)

    intersection = sil & cut
    match_pct = 100.0 * float(np.count_nonzero(intersection)) / float(np.count_nonzero(union))
    mismatch = ((sil & ~cut) | (cut & ~sil)).astype(np.uint8) * 255
    return match_pct, mismatch


def add_curve_to_modelspace(msp, points: list[tuple[float, float]]) -> None:
    """Thêm đường cắt khép kín — polyline chính xác hơn spline fit."""
    if len(points) < 3:
        return
    if EXPORT_AS_SPLINE and len(points) >= 6:
        fit = list(points)
        if fit[0] != fit[-1]:
            fit.append(fit[0])
        msp.add_spline(fit_points=fit)
    else:
        msp.add_lwpolyline(points, close=True, dxfattribs={"const_width": 0})