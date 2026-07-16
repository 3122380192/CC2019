"""Bridge tới ChestEMB — parse dữ liệu & chạy AutoWorkflow."""

from __future__ import annotations

import os
import sys

CHEST_EMB_DIR = os.environ.get(
    "CHEST_EMB_DIR",
    r"E:\AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\vibecoder\ChestEMB",
)


class _SignalAdapter:
    def __init__(self, callback) -> None:
        self._callback = callback

    def emit(self, *args) -> None:
        self._callback(*args)


class EmbWorkflowGuiAdapter:
    """Adapter tối thiểu để AutoWorkflow của ChestEMB chạy trong ACC2019 (tkinter)."""

    def __init__(self, panel) -> None:
        self.panel = panel
        self.current_folder = None
        self.status_signal = _SignalAdapter(self._on_status)
        self.progress_signal = _SignalAdapter(lambda _v: None)
        self.show_success_toast_signal = _SignalAdapter(self._on_success)

    def _on_status(self, msg, _color="#00ff41") -> None:
        self.flash_status(msg)

    def _on_success(self, msg) -> None:
        self.panel.app.log(f"[EMB] {msg}", "success")

    def flash_status(self, msg, color="#00ff41") -> None:
        tag = "success" if "00ff" in color.lower() or "58d7" in color.lower() else "accent"
        if "ff0000" in color.lower() or "ff33" in color.lower():
            tag = "danger"
        self.panel.app.root.after(0, lambda m=msg, t=tag: self.panel.app.log(f"[EMB] {m}", t))

    def on_create_folder(self) -> None:
        self.panel.ensure_folder()


def ensure_chest_emb_path() -> str:
    if not os.path.isdir(CHEST_EMB_DIR):
        raise FileNotFoundError(f"Không tìm thấy ChestEMB: {CHEST_EMB_DIR}")
    if CHEST_EMB_DIR not in sys.path:
        sys.path.insert(0, CHEST_EMB_DIR)
    return CHEST_EMB_DIR


def load_emb_logic():
    ensure_chest_emb_path()
    import logic  # noqa: WPS433 — ChestEMB package

    return logic


def load_auto_workflow():
    """Dùng emb_auto local (logic gốc, không PySide6, timeout ổn định)."""
    from modules.emb_auto import AutoWorkflow

    return AutoWorkflow