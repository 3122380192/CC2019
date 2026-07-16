"""Tab Game LAN."""

from __future__ import annotations

import tkinter as tk
from typing import Any

from modules.registry import COLOR_GAME, TabSpec


def build(app: Any, parent: tk.Misc, colors: dict) -> Any:
    from modules.game.lobby import GameLobbyPanel

    parent.columnconfigure(0, weight=1)
    parent.rowconfigure(0, weight=1)
    return GameLobbyPanel(parent, app)


def cleanup(app: Any) -> None:
    panel = getattr(app, "game_panel", None)
    if panel is not None and hasattr(panel, "destroy"):
        panel.destroy()


SPEC = TabSpec(
    id="game",
    label="Game LAN",
    accent=COLOR_GAME,
    default_size=(720, 560),
    order=60,
    panel_attr="game_panel",
    build=build,
    cleanup=cleanup,
)
