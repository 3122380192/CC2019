"""Tab Sản xuất — drop Patch/DXF/Spot + panel EMB."""

from __future__ import annotations

import tkinter as tk
from typing import Any

from modules.registry import COLOR_PRODUCE, TabSpec

DXF_MIN_MATCH = 95.0


def build(app: Any, parent: tk.Misc, colors: dict) -> Any:
    from modules.emb_panel import EmbProducePanel

    bg = colors.get("bg", "#0c0c14")
    card = colors.get("card", "#141424")
    muted = colors.get("muted", "#82829c")
    accent = colors.get("accent", "#00d2ff")
    success = colors.get("success", COLOR_PRODUCE)
    danger = colors.get("danger", "#ff1744")

    parent.columnconfigure(0, weight=1)
    parent.columnconfigure(1, weight=1)
    parent.columnconfigure(2, weight=1)
    parent.rowconfigure(2, weight=1)

    tools = (
        ("Patch", "Kéo thả", success, "patch_drop_zone", "patch_drop_col", app.select_patch_image),
        ("DXF", "Kéo thả", accent, "dxf_drop_zone", "dxf_drop_col", app.select_dxf_image),
        ("Spot W1", "Kéo thả", danger, "spot_drop_zone", "spot_drop_col", app.select_spot_color_image),
    )
    for i, (title_txt, drop_txt, fg, attr, col_attr, cmd) in enumerate(tools):
        col = tk.Frame(parent, bg=card, bd=0, highlightthickness=0)
        col.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 1, 0 if i == 2 else 1))
        setattr(app, col_attr, col)
        tk.Label(col, text=title_txt, font=("Segoe UI", 7, "bold"), fg=fg, bg=card).pack(
            anchor="w", padx=2,
        )
        zone = app.create_drop_zone(col, drop_txt, fg, card, cmd, wraplength=80, height=1)
        zone.pack(fill=tk.X, padx=2, pady=(0, 1))
        setattr(app, attr, zone)

    opts = tk.Frame(parent, bg=bg)
    opts.grid(row=1, column=0, columnspan=3, sticky="ew")

    app.auto_dxf_var = tk.BooleanVar(value=True)
    tk.Checkbutton(
        opts, text="Patch→DXF", variable=app.auto_dxf_var,
        font=("Segoe UI", 6), fg=muted, bg=bg,
        activebackground=bg, activeforeground=success,
        selectcolor=card,
    ).pack(side=tk.LEFT)

    min_match = float(getattr(app, "DXF_MIN_MATCH", DXF_MIN_MATCH))
    app.dxf_skip_low_var = tk.BooleanVar(value=True)
    tk.Checkbutton(
        opts, text=f"DXF<{int(min_match)}% skip",
        variable=app.dxf_skip_low_var,
        font=("Segoe UI", 6), fg=muted, bg=bg,
        activebackground=bg, activeforeground=danger,
        selectcolor=card,
    ).pack(side=tk.LEFT, padx=(3, 0))

    app.queue_var = tk.StringVar(value="")
    tk.Label(
        opts, textvariable=app.queue_var,
        font=("Segoe UI", 6), fg=success, bg=bg,
    ).pack(side=tk.RIGHT)

    panel = EmbProducePanel(parent, app)
    panel.frame.grid(row=2, column=0, columnspan=3, sticky="nsew")
    return panel


def cleanup(app: Any) -> None:
    panel = getattr(app, "emb_panel", None)
    if panel is not None and hasattr(panel, "destroy"):
        panel.destroy()


SPEC = TabSpec(
    id="produce",
    label="Sản xuất",
    accent=COLOR_PRODUCE,
    default_size=(480, 460),
    order=10,
    panel_attr="emb_panel",
    build=build,
    cleanup=cleanup,
    note="Patch / DXF / Spot + EMB portal",
)
