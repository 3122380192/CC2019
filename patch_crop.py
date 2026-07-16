"""Crop patch images based on the GG Template PSD safe-zone."""

import json
import os

import cv2
import numpy as np
from PIL import Image

DEFAULT_TEMPLATE_PSD = (
    r"E:\Template GG -Custom Shape Patches  -  "
    r"Custom Shape Patches Printed - Custom Shape Felt Patches (1).psd"
)

# Nền xám của template trong vùng an toàn
GRAY_BG_RANGE = (210, 246)
GRAY_BG_TOLERANCE = 14

# Viền cam template
ORANGE_BORDER = ((200, 255), (0, 180), (0, 120))

# Template GG dùng 300 ppi — giữ nguyên khi xuất
TARGET_DPI = (300.0, 300.0)


def _desktop_dir():
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    if os.path.exists(desktop):
        return desktop
    desktop = os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop")
    if os.path.exists(desktop):
        return desktop
    return os.path.expanduser("~")


def _cache_path(base_dir):
    return os.path.join(base_dir, "patch_crop_config.json")


def _detect_inner_crop(layer_arr):
    rgb = layer_arr[:, :, :3]
    orange = (
        (rgb[:, :, 0] > ORANGE_BORDER[0][0])
        & (rgb[:, :, 1] < ORANGE_BORDER[1][1])
        & (rgb[:, :, 2] < ORANGE_BORDER[2][1])
    )
    h, w = orange.shape
    top = next((y for y in range(h) if orange[y].mean() > 0.01), 0)
    bottom = next((y for y in range(h - 1, -1, -1) if orange[y].mean() > 0.01), h - 1)
    left = next((x for x in range(w) if orange[:, x].mean() > 0.01), 0)
    right = next((x for x in range(w - 1, -1, -1) if orange[:, x].mean() > 0.01), w - 1)
    inset = 15
    return (left + inset, top + inset, right - inset, bottom - inset)


def load_crop_config(template_psd=DEFAULT_TEMPLATE_PSD, base_dir=None):
    base_dir = base_dir or os.path.dirname(os.path.abspath(__file__))
    cache_file = _cache_path(base_dir)

    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if cached.get("template_psd") == template_psd and os.path.exists(template_psd):
                return cached
        except Exception:
            pass

    if not os.path.exists(template_psd):
        raise FileNotFoundError(f"Không tìm thấy file template PSD:\n{template_psd}")

    from psd_tools import PSDImage

    psd = PSDImage.open(template_psd)
    size_layer = None
    for layer in psd:
        if layer.name == "size":
            for child in layer:
                if child.visible:
                    size_layer = child
                    break
            break

    if size_layer is None:
        raise ValueError("Không tìm thấy layer size đang hiển thị trong template PSD.")

    layer_bbox = size_layer.bbox
    layer_arr = np.array(size_layer.composite())
    inner = _detect_inner_crop(layer_arr)

    config = {
        "template_psd": template_psd,
        "psd_size": [psd.width, psd.height],
        "layer_name": size_layer.name,
        "layer_bbox": list(layer_bbox),
        "inner_crop": list(inner),
        "abs_crop": [
            layer_bbox[0] + inner[0],
            layer_bbox[1] + inner[1],
            layer_bbox[0] + inner[2],
            layer_bbox[1] + inner[3],
        ],
        "target_dpi": list(TARGET_DPI),
    }

    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    return config


def _resolve_crop_box(image_size, config):
    """Xác định vùng cắt an toàn theo kích thước ảnh đầu vào."""
    psd_w, psd_h = config["psd_size"]
    abs_crop = config["abs_crop"]
    layer_bbox = config["layer_bbox"]
    inner = config["inner_crop"]
    img_w, img_h = image_size

    if (img_w, img_h) == (psd_w, psd_h):
        return tuple(abs_crop)

    layer_w = layer_bbox[2] - layer_bbox[0]
    layer_h = layer_bbox[3] - layer_bbox[1]
    if (img_w, img_h) == (layer_w, layer_h):
        return tuple(inner)

    safe_w = abs_crop[2] - abs_crop[0]
    safe_h = abs_crop[3] - abs_crop[1]
    # Ảnh đã export/cắt sẵn (≤ vùng an toàn + tolerance vài px)
    if img_w <= safe_w + 5 and img_h <= safe_h + 5:
        return (0, 0, img_w, img_h)

    scale_x = img_w / psd_w
    scale_y = img_h / psd_h
    if abs(scale_x - scale_y) < 0.02:
        return (
            int(abs_crop[0] * scale_x),
            int(abs_crop[1] * scale_y),
            int(abs_crop[2] * scale_x),
            int(abs_crop[3] * scale_y),
        )

    # Export theo layer size nhưng scale khác PSD — scale theo layer
    sx = img_w / layer_w
    sy = img_h / layer_h
    return (
        int(inner[0] * sx),
        int(inner[1] * sy),
        int(inner[2] * sx),
        int(inner[3] * sy),
    )


def _is_template_gray(rgb):
    mean = (rgb[:, :, 0] + rgb[:, :, 1] + rgb[:, :, 2]) / 3.0
    spread = np.maximum.reduce(
        [
            np.abs(rgb[:, :, 0] - rgb[:, :, 1]),
            np.abs(rgb[:, :, 1] - rgb[:, :, 2]),
            np.abs(rgb[:, :, 0] - rgb[:, :, 2]),
        ]
    )
    return (
        (mean >= GRAY_BG_RANGE[0])
        & (mean <= GRAY_BG_RANGE[1])
        & (spread <= GRAY_BG_TOLERANCE)
    )


def _is_orange(rgb):
    return (
        (rgb[:, :, 0] > ORANGE_BORDER[0][0])
        & (rgb[:, :, 1] < ORANGE_BORDER[1][1])
        & (rgb[:, :, 2] < ORANGE_BORDER[2][1])
    )


def _pick_patch_contour(contours, img_w, img_h):
    cx_img, cy_img = img_w / 2.0, img_h / 2.0
    max_dist = (img_w ** 2 + img_h ** 2) ** 0.5 / 2.0
    min_area = img_w * img_h * 0.004

    best = None
    best_score = -1.0
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue

        m = cv2.moments(cnt)
        if m["m00"] == 0:
            continue

        cx = m["m10"] / m["m00"]
        cy = m["m01"] / m["m00"]
        dist = ((cx - cx_img) ** 2 + (cy - cy_img) ** 2) ** 0.5
        score = area * (1.0 - min(dist / max_dist, 1.0))

        if score > best_score:
            best_score = score
            best = cnt

    return best


def _contour_to_mask(contour, shape):
    shape_mask = np.zeros(shape, dtype=np.uint8)
    cv2.drawContours(shape_mask, [contour], -1, 255, thickness=-1)
    x, y, w, h = cv2.boundingRect(contour)
    return shape_mask, (x, y, x + w, y + h)


def _mask_from_alpha(arr, smooth=False):
    alpha = arr[:, :, 3]
    if alpha.max() < 10:
        return None

    mask = (alpha > 10).astype(np.uint8) * 255
    if smooth:
        close_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_k)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    h, w = arr.shape[:2]
    chosen = _pick_patch_contour(contours, w, h)
    if chosen is None:
        chosen = max(contours, key=cv2.contourArea)
    return _contour_to_mask(chosen, mask.shape)


def _detect_patch_shape_mask(region_rgba):
    arr = np.array(region_rgba.convert("RGBA"))
    h, w = arr.shape[:2]
    rgb = arr[:, :, :3].astype(np.float32)

    gray_bg = _is_template_gray(rgb)
    orange = _is_orange(rgb)
    gray_ratio = gray_bg.mean()

    # Ảnh đã cắt sẵn (không còn nền xám template) -> giữ nguyên alpha gốc
    if gray_ratio < 0.2:
        alpha = arr[:, :, 3]
        if alpha.max() >= 10:
            ys, xs = np.where(alpha > 10)
            bbox = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
            shape_mask = (alpha > 10).astype(np.uint8) * 255
            return shape_mask, bbox

    # Patch = mọi thứ không phải nền xám template / viền cam
    patch_mask = (~gray_bg & ~orange).astype(np.uint8) * 255

    if patch_mask.sum() == 0:
        alpha_result = _mask_from_alpha(arr)
        if alpha_result is not None:
            return alpha_result
        raise ValueError("Không tìm thấy vùng patch trong ảnh.")

    close_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (17, 17))
    open_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    patch_mask = cv2.morphologyEx(patch_mask, cv2.MORPH_CLOSE, close_k)
    patch_mask = cv2.morphologyEx(patch_mask, cv2.MORPH_OPEN, open_k)

    contours, _ = cv2.findContours(patch_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise ValueError("Không tìm thấy đường viền patch.")

    chosen = _pick_patch_contour(contours, w, h)
    if chosen is None:
        raise ValueError("Không tìm thấy vùng patch hợp lệ.")

    shape_mask, bbox = _contour_to_mask(chosen, patch_mask.shape)
    bw = bbox[2] - bbox[0]
    bh = bbox[3] - bbox[1]
    if bw < 20 or bh < 20:
        raise ValueError("Vùng patch quá nhỏ sau khi nhận diện.")

    return shape_mask, bbox


def _apply_shape_mask(region_rgba, shape_mask, bbox):
    x1, y1, x2, y2 = bbox
    arr = np.array(region_rgba.convert("RGBA"))
    cropped = arr[y1:y2, x1:x2]
    mask = shape_mask[y1:y2, x1:x2]

    cropped[:, :, 3] = np.minimum(cropped[:, :, 3], mask)
    return Image.fromarray(cropped)


def _resolve_dpi(image, config=None):
    dpi = image.info.get("dpi")
    if dpi and len(dpi) >= 2:
        dpi_x, dpi_y = float(dpi[0]), float(dpi[1])
        if dpi_x > 0 and dpi_y > 0:
            return (dpi_x, dpi_y)

    if config and config.get("target_dpi"):
        td = config["target_dpi"]
        return (float(td[0]), float(td[1]))

    return TARGET_DPI


def _save_png_lossless(image, path, dpi):
    """Lưu PNG không nén mất dữ liệu, giữ metadata DPI."""
    image.save(
        path,
        format="PNG",
        dpi=dpi,
        compress_level=3,
        optimize=False,
    )


def _to_black_cut(shape_image):
    arr = np.array(shape_image.convert("RGBA"))
    alpha = arr[:, :, 3] > 10
    out = np.zeros_like(arr)
    out[alpha] = [0, 0, 0, 255]
    return Image.fromarray(out)


def _safe_stem(name: str) -> str:
    for ch in '<>:"/\\|?*':
        name = name.replace(ch, "-")
    return name.strip() or "patch"


def process_patch_image(
    image_path,
    template_psd=DEFAULT_TEMPLATE_PSD,
    base_dir=None,
    output_dir=None,
    order_stem: str | None = None,
    position: str | None = None,
):
    config = load_crop_config(template_psd, base_dir)
    output_dir = output_dir or _desktop_dir()

    with Image.open(image_path) as src:
        src = src.convert("RGBA")
        output_dpi = _resolve_dpi(src, config)

        crop_box = _resolve_crop_box(src.size, config)
        if crop_box == (0, 0, src.size[0], src.size[1]):
            work_image = src
        else:
            work_image = src.crop(crop_box)

        shape_mask, bbox = _detect_patch_shape_mask(work_image)
        design_image = _apply_shape_mask(work_image, shape_mask, bbox)
        black_image = _to_black_cut(design_image)

    if design_image.getbbox() is None:
        raise ValueError("Không tìm thấy nội dung patch sau khi cắt.")

    stem = _safe_stem(order_stem) if order_stem else os.path.splitext(os.path.basename(image_path))[0]
    if position:
        stem = f"{stem}_({position})"
    out_1 = os.path.join(output_dir, f"{stem}_1.png")
    out_2 = os.path.join(output_dir, f"{stem}_2.png")

    _save_png_lossless(design_image, out_1, output_dpi)
    _save_png_lossless(black_image, out_2, output_dpi)

    width_mm = design_image.size[0] / output_dpi[0] * 25.4
    height_mm = design_image.size[1] / output_dpi[1] * 25.4

    return {
        "output_1": out_1,
        "output_2": out_2,
        "size_1": design_image.size,
        "size_2": black_image.size,
        "dpi": output_dpi,
        "size_mm": (round(width_mm, 2), round(height_mm, 2)),
        "crop_box": crop_box,
        "patch_bbox": bbox,
        "layer_name": config["layer_name"],
    }