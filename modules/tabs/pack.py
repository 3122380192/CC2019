"""Tab Đóng gói + Photoshop batch."""

from __future__ import annotations

import tkinter as tk
from typing import Any

from modules.registry import COLOR_PACK, TabSpec


def build(app: Any, parent: tk.Misc, colors: dict) -> Any:
    from modules.pack_panel import PackPanel

    parent.columnconfigure(0, weight=1)
    parent.rowconfigure(0, weight=1)
    return PackPanel(parent, app)


def cleanup(app: Any) -> None:
    panel = getattr(app, "pack_panel", None)
    if panel is not None and hasattr(panel, "destroy"):
        panel.destroy()


SPEC = TabSpec(
    id="pack",
    label="Đóng gói",
    accent=COLOR_PACK,
    default_size=(520, 480),
    order=50,
    panel_attr="pack_panel",
    build=build,
    cleanup=cleanup,
)
