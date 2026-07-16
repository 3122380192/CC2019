"""
ACC2019 — Registry trung tâm.

Thêm TAB mới:
  1. Tạo file modules/tabs/my_tab.py
  2. Viết hàm build(app, parent, colors) + TabSpec
  3. Đăng ký trong modules/tabs/__init__.py (ALL_TABS)

Thêm SẢN PHẨM CSV Loki:
  - Sửa csv_reader/products_config.json  (nhanh)
  - hoặc gọi csv_reader.config.add_product(...)  (code)

Sửa 1 tab / 1 panel: chỉ mở file tab đó, không đụng acc2019.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

# ── Màu tab (đổi 1 chỗ → toàn app) ─────────────────────────────
COLOR_LINKS = "#66ccff"
COLOR_CSV = "#a78bfa"
COLOR_GAME = "#ff6bcb"
COLOR_CHAT = "#38bdf8"
COLOR_MUSIC = "#c084fc"
COLOR_PACK = "#34d399"
COLOR_PRODUCE = "#00e676"  # fallback nếu theme không có success
COLOR_ADOBE = "#00d2ff"
COLOR_TOOLS = "#f0abfc"


BuildFn = Callable[[Any, Any, dict], Any]
"""build(app, parent_frame, colors) -> panel | None | dict"""

CleanupFn = Callable[[Any], None]
"""cleanup(app) — gỡ panel khi đóng app"""


@dataclass
class TabSpec:
    """Khai báo 1 tab. Thêm tab = thêm 1 TabSpec vào ALL_TABS."""

    id: str
    label: str
    accent: str
    default_size: tuple[int, int] = (480, 400)
    order: int = 100
    # Tên attribute gắn panel lên app (vd "emb_panel", "csv_panel")
    panel_attr: str | None = None
    # Hàm dựng UI vào parent
    build: BuildFn | None = None
    # Gọi khi đóng app (stop thread, destroy panel…)
    cleanup: CleanupFn | None = None
    # Bật/tắt tab mà không xóa code
    enabled: bool = True
    # Ghi chú cho dev
    note: str = ""

    def resolve_accent(self, colors: dict) -> str:
        """Ưu tiên màu theme nếu có key trùng id / label quen thuộc."""
        key_map = {
            "produce": "success",
            "csv": "csv",
            "adobe": "accent",
            "pack": "success",
        }
        k = key_map.get(self.id)
        if k and colors.get(k):
            return colors[k]
        return self.accent


class TabRegistry:
    """Danh sách tab có thứ tự — dùng cho setup_ui / show_tab / prefs."""

    def __init__(self, specs: Sequence[TabSpec] | None = None) -> None:
        self._specs: dict[str, TabSpec] = {}
        if specs:
            for s in specs:
                self.register(s)

    def register(self, spec: TabSpec) -> None:
        self._specs[spec.id] = spec

    def get(self, tab_id: str) -> TabSpec | None:
        return self._specs.get(tab_id)

    def enabled_tabs(self) -> list[TabSpec]:
        return sorted(
            (s for s in self._specs.values() if s.enabled),
            key=lambda s: (s.order, s.id),
        )

    def default_sizes(self) -> dict[str, tuple[int, int]]:
        return {s.id: s.default_size for s in self.enabled_tabs()}

    def ids(self) -> list[str]:
        return [s.id for s in self.enabled_tabs()]

    def prepare_frames(self, app: Any, content: Any, colors: dict) -> None:
        """Tạo frame rỗng cho mọi tab — chưa build panel (lazy)."""
        import tkinter as tk

        app.tab_frames = getattr(app, "tab_frames", {})
        app._tabs_built = getattr(app, "_tabs_built", set())
        bg = colors.get("bg", "#0c0c14")
        for spec in self.enabled_tabs():
            if spec.id not in app.tab_frames:
                app.tab_frames[spec.id] = tk.Frame(content, bg=bg)
            if spec.panel_attr and not hasattr(app, spec.panel_attr):
                setattr(app, spec.panel_attr, None)

    def ensure_tab(self, app: Any, tab_id: str, colors: dict) -> bool:
        """Build tab lần đầu mở. Trả True nếu tab sẵn sàng."""
        import tkinter as tk

        built: set = getattr(app, "_tabs_built", None) or set()
        app._tabs_built = built
        if tab_id in built:
            return True
        spec = self.get(tab_id)
        if not spec or not spec.enabled:
            return False
        frame = getattr(app, "tab_frames", {}).get(tab_id)
        if frame is None:
            return False

        panel = None
        if spec.build:
            try:
                panel = spec.build(app, frame, colors)
            except Exception as exc:
                danger = colors.get("danger", "#ff1744")
                bg = colors.get("bg", "#0c0c14")
                tk.Label(
                    frame,
                    text=f"Tab «{spec.label}» lỗi: {exc}",
                    fg=danger,
                    bg=bg,
                    font=("Segoe UI", 8),
                    wraplength=360,
                    justify="left",
                ).pack(anchor="w", padx=6, pady=6)
                if hasattr(app, "log"):
                    try:
                        app.log(f"Tab {spec.id} lỗi: {exc}", "danger")
                    except Exception:
                        pass
                panel = None

        if spec.panel_attr:
            # build có thể trả panel trực tiếp, hoặc dict{"panel": ...}
            if isinstance(panel, dict):
                setattr(app, spec.panel_attr, panel.get("panel"))
                for k, v in panel.items():
                    if k != "panel" and not k.startswith("_"):
                        setattr(app, k, v)
            else:
                setattr(app, spec.panel_attr, panel)

        built.add(tab_id)
        self._after_tab_built(app, tab_id)
        return True

    def _after_tab_built(self, app: Any, tab_id: str) -> None:
        """Hook sau khi build tab (kéo thả, backend…)."""
        if tab_id == "produce":
            emb = getattr(app, "emb_panel", None)
            if emb is not None and hasattr(emb, "start_backend"):
                try:
                    emb.start_backend()
                except Exception:
                    pass
            if hasattr(app, "setup_drag_and_drop"):
                try:
                    app._drag_drop_hooked = False
                    app.setup_drag_and_drop()
                except Exception:
                    pass
        elif tab_id == "csv":
            panel = getattr(app, "csv_panel", None)
            if panel is not None and hasattr(panel, "setup_drop"):
                try:
                    panel.setup_drop()
                except Exception:
                    pass

    def build_all(self, app: Any, content: Any, colors: dict) -> None:
        """Tạo frame + build mọi tab (eager — dùng khi cần full)."""
        self.prepare_frames(app, content, colors)
        for spec in self.enabled_tabs():
            self.ensure_tab(app, spec.id, colors)

    def cleanup_all(self, app: Any) -> None:
        for spec in self._specs.values():
            if spec.cleanup:
                try:
                    spec.cleanup(app)
                except Exception:
                    pass
            elif spec.panel_attr:
                panel = getattr(app, spec.panel_attr, None)
                if panel is not None and hasattr(panel, "destroy"):
                    try:
                        panel.destroy()
                    except Exception:
                        pass


# Singleton app-level (gán sau khi load tabs)
_APP_REGISTRY: TabRegistry | None = None


def get_registry() -> TabRegistry:
    global _APP_REGISTRY
    if _APP_REGISTRY is None:
        from modules.tabs import create_registry

        _APP_REGISTRY = create_registry()
    return _APP_REGISTRY


def reset_registry() -> None:
    """Test / reload hot — xóa cache registry."""
    global _APP_REGISTRY
    _APP_REGISTRY = None
