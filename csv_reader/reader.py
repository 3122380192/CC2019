"""Core CSV reading utilities — cross-platform (Windows & Linux)."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "latin-1")


@dataclass
class CsvData:
    path: Path
    encoding: str
    delimiter: str
    headers: list[str]
    rows: list[list[str]]

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def column_count(self) -> int:
        return len(self.headers)


def detect_delimiter(sample: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return dialect.delimiter
    except csv.Error:
        return ","


def read_csv_file(
    path: str | Path,
    *,
    encoding: str | None = None,
    delimiter: str | None = None,
    has_header: bool = True,
) -> CsvData:
    file_path = Path(path).expanduser().resolve()

    if not file_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy file: {file_path}")

    raw = file_path.read_bytes()
    used_encoding = encoding or _detect_encoding(raw)
    text = raw.decode(used_encoding)
    used_delimiter = delimiter or detect_delimiter(text[:4096])

    reader = csv.reader(io.StringIO(text), delimiter=used_delimiter)
    all_rows = [list(row) for row in reader]

    if not all_rows:
        return CsvData(file_path, used_encoding, used_delimiter, [], [])

    if has_header:
        headers = all_rows[0]
        data_rows = all_rows[1:]
    else:
        col_count = max(len(r) for r in all_rows)
        headers = [f"Cột {i + 1}" for i in range(col_count)]
        data_rows = all_rows

    return CsvData(file_path, used_encoding, used_delimiter, headers, data_rows)


def _detect_encoding(raw: bytes) -> str:
    for enc in ENCODINGS:
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin-1"


def iter_rows(data: CsvData) -> Iterator[dict[str, str]]:
    for row in data.rows:
        padded = row + [""] * (len(data.headers) - len(row))
        yield dict(zip(data.headers, padded[: len(data.headers)]))