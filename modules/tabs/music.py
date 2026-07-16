"""Tab Nhạc YouTube (audio)."""

from __future__ import annotations

import tkinter as tk
from typing import Any

from modules.registry import COLOR_MUSIC, TabSpec


def build(app: Any, parent: tk.Misc, colors: dict) -> Any:
    from modules.music_panel import MusicPanel

    parent.columnconfigure(0, weight=1)
    parent.rowconfigure(0, weight=1)
    return MusicPanel(parent, app)


def cleanup(app: Any) -> None:
    panel = getattr(app, "music_panel", None)
    if panel is not None and hasattr(panel, "destroy"):
        panel.destroy()


SPEC = TabSpec(
    id="music",
    label="Nhạc",
    accent=COLOR_MUSIC,
    default_size=(480, 400),
    order=80,
    panel_attr="music_panel",
    build=build,
    cleanup=cleanup,
)
