"""Copy mapped Loki columns to clipboard format."""

from __future__ import annotations

from csv_reader.config import AppConfig, LokiProduct
from csv_reader.loki_mapper import format_mapped, map_data
from csv_reader.reader import CsvData


def build_copy_payload(
    data: CsvData,
    product: LokiProduct,
    config: AppConfig,
    *,
    row_indices: list[int] | None = None,
) -> str:
    columns, rows = map_data(data, product)
    if row_indices is not None:
        rows = [rows[i] for i in row_indices if 0 <= i < len(rows)]
    return format_mapped(
        rows,
        columns,
        separator=config.copy_separator,
        include_header=config.include_header,
    )