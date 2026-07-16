"""Tab Tiện ích — công cụ phụ trợ sản xuất."""

from __future__ import annotations

import tkinter as tk
from typing import Any

from modules.registry import COLOR_TOOLS, TabSpec


def build(app: Any, parent: tk.Misc, colors: dict) -> Any:
    from modules.tools_panel import ToolsPanel

    parent.columnconfigure(0, weight=1)
    parent.rowconfigure(0, weight=1)
    return ToolsPanel(parent, app)


def cleanup(app: Any) -> None:
    panel = getattr(app, "tools_panel", None)
    if panel is not None and hasattr(panel, "destroy"):
        panel.destroy()


SPEC = TabSpec(
    id="tools",
    label="Tiện ích",
    accent=COLOR_TOOLS,
    default_size=(500, 560),
    order=55,  # sau Đóng gói
    panel_attr="tools_panel",
    build=build,
    cleanup=cleanup,
    note="QR · OCR · backup · checklist · đổi tên · sắp ảnh",
)
