"""Loki-style column mapping — ported from E:\\Loki\\tool.html."""

from __future__ import annotations

from csv_reader.config import LokiProduct
from csv_reader.reader import CsvData


def _headers_lower(headers: list[str]) -> list[str]:
    return [h.strip().lower() for h in headers]


def _get_by_headers(row: list[str], headers_lower: list[str], candidates: list[str]) -> str:
    for cand in candidates:
        key = cand.lower()
        if key in headers_lower:
            idx = headers_lower.index(key)
            if idx < len(row):
                return row[idx]
    return ""


def _has_artwork_column(target_cols: list[str]) -> bool:
    for col in target_cols:
        c = col.lower()
        if any(k in c for k in ("artwork", "front", "back", "link", "url")):
            return True
    return False


def map_row(
    row: list[str],
    headers: list[str],
    target_cols: list[str],
) -> list[str]:
    headers_lower = _headers_lower(headers)
    has_artwork = _has_artwork_column(target_cols)
    values: list[str] = []

    for col in target_cols:
        col_lower = col.lower().strip()

        if any(k in col_lower for k in ("po-stt",)) or col_lower in ("po", "p-o") or "production order" in col_lower:
            val = _get_by_headers(row, headers_lower, ["PO", "Item Input", "Order ID"])
        elif "item input" in col_lower:
            val = _get_by_headers(row, headers_lower, ["Item Input"])
        elif "item id" in col_lower or "item-id" in col_lower:
            val = _get_by_headers(row, headers_lower, ["Item ID", "Item ID PO", "Order ID"])
        elif col_lower in ("quantity", "qty"):
            val = _get_by_headers(row, headers_lower, ["Quantity"])
            if not val and not has_artwork:
                val = _get_by_headers(row, headers_lower, ["Artwork Front", "Quantity"])
        elif "artwork front" in col_lower or col_lower in ("front", "artwork-front"):
            val = _get_by_headers(row, headers_lower, ["Artwork Front"])
        elif "artwork back" in col_lower or col_lower in ("back", "artwork-back"):
            val = _get_by_headers(row, headers_lower, ["Artwork Back"])
        elif col_lower == "size":
            val = _get_by_headers(row, headers_lower, ["Size", "Variant Name"])
        elif col_lower == "color":
            val = _get_by_headers(row, headers_lower, ["Color"])
        elif col_lower in ("print side", "print-side", "side", "print-val"):
            val = _get_by_headers(row, headers_lower, ["Print Side"])
        elif col_lower in ("variant name", "variant-name"):
            val = _get_by_headers(row, headers_lower, ["Variant Name"])
        elif any(k in col_lower for k in ("product code", "variant code", "type(product code)", "type")):
            val = _get_by_headers(row, headers_lower, ["Product Code", "Variant Code"])
        elif "pack" in col_lower:
            val = _get_by_headers(row, headers_lower, ["Variant Name", "Print Side"])
        elif "layer" in col_lower:
            val = _get_by_headers(row, headers_lower, ["Variant Name", "Customize 1"])
        else:
            val = ""
            for idx, h in enumerate(headers_lower):
                if h and (h in col_lower or col_lower in h):
                    if idx < len(row):
                        val = row[idx]
                        break
            if not val:
                if "size" in col_lower or "variant" in col_lower:
                    val = _get_by_headers(row, headers_lower, ["Size", "Variant Name"])
                elif "color" in col_lower:
                    val = _get_by_headers(row, headers_lower, ["Color"])
                elif "print" in col_lower:
                    val = _get_by_headers(row, headers_lower, ["Print Side"])

        values.append(val)

    return values


def map_data(data: CsvData, product: LokiProduct) -> tuple[list[str], list[list[str]]]:
    cols = product.columns
    rows = [map_row(row, data.headers, cols) for row in data.rows]
    return cols, rows


def format_mapped(rows: list[list[str]], columns: list[str], *, separator: str = "\t", include_header: bool = False) -> str:
    lines: list[str] = []
    if include_header:
        lines.append(separator.join(columns))
    lines.extend(separator.join(r) for r in rows)
    return "\n".join(lines)