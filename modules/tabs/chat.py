"""Tab Chat LAN."""

from __future__ import annotations

import tkinter as tk
from typing import Any

from modules.registry import COLOR_CHAT, TabSpec


def build(app: Any, parent: tk.Misc, colors: dict) -> Any:
    from modules.chat_lan import ChatLanPanel

    parent.columnconfigure(0, weight=1)
    parent.rowconfigure(0, weight=1)
    return ChatLanPanel(parent, app)


def cleanup(app: Any) -> None:
    panel = getattr(app, "chat_panel", None)
    if panel is not None and hasattr(panel, "destroy"):
        panel.destroy()


SPEC = TabSpec(
    id="chat",
    label="Chat LAN",
    accent=COLOR_CHAT,
    default_size=(520, 420),
    order=70,
    panel_attr="chat_panel",
    build=build,
    cleanup=cleanup,
)
