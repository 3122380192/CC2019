"""
Đăng ký TAB — thêm tab mới chỉ sửa file này + tạo modules/tabs/<ten>.py

Ví dụ tab mới:
    # modules/tabs/my_feature.py
    from modules.registry import TabSpec
    def build(app, parent, colors): ...
    SPEC = TabSpec(id="my", label="My", accent="#fff", order=90, build=build, panel_attr="my_panel")

    # rồi thêm vào ALL_TABS bên dưới
"""

from __future__ import annotations

from modules.registry import TabRegistry, TabSpec

from . import adobe, chat, csv_tab, game, links, music, pack, produce, tools

# ── Danh sách tab (thứ tự = order trong SPEC) ──────────────────
# Tắt tab: SPEC.enabled = False, hoặc comment dòng dưới.
ALL_TABS: list[TabSpec] = [
    produce.SPEC,
    links.SPEC,
    csv_tab.SPEC,
    adobe.SPEC,
    pack.SPEC,
    tools.SPEC,   # Tiện ích (đổi tên · sắp ảnh · đơn vị…)
    game.SPEC,
    chat.SPEC,
    music.SPEC,
]


def create_registry() -> TabRegistry:
    reg = TabRegistry()
    for spec in ALL_TABS:
        reg.register(spec)
    return reg


def tab_template() -> str:
    """Skeleton copy-paste khi tạo tab mới."""
    return '''"""Tab ... — mô tả ngắn."""

from __future__ import annotations

import tkinter as tk
from typing import Any

from modules.registry import TabSpec


def build(app: Any, parent: tk.Misc, colors: dict) -> Any:
    parent.columnconfigure(0, weight=1)
    parent.rowconfigure(0, weight=1)
    # from modules.xxx import MyPanel
    # return MyPanel(parent, app)
    tk.Label(
        parent, text="Hello",
        bg=colors.get("bg", "#0c0c14"),
        fg=colors.get("text", "#fff"),
    ).pack()
    return None


SPEC = TabSpec(
    id="mytab",
    label="My Tab",
    accent="#f0abfc",
    default_size=(480, 400),
    order=90,
    panel_attr="my_panel",
    build=build,
)
'''
