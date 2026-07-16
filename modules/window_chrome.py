"""Khung cửa sổ tùy chỉnh — kéo thả, ghi nhớ vị trí/size theo tab, không viền OS."""

from __future__ import annotations

import json
import os
import tkinter as tk

COLOR_BG = "#0c0c14"
COLOR_CARD = "#141424"
COLOR_MUTED = "#82829c"
COLOR_DANGER = "#ff1744"
COLOR_ACCENT = "#00d2ff"


class FramelessChrome:
    """Bọc root Tk: overrideredirect + thanh tiêu đề kéo + lưu geometry."""

    def __init__(
        self,
        root: tk.Tk,
        base_dir: str,
        title: str = "ACC2019",
        version: str = "2.9.1",
        *,
        default_size: tuple[int, int] = (470, 500),
        on_close=None,
    ) -> None:
        self.root = root
        self.base_dir = base_dir
        self.config_path = os.path.join(base_dir, "acc2019_window.json")
        self.on_close_cb = on_close
        self._drag_x = 0
        self._drag_y = 0
        self._title_lbl = None
        self._ver_lbl = None
        self._btn_close = None
        self._btn_min = None
        self._default_size = default_size

        cfg = self._load()
        w = int(cfg.get("width", default_size[0]))
        h = int(cfg.get("height", default_size[1]))
        x, y = cfg.get("x"), cfg.get("y")

        root.overrideredirect(True)
        root.configure(bg=COLOR_BG)
        geom = f"{w}x{h}"
        if x is not None and y is not None:
            geom += f"+{int(x)}+{int(y)}"
        root.geometry(geom)
        root.minsize(360, 260)

        self.shell = tk.Frame(root, bg=COLOR_BG, bd=0, highlightthickness=0)
        self.shell.pack(fill="both", expand=True)

        self.title_bar = tk.Frame(self.shell, bg=COLOR_CARD, height=16, bd=0, highlightthickness=0)
        self.title_bar.pack(fill="x", side="top")
        self.title_bar.pack_propagate(False)

        self._title_lbl = tk.Label(
            self.title_bar, text=title, font=("Segoe UI", 8, "bold"),
            fg=COLOR_ACCENT, bg=COLOR_CARD, bd=0,
        )
        self._title_lbl.pack(side="left", padx=(5, 0))
        self._ver_lbl = tk.Label(
            self.title_bar, text=f" v{version}", font=("Segoe UI", 7),
            fg=COLOR_MUTED, bg=COLOR_CARD, bd=0,
        )
        self._ver_lbl.pack(side="left")

        btn_style = dict(
            font=("Segoe UI", 8), bg=COLOR_CARD, fg=COLOR_MUTED,
            activebackground=COLOR_CARD, bd=0, padx=4, pady=0, cursor="hand2",
        )
        self._btn_close = tk.Button(
            self.title_bar, text="×", **btn_style, activeforeground=COLOR_DANGER,
            command=self._close,
        )
        self._btn_close.pack(side="right")
        self._btn_min = tk.Button(self.title_bar, text="—", **btn_style, command=self._minimize)
        self._btn_min.pack(side="right")
        # Snap nhanh (multi-monitor)
        self._snap_cb = None
        self._btn_snap = tk.Button(
            self.title_bar, text="⧉", **btn_style, command=self._snap_menu,
        )
        self._btn_snap.pack(side="right")

        # Content pack (không place full) — cửa sổ co theo nội dung, hết khoảng trắng
        self.bg_layer = tk.Frame(self.shell, bg=COLOR_BG, bd=0, highlightthickness=0)
        self.bg_layer.pack(fill="both", expand=True)

        self.content = tk.Frame(self.bg_layer, bg=COLOR_BG, bd=0, highlightthickness=0)
        self.content.pack(fill="both", expand=True, anchor="n")

        # ── Resize grips (kéo tự do chỉnh size) ──
        self._resize_edge = None  # "se" | "e" | "s"
        self._rz_start = (0, 0, 0, 0)  # x_root, y_root, w, h
        self._on_resize_end_cb = None

        grip_bg = COLOR_CARD
        # Góc dưới-phải
        self.grip_se = tk.Label(
            self.shell, text="⌟", font=("Segoe UI", 10),
            bg=grip_bg, fg=COLOR_MUTED, cursor="size_nw_se", bd=0,
        )
        self.grip_se.place(relx=1.0, rely=1.0, anchor="se", width=14, height=14)
        self.grip_se.bind("<Button-1>", lambda e: self._rz_start_at(e, "se"))
        self.grip_se.bind("<B1-Motion>", self._rz_drag)
        self.grip_se.bind("<ButtonRelease-1>", self._rz_end)
        # Cạnh phải
        self.grip_e = tk.Frame(self.shell, bg=COLOR_BG, cursor="sb_h_double_arrow", width=4, bd=0)
        self.grip_e.place(relx=1.0, rely=0.5, anchor="e", relheight=0.7, width=5)
        self.grip_e.bind("<Button-1>", lambda e: self._rz_start_at(e, "e"))
        self.grip_e.bind("<B1-Motion>", self._rz_drag)
        self.grip_e.bind("<ButtonRelease-1>", self._rz_end)
        # Cạnh dưới
        self.grip_s = tk.Frame(self.shell, bg=COLOR_BG, cursor="sb_v_double_arrow", height=4, bd=0)
        self.grip_s.place(relx=0.5, rely=1.0, anchor="s", relwidth=0.7, height=5)
        self.grip_s.bind("<Button-1>", lambda e: self._rz_start_at(e, "s"))
        self.grip_s.bind("<B1-Motion>", self._rz_drag)
        self.grip_s.bind("<ButtonRelease-1>", self._rz_end)

        self._bind_drag(self.title_bar)

    @property
    def mount(self) -> tk.Frame:
        return self.content

    def set_resize_callback(self, cb) -> None:
        """Gọi sau khi user thả resize (layout sync)."""
        self._on_resize_end_cb = cb

    def _rz_start_at(self, event: tk.Event, edge: str) -> None:
        self._resize_edge = edge
        try:
            self.root.update_idletasks()
            self._rz_start = (
                event.x_root, event.y_root,
                self.root.winfo_width(), self.root.winfo_height(),
            )
        except tk.TclError:
            self._resize_edge = None

    def _rz_drag(self, event: tk.Event) -> None:
        if not self._resize_edge:
            return
        sx, sy, sw, sh = self._rz_start
        dx = event.x_root - sx
        dy = event.y_root - sy
        min_w, min_h = self.root.minsize()
        w, h = sw, sh
        if self._resize_edge in ("se", "e"):
            w = max(min_w, sw + dx)
        if self._resize_edge in ("se", "s"):
            h = max(min_h, sh + dy)
        try:
            x, y = self.root.winfo_x(), self.root.winfo_y()
            self.root.geometry(f"{int(w)}x{int(h)}+{x}+{y}")
        except tk.TclError:
            pass

    def _rz_end(self, _event=None) -> None:
        self._resize_edge = None
        if self._on_resize_end_cb:
            try:
                self._on_resize_end_cb()
            except Exception:
                pass

    def apply_colors(self, colors: dict) -> None:
        """Áp theme cho chrome."""
        bg = colors.get("bg", COLOR_BG)
        card = colors.get("card", COLOR_CARD)
        muted = colors.get("muted", COLOR_MUTED)
        accent = colors.get("accent", COLOR_ACCENT)
        danger = colors.get("danger", COLOR_DANGER)

        self.root.configure(bg=bg)
        self.shell.configure(bg=bg)
        self.bg_layer.configure(bg=bg)
        self.content.configure(bg=bg)
        self.title_bar.configure(bg=card)
        if self._title_lbl:
            self._title_lbl.configure(bg=card, fg=accent)
        if self._ver_lbl:
            self._ver_lbl.configure(bg=card, fg=muted)
        for btn in (self._btn_close, self._btn_min, getattr(self, "_btn_snap", None)):
            if btn:
                btn.configure(bg=card, fg=muted, activebackground=card)
        if self._btn_close:
            self._btn_close.configure(activeforeground=danger)
        if getattr(self, "grip_se", None):
            self.grip_se.configure(bg=card, fg=muted)
        if getattr(self, "grip_e", None):
            self.grip_e.configure(bg=bg)
        if getattr(self, "grip_s", None):
            self.grip_s.configure(bg=bg)

    def set_size(self, width: int, height: int, *, keep_pos: bool = True) -> None:
        """Đổi kích thước cửa sổ (giữ vị trí nếu keep_pos)."""
        try:
            self.root.update_idletasks()
            min_w, min_h = self.root.minsize()
            w = max(min_w, int(width))
            h = max(min_h, int(height))
            if keep_pos:
                x, y = self.root.winfo_x(), self.root.winfo_y()
                self.root.geometry(f"{w}x{h}+{x}+{y}")
            else:
                self.root.geometry(f"{w}x{h}")
        except tk.TclError:
            pass

    def title_height(self) -> int:
        try:
            self.root.update_idletasks()
            return max(16, self.title_bar.winfo_height() or 16)
        except tk.TclError:
            return 16

    def set_snap_callback(self, cb) -> None:
        """cb(side: str) — app.snap_window."""
        self._snap_cb = cb

    def _snap_menu(self) -> None:
        menu = tk.Menu(
            self.root, tearoff=0, font=("Segoe UI", 8),
            bg=COLOR_CARD, fg="#eee", activebackground="#23233c",
            activeforeground=COLOR_ACCENT, bd=0,
        )
        for label, side in (
            ("Nửa trái", "left"),
            ("Nửa phải", "right"),
            ("Giữa", "center"),
            ("Full màn", "full"),
            ("Góc TL", "tl"),
            ("Góc TR", "tr"),
            ("Góc BL", "bl"),
            ("Góc BR", "br"),
        ):
            menu.add_command(
                label=label,
                command=lambda s=side: self._snap_cb(s) if self._snap_cb else None,
            )
        menu.add_separator()
        menu.add_command(
            label="⇄ Màn hình khác",
            command=lambda: self._snap_cb("cycle") if self._snap_cb else None,
        )
        try:
            menu.tk_popup(
                self._btn_snap.winfo_rootx(),
                self._btn_snap.winfo_rooty() + self._btn_snap.winfo_height(),
            )
        finally:
            menu.grab_release()

    def bind_drag(self, widget: tk.Misc) -> None:
        """Cho phép kéo cửa sổ từ vùng nền (header, v.v.)."""
        self._bind_drag(widget)

    def _bind_drag(self, widget: tk.Misc) -> None:
        widget.bind("<Button-1>", self._start_drag, add="+")
        widget.bind("<B1-Motion>", self._drag, add="+")
        for child in widget.winfo_children():
            if isinstance(child, tk.Button):
                continue
            self._bind_drag(child)

    def _start_drag(self, event: tk.Event) -> None:
        self._drag_x = event.x_root - self.root.winfo_x()
        self._drag_y = event.y_root - self.root.winfo_y()

    def _drag(self, event: tk.Event) -> None:
        self.root.geometry(f"+{event.x_root - self._drag_x}+{event.y_root - self._drag_y}")

    def _minimize(self) -> None:
        self.root.overrideredirect(False)
        self.root.iconify()
        self.root.bind("<Map>", self._on_restore, add="+")

    def _on_restore(self, _event=None) -> None:
        if self.root.state() == "normal":
            self.root.overrideredirect(True)
            self.root.unbind("<Map>")

    def _close(self) -> None:
        self.save_geometry()
        if self.on_close_cb:
            self.on_close_cb()
        else:
            self.root.destroy()

    def _load(self) -> dict:
        if not os.path.isfile(self.config_path):
            return {}
        try:
            with open(self.config_path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

    def merge_save(self, extra: dict | None = None) -> None:
        """Ghi config: geometry + extra (tab_sizes, last_tab, theme…)."""
        try:
            self.root.update_idletasks()
            data = self._load()
            geo = self.root.geometry()
            parts = geo.split("+")
            size = parts[0].split("x")
            data["width"] = int(size[0])
            data["height"] = int(size[1])
            if len(parts) >= 3:
                data["x"] = int(parts[1])
                data["y"] = int(parts[2])
            if extra:
                data.update(extra)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except (OSError, ValueError, tk.TclError):
            pass

    def save_geometry(self) -> None:
        self.merge_save()
