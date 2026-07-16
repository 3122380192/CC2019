#!/usr/bin/env python3
"""CLI entry point for CSV Reader."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from csv_reader.config import load_config
from csv_reader.detector import detect_product
from csv_reader.loki_mapper import map_data
from csv_reader.reader import read_csv_file


def format_table(headers: list[str], rows: list[list[str]], max_rows: int = 20) -> str:
    widths = [len(h) for h in headers]
    display_rows = rows[:max_rows]

    for row in display_rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(cell))

    def fmt_row(cells: list[str]) -> str:
        parts = []
        for i, h in enumerate(headers):
            cell = cells[i] if i < len(cells) else ""
            parts.append(cell.ljust(widths[i]))
        return " | ".join(parts)

    sep = "-+-".join("-" * w for w in widths)
    lines = [fmt_row(headers), sep]
    lines.extend(fmt_row(r) for r in display_rows)

    if len(rows) > max_rows:
        lines.append(f"... ({len(rows) - max_rows} dòng còn lại)")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Đọc và hiển thị file CSV (Windows & Linux)",
    )
    parser.add_argument("file", nargs="?", help="Đường dẫn file CSV")
    parser.add_argument("-e", "--encoding", help="Bắt buộc encoding (utf-8, cp1252, ...)")
    parser.add_argument("-d", "--delimiter", help="Ký tự phân cách (, ; \\t |)")
    parser.add_argument("--no-header", action="store_true", help="File không có dòng tiêu đề")
    parser.add_argument("-n", "--max-rows", type=int, default=20, help="Số dòng hiển thị tối đa")
    parser.add_argument("--gui", action="store_true", help="Mở giao diện đồ họa")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.gui or not args.file:
        from csv_reader.gui import run_gui

        run_gui(initial_file=args.file)
        return 0

    try:
        data = read_csv_file(
            args.file,
            encoding=args.encoding,
            delimiter=args.delimiter,
            has_header=not args.no_header,
        )
    except (OSError, ValueError, csv.Error) as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 1

    config = load_config()
    det = detect_product(data, config)

    print(f"File     : {data.path}")
    print(f"Encoding : {data.encoding}")
    print(f"Delimiter: {repr(data.delimiter)}")
    print(f"Kích thước: {data.row_count} dòng x {data.column_count} cột")
    if det.product:
        print(f"Sản phẩm : {det.product.name} ({det.confidence}, {det.reason})")
        cols, rows = map_data(data, det.product)
        print(f"Cột copy : {' | '.join(cols)}")
        print()
        print(format_table(cols, rows, max_rows=args.max_rows))
    else:
        print("Sản phẩm : Không nhận diện")
        print()
        print(format_table(data.headers, data.rows, max_rows=args.max_rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())