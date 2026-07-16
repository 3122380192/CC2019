"""CSV Loki — tải ảnh, so sánh, lịch sử, thống kê."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path

from csv_reader.config import AppConfig, load_config
from csv_reader.detector import detect_product
from csv_reader.reader import CsvData, read_csv_file

_BASE = Path(__file__).resolve().parents[1]
RECENT_PATH = _BASE / "csv_reader" / "recent_files.json"
STATS_PATH = _BASE / "csv_reader" / "daily_stats.json"
MAX_RECENT = 10

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _field_index(headers: list[str], names: list[str]) -> int | None:
    lower = [h.strip().lower() for h in headers]
    for name in names:
        key = name.lower()
        if key in lower:
            return lower.index(key)
    return None


def get_cell(row: list[str], headers: list[str], names: list[str]) -> str:
    idx = _field_index(headers, names)
    if idx is None or idx >= len(row):
        return ""
    return row[idx].strip()


def safe_filename(name: str) -> str:
    cleaned = _INVALID_CHARS.sub("_", name.strip())
    return cleaned or "unknown"


def _load_json(path: Path, default):
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def add_recent_file(path: str | Path) -> list[str]:
    p = str(Path(path).resolve())
    items = _load_json(RECENT_PATH, [])
    items = [x for x in items if x != p]
    items.insert(0, p)
    items = items[:MAX_RECENT]
    _save_json(RECENT_PATH, items)
    return items


def get_recent_files() -> list[str]:
    items = _load_json(RECENT_PATH, [])
    return [p for p in items if Path(p).is_file()]


def record_csv_processed(path: str | Path, product_name: str, row_count: int) -> None:
    today = date.today().isoformat()
    stats = _load_json(STATS_PATH, {})
    day = stats.setdefault(today, {"files": 0, "rows": 0, "items": []})
    day["files"] = int(day.get("files", 0)) + 1
    day["rows"] = int(day.get("rows", 0)) + row_count
    items = day.setdefault("items", [])
    entry = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "file": Path(path).name,
        "product": product_name,
        "rows": row_count,
    }
    items.insert(0, entry)
    day["items"] = items[:50]
    _save_json(STATS_PATH, stats)


def get_today_stats() -> dict:
    today = date.today().isoformat()
    stats = _load_json(STATS_PATH, {})
    day = stats.get(today, {"files": 0, "rows": 0, "items": []})
    return {
        "date": today,
        "files": int(day.get("files", 0)),
        "rows": int(day.get("rows", 0)),
        "items": day.get("items", []),
    }


def _guess_extension(url: str, content_type: str) -> str:
    url_lower = url.lower().split("?")[0]
    for ext in (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"):
        if url_lower.endswith(ext):
            return ext if ext != ".jpeg" else ".jpg"
    ct = content_type.lower()
    if "png" in ct:
        return ".png"
    if "jpeg" in ct or "jpg" in ct:
        return ".jpg"
    if "webp" in ct:
        return ".webp"
    if "tiff" in ct:
        return ".tif"
    return ".png"


def download_artworks(
    data: CsvData,
    output_dir: str | Path,
    *,
    row_indices: list[int] | None = None,
) -> list[dict]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    indices = row_indices if row_indices is not None else list(range(len(data.rows)))
    results: list[dict] = []

    for idx in indices:
        if idx < 0 or idx >= len(data.rows):
            continue
        row = data.rows[idx]
        item_id = get_cell(row, data.headers, ["Item ID", "Item ID PO", "Order ID"])
        url = get_cell(row, data.headers, ["Artwork Front", "Artwork Back"])
        if not item_id:
            results.append({"index": idx, "ok": False, "error": "Thiếu Item ID"})
            continue
        if not url or not url.startswith("http"):
            results.append({"index": idx, "item_id": item_id, "ok": False, "error": "Thiếu URL Artwork"})
            continue

        fname = safe_filename(item_id)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ACC2019/2.2"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read()
                ctype = resp.headers.get("Content-Type", "")
            ext = _guess_extension(url, ctype)
            dest = out / f"{fname}{ext}"
            n = 1
            while dest.exists():
                dest = out / f"{fname}_{n}{ext}"
                n += 1
            dest.write_bytes(body)
            results.append({
                "index": idx, "item_id": item_id, "ok": True,
                "path": str(dest), "url": url,
            })
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            results.append({
                "index": idx, "item_id": item_id, "ok": False, "error": str(exc), "url": url,
            })

    return results


def _extract_ids(data: CsvData) -> tuple[set[str], set[str]]:
    pos: set[str] = set()
    items: set[str] = set()
    for row in data.rows:
        po = get_cell(row, data.headers, ["PO", "Item Input", "Order ID"])
        item = get_cell(row, data.headers, ["Item ID", "Item ID PO"])
        if po:
            pos.add(po)
        if item:
            items.add(item)
    return pos, items


def compare_csv_files(
    path_a: str | Path,
    path_b: str | Path,
    config: AppConfig | None = None,
) -> dict:
    cfg = config or load_config()
    data_a = read_csv_file(path_a)
    data_b = read_csv_file(path_b)
    det_a = detect_product(data_a, cfg)
    det_b = detect_product(data_b, cfg)

    pos_a, items_a = _extract_ids(data_a)
    pos_b, items_b = _extract_ids(data_b)

    dup_a = _find_duplicates(data_a, "Item ID")
    dup_b = _find_duplicates(data_b, "Item ID")

    return {
        "file_a": Path(path_a).name,
        "file_b": Path(path_b).name,
        "product_a": det_a.product.name if det_a.product else "?",
        "product_b": det_b.product.name if det_b.product else "?",
        "rows_a": data_a.row_count,
        "rows_b": data_b.row_count,
        "po_only_a": sorted(pos_a - pos_b),
        "po_only_b": sorted(pos_b - pos_a),
        "item_only_a": sorted(items_a - items_b),
        "item_only_b": sorted(items_b - items_a),
        "item_dup_a": dup_a,
        "item_dup_b": dup_b,
        "item_common": len(items_a & items_b),
    }


def _find_duplicates(data: CsvData, field: str) -> list[str]:
    seen: dict[str, int] = {}
    for row in data.rows:
        val = get_cell(row, data.headers, [field, "Item ID PO"])
        if val:
            seen[val] = seen.get(val, 0) + 1
    return sorted(k for k, v in seen.items() if v > 1)


def format_compare_report(result: dict) -> str:
    lines = [
        f"A: {result['file_a']} ({result['product_a']}, {result['rows_a']} dòng)",
        f"B: {result['file_b']} ({result['product_b']}, {result['rows_b']} dòng)",
        f"Item ID trùng cả 2 file: {result['item_common']}",
        "",
        f"PO chỉ có ở A ({len(result['po_only_a'])}):",
        *([f"  - {x}" for x in result['po_only_a'][:20]] or ["  (không)"]),
        f"PO chỉ có ở B ({len(result['po_only_b'])}):",
        *([f"  - {x}" for x in result['po_only_b'][:20]] or ["  (không)"]),
        "",
        f"Item ID chỉ có ở A ({len(result['item_only_a'])}):",
        *([f"  - {x}" for x in result['item_only_a'][:15]] or ["  (không)"]),
        f"Item ID chỉ có ở B ({len(result['item_only_b'])}):",
        *([f"  - {x}" for x in result['item_only_b'][:15]] or ["  (không)"]),
    ]
    if result["item_dup_a"]:
        lines += ["", f"Item ID trùng trong A: {', '.join(result['item_dup_a'][:10])}"]
    if result["item_dup_b"]:
        lines += [f"Item ID trùng trong B: {', '.join(result['item_dup_b'][:10])}"]
    return "\n".join(lines)