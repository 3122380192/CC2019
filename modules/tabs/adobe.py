"""Tab Adobe — cài/gỡ/mở Photoshop & Illustrator."""

from __future__ import annotations

import tkinter as tk
from typing import Any

from modules.registry import COLOR_ADOBE, TabSpec


def build(app: Any, parent: tk.Misc, colors: dict) -> Any:
    from acc2019_core import COLOR_ACCENT_AI

    bg = colors.get("bg", "#0c0c14")
    card = colors.get("card", "#141424")
    accent = colors.get("accent", COLOR_ADOBE)
    success = colors.get("success", "#00e676")
    danger = colors.get("danger", "#ff1744")

    toolbar = tk.Frame(parent, bg=bg)
    toolbar.pack(fill=tk.X)
    adobe_btns = (
        ("Làm mới", "btn_refresh", app.refresh_data, success),
        ("Đóng PS+AI", "btn_kill_all", app.force_close_all_processes, danger),
        ("Dọn tàn dư", "btn_clean", app.clean_adobe_remnants, accent),
        ("Tắt dịch vụ", "btn_disable_services", app.disable_adobe_services, COLOR_ACCENT_AI),
    )
    for text, attr, cmd, fg in adobe_btns:
        btn = app.create_flat_button(
            toolbar, text=text, bg=card, fg=fg,
            border_color=card, padx=4, pady=1, command=cmd,
        )
        btn.pack(side=tk.LEFT, padx=(0, 1))
        setattr(app, attr, btn)

    ps = app.create_app_card(parent, "Photoshop CC 2019", accent)
    app.ps_card = ps["card"]
    app.ps_status_label = ps["status"]
    app.btn_install_ps = ps["btn_install"]
    app.btn_uninstall_ps = ps["btn_uninstall"]
    app.btn_open_ps = ps["btn_open"]
    app.ps_progress_canvas = ps["progress_canvas"]
    app.ps_progress_rect = ps["progress_rect"]
    app.btn_install_ps.config(command=app.start_install_ps)
    app.btn_uninstall_ps.config(command=app.start_uninstall_ps)
    app.btn_open_ps.config(command=app.toggle_photoshop)

    app.btn_import_ps = app.create_flat_button(
        ps["card"], text="Nhập Actions/Scripts", bg=card, fg=accent,
        border_color=accent, padx=4, pady=1, command=app.import_ps_presets,
    )
    app.btn_import_ps.pack(fill=tk.X, padx=4, pady=(0, 1))

    ai = app.create_app_card(parent, "Illustrator CC 2019", COLOR_ACCENT_AI)
    app.ai_card = ai["card"]
    app.ai_status_label = ai["status"]
    app.btn_install_ai = ai["btn_install"]
    app.btn_uninstall_ai = ai["btn_uninstall"]
    app.btn_open_ai = ai["btn_open"]
    app.ai_progress_canvas = ai["progress_canvas"]
    app.ai_progress_rect = ai["progress_rect"]
    app.btn_install_ai.config(command=app.start_install_ai)
    app.btn_uninstall_ai.config(command=app.start_uninstall_ai)
    app.btn_open_ai.config(command=app.toggle_illustrator)

    # cập nhật UI trạng thái nếu core đã có
    if hasattr(app, "update_ps_ui"):
        try:
            app.update_ps_ui()
            app.update_ai_ui()
        except Exception:
            pass
    return None


SPEC = TabSpec(
    id="adobe",
    label="Adobe",
    accent=COLOR_ADOBE,
    default_size=(430, 300),
    order=40,
    panel_attr=None,
    build=build,
    note="Logic cài/gỡ nằm trong acc2019_core.py",
)
