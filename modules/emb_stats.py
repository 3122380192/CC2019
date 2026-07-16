"""Thống kê đơn EMB theo ngày + ghi lịch sử mã đơn ra text (Desktop\\ngày)."""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Callable

_BASE = Path(__file__).resolve().parents[1]
STATS_PATH = _BASE / "csv_reader" / "emb_daily_stats.json"
MAX_ITEMS = 200

# Tên file trong Desktop\YYYY-MM-DD\
HISTORY_LOG_NAME = "lich_su_don.txt"   # chi tiết: giờ · mã · SP
IDS_ONLY_NAME = "ma_don.txt"           # mỗi dòng 1 mã — dễ tìm / copy
SUMMARY_NAME = "thong_ke_don.txt"      # tóm tắt số lượng


def _load() -> dict:
    if not STATS_PATH.is_file():
        return {}
    try:
        return json.loads(STATS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save(data: dict) -> None:
    STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _desktop_base() -> str:
    for p in (
        os.path.join(os.path.expanduser("~"), "Desktop"),
        os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop"),
    ):
        if os.path.isdir(p):
            return p
    return os.path.expanduser("~")


def get_today_orders_folder() -> str:
    """Thư mục tổng tất cả đơn hôm nay: Desktop/YYYY-MM-DD."""
    return os.path.join(_desktop_base(), date.today().isoformat())


def ensure_today_folder() -> str:
    folder = get_today_orders_folder()
    os.makedirs(folder, exist_ok=True)
    return folder


def today_history_log_path() -> str:
    return os.path.join(ensure_today_folder(), HISTORY_LOG_NAME)


def today_ids_file_path() -> str:
    return os.path.join(ensure_today_folder(), IDS_ONLY_NAME)


def today_summary_path() -> str:
    return os.path.join(ensure_today_folder(), SUMMARY_NAME)


def _append_line(path: str, line: str) -> None:
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line.rstrip("\n") + "\n")


def _id_already_in_file(path: str, order_id: str) -> bool:
    if not order_id or not os.path.isfile(path):
        return False
    key = order_id.strip().upper()
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip().upper() == key:
                    return True
    except OSError:
        return False
    return False


def count_today_order_folders() -> int:
    """Đếm subfolder trong Desktop\\YYYY-MM-DD (mỗi folder = 1 đơn)."""
    folder = get_today_orders_folder()
    if not os.path.isdir(folder):
        return 0
    n = 0
    try:
        for name in os.listdir(folder):
            path = os.path.join(folder, name)
            if os.path.isdir(path) and not name.startswith("."):
                n += 1
    except OSError:
        return 0
    return n


def count_today_ids_in_text() -> int:
    path = os.path.join(get_today_orders_folder(), IDS_ONLY_NAME)
    if not os.path.isfile(path):
        return 0
    try:
        with open(path, encoding="utf-8") as f:
            return sum(1 for ln in f if ln.strip() and not ln.startswith("#"))
    except OSError:
        return 0


def is_order_already_logged(order_id: str) -> bool:
    """True nếu mã đã có trong ma_don.txt hôm nay (trùng)."""
    oid = (order_id or "").strip()
    if not oid:
        return True
    return _id_already_in_file(os.path.join(get_today_orders_folder(), IDS_ONLY_NAME), oid)


def append_order_to_desktop_log(
    order_id: str,
    product_name: str = "",
    *,
    note: str = "",
    force: bool = False,
) -> tuple[str | None, bool]:
    """
    Ghi mã đơn vào text trong folder ngày Desktop\\YYYY-MM-DD\\.
    Trả (path_log, is_new) — is_new=True chỉ khi lần đầu ghi mã hôm nay.
    """
    oid = (order_id or "").strip()
    if not oid:
        return None, False
    folder = ensure_today_folder()
    ids_path = os.path.join(folder, IDS_ONLY_NAME)
    log_path = os.path.join(folder, HISTORY_LOG_NAME)

    is_new = not _id_already_in_file(ids_path, oid)
    if not is_new and not force:
        return (log_path if os.path.isfile(log_path) else None), False

    now = datetime.now().strftime("%H:%M:%S")
    prod = (product_name or "").replace("\n", " ").strip()[:80]
    extra = (note or "").replace("\n", " ").strip()[:60]
    parts = [f"[{now}]", oid]
    if prod:
        parts.append(prod)
    if extra:
        parts.append(extra)
    line = " | ".join(parts)

    try:
        if is_new:
            if not os.path.isfile(ids_path):
                _append_line(ids_path, f"# Mã đơn {date.today().isoformat()} — mỗi dòng 1 mã")
            if not os.path.isfile(log_path):
                _append_line(
                    log_path,
                    f"# Lịch sử đơn {date.today().isoformat()}  (giờ | mã | sản phẩm)",
                )
            _append_line(ids_path, oid)
        if is_new or force:
            _append_line(log_path, line)
        _write_summary_file(folder)
        return log_path, is_new
    except OSError:
        return None, False


def _write_summary_file(folder: str | None = None) -> str:
    """Cập nhật thong_ke_don.txt (đếm + danh sách)."""
    folder = folder or ensure_today_folder()
    today = date.today().isoformat()
    stats = _stats_from_json_only()
    ids_path = os.path.join(folder, IDS_ONLY_NAME)
    ids: list[str] = []
    if os.path.isfile(ids_path):
        try:
            with open(ids_path, encoding="utf-8") as f:
                ids = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
        except OSError:
            pass
    folder_n = count_today_order_folders()
    lines = [
        f"=== Thống kê đơn {today} ===",
        f"Cập nhật: {datetime.now().strftime('%H:%M:%S')}",
        f"Tổng mã tool (file, không trùng): {len(ids)}",
        f"Tổng folder Desktop\\ngày: {folder_n}",
        f"Tổng đơn (app JSON): {stats.get('orders', 0)}",
        f"Patch/DXF: {stats.get('patch_dxf', 0)}",
        "",
        "--- Danh sách mã ---",
        *ids,
        "",
        f"File chi tiết: {HISTORY_LOG_NAME}",
        f"File chỉ mã:   {IDS_ONLY_NAME}",
    ]
    path = os.path.join(folder, SUMMARY_NAME)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except OSError:
        pass
    return path


def _stats_from_json_only() -> dict:
    today = date.today().isoformat()
    data = _load()
    day = data.get(today, {"orders": 0, "items": [], "actions": []})
    actions = day.get("actions", [])
    items = day.get("items", [])
    return {
        "orders": int(day.get("orders", 0)),
        "products": len(items),
        "items": items,
        "patch_dxf": sum(1 for a in actions if a.get("action") in ("patch", "dxf")),
    }


def record_emb_order(
    order_id: str,
    product_name: str = "",
    *,
    merged: bool = False,
    notify_telegram: bool = True,
    base_dir: str | None = None,
    on_telegram_done: Callable | None = None,
) -> dict:
    """
    Ghi nhận đơn khi portal gửi / nhận đơn (TỰ ĐỘNG — không cần phím tắt).

    Nguồn sự thật trùng: ma_don.txt hôm nay.
    - Mã đã có trong ma_don.txt → không +1, không gửi Telegram.
    - Mã mới → ghi text, +1 tool, TỰ ĐỘNG gửi Telegram + thống kê folder ngày.

    (merged chỉ ảnh hưởng UI history, không chặn Telegram nếu mã chưa có trong file.)
    Trả {"new": bool, "tool_count": int, "folder_count": int, "telegram": "queued"|"skip"|...}.
    """
    oid = (order_id or "").strip()
    result = {
        "new": False,
        "tool_count": count_today_ids_in_text(),
        "folder_count": count_today_order_folders(),
        "telegram": "skip",
    }
    if not oid:
        return result

    # Trùng theo file text → bỏ qua hoàn toàn
    if is_order_already_logged(oid):
        result["tool_count"] = count_today_ids_in_text()
        result["folder_count"] = count_today_order_folders()
        result["telegram"] = "skip_duplicate"
        return result

    # Đơn mới trong ngày
    _path, is_new = append_order_to_desktop_log(oid, product_name)
    if not is_new:
        result["tool_count"] = count_today_ids_in_text()
        result["folder_count"] = count_today_order_folders()
        result["telegram"] = "skip_duplicate"
        return result

    today = date.today().isoformat()
    data = _load()
    day = data.setdefault(today, {"orders": 0, "items": []})
    ids = {x.get("id") for x in day.get("items", [])}
    if oid not in ids:
        day["orders"] = int(day.get("orders", 0)) + 1
        items = day.setdefault("items", [])
        items.insert(0, {
            "time": datetime.now().strftime("%H:%M:%S"),
            "id": oid,
            "product": (product_name or "")[:60],
        })
        day["items"] = items[:MAX_ITEMS]
        _save(data)

    tool_count = count_today_ids_in_text()
    folder_count = count_today_order_folders()
    result = {
        "new": True,
        "tool_count": tool_count,
        "folder_count": folder_count,
        "telegram": "queued" if notify_telegram else "off",
    }

    if notify_telegram:
        try:
            from modules.telegram_notify import notify_new_order

            notify_new_order(
                oid,
                product_name or "",
                base_dir=base_dir,
                tool_count=tool_count,
                folder_count=folder_count,
                time_str=datetime.now().strftime("%H:%M:%S"),
                date_str=today,
                folder_path=get_today_orders_folder(),
                on_done=on_telegram_done,
            )
        except Exception as exc:
            result["telegram"] = f"error:{exc}"
            if on_telegram_done:
                try:
                    on_telegram_done(False, str(exc))
                except Exception:
                    pass
    return result


def record_emb_action(order_id: str, action: str) -> None:
    """Ghi nhận patch/dxf/spot cho đơn (không tăng đếm đơn mới)."""
    if not order_id:
        return
    today = date.today().isoformat()
    data = _load()
    day = data.setdefault(today, {"orders": 0, "items": [], "actions": []})
    acts = day.setdefault("actions", [])
    acts.insert(0, {
        "time": datetime.now().strftime("%H:%M:%S"),
        "id": order_id,
        "action": action,
    })
    day["actions"] = acts[:MAX_ITEMS]
    _save(data)
    # không ghi đơn mới / không telegram khi chỉ patch-dxf


def get_emb_today_stats() -> dict:
    today = date.today().isoformat()
    data = _load()
    day = data.get(today, {"orders": 0, "items": [], "actions": []})
    actions = day.get("actions", [])
    items = day.get("items", [])
    folder = get_today_orders_folder()
    ids_path = os.path.join(folder, IDS_ONLY_NAME)
    ids_file = count_today_ids_in_text()
    folder_n = count_today_order_folders()
    return {
        "date": today,
        "orders": int(day.get("orders", 0)),
        "products": len(items),
        "items": items,
        "patch_dxf": sum(1 for a in actions if a.get("action") in ("patch", "dxf")),
        "ids_in_text": ids_file,
        "folder_count": folder_n,
        "log_path": os.path.join(folder, HISTORY_LOG_NAME),
        "ids_path": ids_path,
        "folder": folder,
    }


def open_today_stats_folder() -> str:
    folder = ensure_today_folder()
    _write_summary_file(folder)
    try:
        os.startfile(folder)
    except OSError:
        pass
    return folder


def open_today_ids_file() -> str:
    path = today_ids_file_path()
    if not os.path.isfile(path):
        ensure_today_folder()
        _append_line(path, f"# Mã đơn {date.today().isoformat()} — mỗi dòng 1 mã")
    try:
        os.startfile(path)
    except OSError:
        pass
    return path


def open_today_history_log() -> str:
    path = today_history_log_path()
    if not os.path.isfile(path):
        ensure_today_folder()
        _append_line(
            path,
            f"# Lịch sử đơn {date.today().isoformat()}  (giờ | mã | sản phẩm)",
        )
    try:
        os.startfile(path)
    except OSError:
        pass
    return path


def copy_today_ids_text() -> str:
    """Nội dung ma_don.txt (không comment) — để copy clipboard."""
    path = today_ids_file_path()
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, encoding="utf-8") as f:
            return "\n".join(
                ln.strip() for ln in f if ln.strip() and not ln.startswith("#")
            )
    except OSError:
        return ""


def record_last_folder(folder_path: str) -> None:
    if not folder_path or not os.path.isdir(folder_path):
        return
    data = _load()
    meta = data.setdefault("_meta", {})
    meta["last_folder"] = os.path.abspath(folder_path)
    _save(data)


def get_last_folder() -> str:
    data = _load()
    path = data.get("_meta", {}).get("last_folder", "")
    return path if path and os.path.isdir(path) else ""
