"""Kiểm tra file trong folder đơn — TBF / DST (+ DXF tùy chọn)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# Required packages (không gồm DXF — DXF hiện nút riêng)
TBF_REQUIRED = ("TBF", "CTO", "DGF", "EMB", "LTO", "PNG")
DST_REQUIRED = ("DST", "DGT", "EMB", "PNG")

# Màu trạng thái
COLOR_OK = "#00e676"       # xanh — đủ / có
COLOR_WIP = "#ffc107"      # vàng — đang làm (một phần)
COLOR_MISS = "#ff1744"     # đỏ — thiếu
COLOR_IDLE = "#555566"     # xám — chưa check


@dataclass
class ExtStatus:
    ext: str
    present: bool
    path: str | None = None


@dataclass
class FolderFileStatus:
    file_type: str  # TBF | DST | …
    folder: str | None
    stem: str | None
    required: list[ExtStatus] = field(default_factory=list)
    dxf: ExtStatus | None = None
    # overall: green | yellow | red | idle
    overall: str = "idle"
    found: int = 0
    total: int = 0

    @property
    def overall_color(self) -> str:
        return {
            "green": COLOR_OK,
            "yellow": COLOR_WIP,
            "red": COLOR_MISS,
            "idle": COLOR_IDLE,
        }.get(self.overall, COLOR_IDLE)

    @property
    def summary(self) -> str:
        if self.overall == "idle":
            return "—"
        return f"{self.found}/{self.total}"


def required_exts(file_type: str) -> tuple[str, ...]:
    ft = (file_type or "").upper().strip()
    if ft == "DST":
        return DST_REQUIRED
    # default TBF (và các loại patch tương tự)
    return TBF_REQUIRED


def _list_files(folder: str) -> list[str]:
    try:
        return [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]
    except OSError:
        return []


def _match_ext(files: list[str], folder: str, stem: str | None, ext: str, order_id: str = "") -> ExtStatus:
    """Tìm file .ext khớp stem hoặc chứa_id (không phân biệt hoa thường)."""
    ext_l = ext.lower().lstrip(".")
    stem_l = (stem or "").lower()
    oid_l = (order_id or "").lower().replace("/", "-").replace("\\", "-")
    # candidates ordered by preference
    for name in files:
        base, e = os.path.splitext(name)
        if e.lower().lstrip(".") != ext_l:
            continue
        bl = base.lower()
        if stem_l and (bl == stem_l or bl.startswith(stem_l) or stem_l in bl):
            return ExtStatus(ext=ext.upper(), present=True, path=os.path.join(folder, name))
        if oid_l and oid_l in bl:
            return ExtStatus(ext=ext.upper(), present=True, path=os.path.join(folder, name))
    # any file with that extension in folder (fallback khi stem lệch)
    for name in files:
        e = os.path.splitext(name)[1].lower().lstrip(".")
        if e == ext_l:
            return ExtStatus(ext=ext.upper(), present=True, path=os.path.join(folder, name))
    return ExtStatus(ext=ext.upper(), present=False, path=None)


def check_folder(
    folder: str | None,
    file_type: str,
    stem: str | None = None,
    order_id: str = "",
    *,
    also_desktop: str | None = None,
) -> FolderFileStatus:
    """
    Check file required theo loại TBF/DST.
    DXF tách riêng (không ảnh hưởng overall green).
    overall:
      idle  — không folder
      red   — 0 file required
      yellow — có một phần
      green — đủ required
    """
    req_list = required_exts(file_type)
    result = FolderFileStatus(
        file_type=(file_type or "TBF").upper(),
        folder=folder,
        stem=stem,
        total=len(req_list),
    )

    search_dirs: list[str] = []
    if folder and os.path.isdir(folder):
        search_dirs.append(folder)
    if also_desktop and os.path.isdir(also_desktop) and also_desktop not in search_dirs:
        search_dirs.append(also_desktop)

    if not search_dirs:
        result.overall = "idle"
        result.required = [ExtStatus(ext=e, present=False) for e in req_list]
        result.dxf = ExtStatus(ext="DXF", present=False)
        return result

    # gộp danh sách file từ mọi thư mục (ưu tiên folder đơn)
    all_hits: dict[str, ExtStatus] = {}
    dxf_hit: ExtStatus | None = None
    for d in search_dirs:
        files = _list_files(d)
        for ext in req_list:
            if all_hits.get(ext.upper(), ExtStatus(ext, False)).present:
                continue
            st = _match_ext(files, d, stem, ext, order_id)
            if st.present or ext.upper() not in all_hits:
                all_hits[ext.upper()] = st
        if not (dxf_hit and dxf_hit.present):
            dx = _match_ext(files, d, stem, "DXF", order_id)
            if not dx.present:
                # bất kỳ .dxf trong folder đơn; Desktop chỉ khi khớp stem/oid
                for name in files:
                    if not name.lower().endswith(".dxf"):
                        continue
                    bl = os.path.splitext(name)[0].lower()
                    oid_l = (order_id or "").lower()[:12]
                    stem_l = (stem or "").lower()
                    if d == folder or (stem_l and stem_l in bl) or (oid_l and oid_l in bl):
                        dx = ExtStatus("DXF", True, os.path.join(d, name))
                        break
            if dx.present:
                dxf_hit = dx

    result.required = [all_hits.get(e.upper(), ExtStatus(e.upper(), False)) for e in req_list]
    result.dxf = dxf_hit or ExtStatus("DXF", False)

    result.found = sum(1 for s in result.required if s.present)
    if result.found <= 0:
        result.overall = "red"
    elif result.found >= result.total:
        result.overall = "green"
    else:
        result.overall = "yellow"
    return result
