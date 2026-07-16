"""Tab CSV Loki — đọc CSV / copy theo sản phẩm."""

from __future__ import annotations

import tkinter as tk
from typing import Any

from modules.registry import COLOR_CSV, TabSpec


def build(app: Any, parent: tk.Misc, colors: dict) -> Any:
    from modules.csv_panel import CsvLokiPanel

    parent.columnconfigure(0, weight=1)
    return CsvLokiPanel(parent, app)


SPEC = TabSpec(
    id="csv",
    label="CSV Loki",
    accent=COLOR_CSV,
    default_size=(470, 360),
    order=30,
    panel_attr="csv_panel",
    build=build,
    note="Sản phẩm: csv_reader/products_config.json",
)
