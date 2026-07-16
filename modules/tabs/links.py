"""Tab Truy cập nhanh."""

from __future__ import annotations

import os
import tkinter as tk
from typing import Any

from modules.registry import COLOR_LINKS, TabSpec


def build(app: Any, parent: tk.Misc, colors: dict) -> Any:
    from modules.quick_links_panel import QuickLinksPanel

    cfg = os.path.join(getattr(app, "base_dir", "."), "quick_links.json")
    return QuickLinksPanel(parent, app, cfg)


SPEC = TabSpec(
    id="links",
    label="Truy cập",
    accent=COLOR_LINKS,
    default_size=(400, 290),
    order=20,
    panel_attr="quick_links_panel",
    build=build,
    note="Quick links JSON",
)
