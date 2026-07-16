"""Bảng mã vùng thêu — cột B = checkbox, cột C = từ khóa biến thể."""

from __future__ import annotations

# (checkbox, từ khóa cột C) — dài trước để tránh khớp nhầm
REGION_ENTRIES: list[tuple[str, str]] = [
    ("5", "right arm"),
    ("6", "left arm"),
    ("8", "right cuff"),
    ("9", "left cuff"),
    ("A", "upper arm right"),
    ("V", "sleeve left"),
    ("T", "sleeve right"),
    ("E", "slit side left"),
    ("N", "neck inner"),
    ("I", "pocket top"),
    ("O", "pocket lower"),
    ("P", "pocket arm"),
    ("U", "underarm"),
    ("1", "neck"),
    ("3", "chest"),
    ("4", "middle"),
    ("B", "back"),
    ("C", "collar"),
    ("D", "shoulder"),
    ("F", "front"),
    ("G", "leg"),
    ("H", "thigh"),
    ("K", "ear"),
    ("L", "left"),
    ("R", "right"),
    ("S", "sleeve"),
]

# Checkbox hiển thị trên UI (thứ tự ưu tiên)
CHECKBOX_ORDER = [
    "1", "3", "4", "5", "6", "8", "9",
    "A", "B", "C", "D", "E", "F", "G", "H", "K", "L", "N",
    "I", "O", "P", "R", "S", "V", "T", "U",
]


def detect_position_codes(product_name: str, variant_info: str) -> list[str]:
    """Quét biến thể → danh sách mã checkbox cần hiển thị."""
    text = f"{product_name or ''} {variant_info or ''}".lower()
    found: list[str] = []
    seen: set[str] = set()

    for code, keyword in REGION_ENTRIES:
        if keyword in text and code not in seen:
            found.append(code)
            seen.add(code)

    has_right_arm = "5" in seen
    has_left_arm = "6" in seen
    if "arm" in text and not (has_right_arm and has_left_arm):
        if "5" not in seen:
            found.append("5")
            seen.add("5")
        if "6" not in seen:
            found.append("6")
            seen.add("6")

    combined = f"{product_name or ''}".lower()
    if ("patch" in combined or "patches" in combined) and "4" not in seen:
        found.insert(0, "4")
        seen.add("4")

    if seen & {"5", "6"}:
        found = [c for c in found if c not in ("L", "R")]
        seen -= {"L", "R"}

    if not found:
        found = ["4"]

    order = {c: i for i, c in enumerate(CHECKBOX_ORDER)}
    return sorted(found, key=lambda c: order.get(c, 99))


def sort_for_display(codes: list[str]) -> list[str]:
    order = {c: i for i, c in enumerate(CHECKBOX_ORDER)}
    return sorted(codes, key=lambda c: order.get(c, 99))