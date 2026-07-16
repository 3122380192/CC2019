"""Cửa sổ Cài đặt — giao diện, cỡ chữ, theme, FX, tùy chọn EMB."""

from __future__ import annotations

import json
import os
import tkinter as tk
from tkinter import ttk

from modules.theme_manager import THEMES, CATEGORY_LABELS, DEFAULT_THEME_ID

TEXT_SIZE_MIN = 5
TEXT_SIZE_MAX = 11
CONSOLE_H_MIN = 1
CONSOLE_H_MAX = 8


def _load_prefs(path: str) -> dict:
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_prefs(path: str, updates: dict) -> None:
    data = _load_prefs(path)
    data.update(updates)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except OSError:
        pass


class SettingsDialog:
    """Popup Settings gọn — áp dụng ngay + lưu config."""

    def __init__(self, app) -> None:
        self.app = app
        self.root = app.root
        self.base_dir = getattr(app, "base_dir", os.getcwd())
        self.config_path = os.path.join(self.base_dir, "acc2019_window.json")
        self.prefs = _load_prefs(self.config_path)
        self.win: tk.Toplevel | None = None

        colors = {}
        if getattr(app, "theme_mgr", None):
            colors = app.theme_mgr.colors
        self.bg = colors.get("bg", "#0c0c14")
        self.card = colors.get("card", "#141424")
        self.text = colors.get("text", "#ffffff")
        self.muted = colors.get("muted", "#82829c")
        self.accent = colors.get("accent", "#00d2ff")
        self.success = colors.get("success", "#00e676")
        self.danger = colors.get("danger", "#ff1744")
        self.hover = colors.get("hover", "#23233c")

    def show(self) -> None:
        if self.win is not None:
            try:
                self.win.lift()
                self.win.focus_force()
                return
            except tk.TclError:
                self.win = None

        win = tk.Toplevel(self.root)
        self.win = win
        win.title("Cài đặt ACC2019")
        win.configure(bg=self.bg)
        win.geometry("390x520")
        win.minsize(350, 460)
        win.attributes("-topmost", True)
        win.transient(self.root)

        # Header
        hdr = tk.Frame(win, bg=self.card)
        hdr.pack(fill=tk.X)
        tk.Label(
            hdr, text="⚙  Cài đặt", font=("Segoe UI", 10, "bold"),
            fg=self.accent, bg=self.card, padx=8, pady=6,
        ).pack(side=tk.LEFT)
        tk.Button(
            hdr, text="×", font=("Segoe UI", 10), bg=self.card, fg=self.muted,
            activebackground=self.card, activeforeground=self.danger,
            bd=0, padx=8, cursor="hand2", command=win.destroy,
        ).pack(side=tk.RIGHT)

        body = tk.Frame(win, bg=self.bg)
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)

        # ── 1. Giao diện ──
        self._section(body, "Giao diện")

        # Theme
        row = tk.Frame(body, bg=self.bg)
        row.pack(fill=tk.X, pady=2)
        tk.Label(row, text="Theme", font=("Segoe UI", 8), fg=self.muted, bg=self.bg, width=14, anchor="w").pack(side=tk.LEFT)
        theme_id = self.prefs.get("theme") or (
            self.app.theme_mgr.theme_id if getattr(self.app, "theme_mgr", None) else DEFAULT_THEME_ID
        )
        self.theme_var = tk.StringVar(value=THEMES.get(theme_id, THEMES[DEFAULT_THEME_ID])["name"])
        # list display names with id mapping
        self._theme_map = {t["name"]: tid for tid, t in THEMES.items()}
        theme_names = []
        for cat in ("classic", "weather", "hero", "anime", "game"):
            for tid, t in THEMES.items():
                if t.get("category") == cat:
                    theme_names.append(t["name"])
        self.theme_combo = ttk.Combobox(
            row, textvariable=self.theme_var, values=theme_names,
            state="readonly", font=("Segoe UI", 8), width=18,
        )
        self.theme_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.theme_combo.bind("<<ComboboxSelected>>", self._on_theme_pick)

        # Text size
        row = tk.Frame(body, bg=self.bg)
        row.pack(fill=tk.X, pady=4)
        tk.Label(row, text="Cỡ chữ", font=("Segoe UI", 8), fg=self.muted, bg=self.bg, width=14, anchor="w").pack(side=tk.LEFT)
        cur_sz = int(self.prefs.get("text_size", 6))
        if getattr(self.app, "emb_panel", None):
            cur_sz = getattr(self.app.emb_panel, "_text_size", cur_sz)
        self.size_var = tk.IntVar(value=cur_sz)
        self.size_label = tk.Label(row, text=str(cur_sz), font=("Consolas", 9, "bold"), fg=self.accent, bg=self.bg, width=3)
        tk.Button(row, text="A−", font=("Segoe UI", 8, "bold"), bg=self.card, fg=self.muted,
                  bd=0, padx=6, cursor="hand2", command=lambda: self._bump_size(-1)).pack(side=tk.LEFT)
        self.size_label.pack(side=tk.LEFT, padx=4)
        tk.Button(row, text="A+", font=("Segoe UI", 8, "bold"), bg=self.card, fg=self.accent,
                  bd=0, padx=6, cursor="hand2", command=lambda: self._bump_size(1)).pack(side=tk.LEFT)
        self.size_scale = tk.Scale(
            row, from_=TEXT_SIZE_MIN, to=TEXT_SIZE_MAX, orient=tk.HORIZONTAL,
            variable=self.size_var, showvalue=0, length=120,
            bg=self.bg, fg=self.text, troughcolor=self.card,
            highlightthickness=0, bd=0, command=self._on_size_scale,
        )
        self.size_scale.pack(side=tk.LEFT, padx=(8, 0))

        # Console height
        row = tk.Frame(body, bg=self.bg)
        row.pack(fill=tk.X, pady=2)
        tk.Label(row, text="Cao nhật ký", font=("Segoe UI", 8), fg=self.muted, bg=self.bg, width=14, anchor="w").pack(side=tk.LEFT)
        ch = int(self.prefs.get("console_height", 2))
        self.console_var = tk.IntVar(value=max(CONSOLE_H_MIN, min(CONSOLE_H_MAX, ch)))
        self.console_lbl = tk.Label(row, text=str(self.console_var.get()), font=("Consolas", 9, "bold"), fg=self.accent, bg=self.bg, width=3)
        self.console_lbl.pack(side=tk.LEFT)
        tk.Scale(
            row, from_=CONSOLE_H_MIN, to=CONSOLE_H_MAX, orient=tk.HORIZONTAL,
            variable=self.console_var, showvalue=0, length=160,
            bg=self.bg, fg=self.text, troughcolor=self.card,
            highlightthickness=0, bd=0, command=self._on_console_scale,
        ).pack(side=tk.LEFT, padx=(6, 0))

        # FX + always on top
        row = tk.Frame(body, bg=self.bg)
        row.pack(fill=tk.X, pady=4)
        self.fx_var = tk.BooleanVar(value=bool(self.prefs.get("fx_enabled", True)))
        self.top_var = tk.BooleanVar(value=bool(self.prefs.get("always_on_top", False)))
        tk.Checkbutton(
            row, text="Hiệu ứng nền (FX)", variable=self.fx_var,
            font=("Segoe UI", 8), fg=self.text, bg=self.bg,
            activebackground=self.bg, activeforeground=self.accent,
            selectcolor=self.card, command=self._on_fx_toggle,
        ).pack(side=tk.LEFT)
        tk.Checkbutton(
            row, text="Luôn trên cùng", variable=self.top_var,
            font=("Segoe UI", 8), fg=self.text, bg=self.bg,
            activebackground=self.bg, activeforeground=self.accent,
            selectcolor=self.card, command=self._on_top_toggle,
        ).pack(side=tk.LEFT, padx=(12, 0))

        # Night mode
        self._section(body, "Night mode · Ca đêm")
        row = tk.Frame(body, bg=self.bg)
        row.pack(fill=tk.X, pady=2)
        self.night_var = tk.BooleanVar(value=bool(self.prefs.get("night_mode", False)))
        self.night_auto_var = tk.BooleanVar(value=bool(self.prefs.get("night_auto", False)))
        tk.Checkbutton(
            row, text="Night mode (dịu mắt)", variable=self.night_var,
            font=("Segoe UI", 8), fg=self.text, bg=self.bg,
            activebackground=self.bg, activeforeground=self.accent,
            selectcolor=self.card, command=self._on_night_toggle,
        ).pack(side=tk.LEFT)
        tk.Checkbutton(
            row, text="Tự bật theo giờ", variable=self.night_auto_var,
            font=("Segoe UI", 8), fg=self.text, bg=self.bg,
            activebackground=self.bg, activeforeground=self.accent,
            selectcolor=self.card,
        ).pack(side=tk.LEFT, padx=(12, 0))
        row2 = tk.Frame(body, bg=self.bg)
        row2.pack(fill=tk.X, pady=2)
        tk.Label(row2, text="Từ giờ", font=("Segoe UI", 8), fg=self.muted, bg=self.bg).pack(side=tk.LEFT)
        self.night_from = tk.IntVar(value=int(self.prefs.get("night_from", 19)))
        self.night_to = tk.IntVar(value=int(self.prefs.get("night_to", 6)))
        tk.Spinbox(
            row2, from_=0, to=23, width=3, textvariable=self.night_from,
            font=("Consolas", 9), bg=self.card, fg=self.accent, buttonbackground=self.card,
        ).pack(side=tk.LEFT, padx=4)
        tk.Label(row2, text="→", font=("Segoe UI", 8), fg=self.muted, bg=self.bg).pack(side=tk.LEFT)
        tk.Spinbox(
            row2, from_=0, to=23, width=3, textvariable=self.night_to,
            font=("Consolas", 9), bg=self.card, fg=self.accent, buttonbackground=self.card,
        ).pack(side=tk.LEFT, padx=4)
        tk.Label(row2, text="(vd 19→6 = tối đến sáng)", font=("Segoe UI", 7), fg=self.muted, bg=self.bg).pack(
            side=tk.LEFT, padx=6,
        )
        row3 = tk.Frame(body, bg=self.bg)
        row3.pack(fill=tk.X, pady=2)
        self.night_contrast_var = tk.BooleanVar(value=bool(self.prefs.get("night_contrast", True)))
        tk.Checkbutton(
            row3, text="Tăng contrast chữ Night (rõ hơn, bold console)",
            variable=self.night_contrast_var,
            font=("Segoe UI", 8), fg=self.text, bg=self.bg,
            activebackground=self.bg, activeforeground=self.accent,
            selectcolor=self.card,
        ).pack(side=tk.LEFT)

        # ── Thời tiết Bắc Ninh ──
        self._section(body, "Theme thời tiết · Bắc Ninh")
        row = tk.Frame(body, bg=self.bg)
        row.pack(fill=tk.X, pady=2)
        self.weather_auto_var = tk.BooleanVar(value=bool(self.prefs.get("weather_auto", False)))
        tk.Checkbutton(
            row, text="Tự đổi theme theo thời tiết thật (Bắc Ninh)",
            variable=self.weather_auto_var,
            font=("Segoe UI", 8), fg=self.text, bg=self.bg,
            activebackground=self.bg, activeforeground=self.accent,
            selectcolor=self.card,
        ).pack(side=tk.LEFT)
        roww = tk.Frame(body, bg=self.bg)
        roww.pack(fill=tk.X, pady=2)
        tk.Label(roww, text="Cập nhật mỗi", font=("Segoe UI", 8), fg=self.muted, bg=self.bg).pack(side=tk.LEFT)
        self.weather_iv_var = tk.IntVar(value=int(self.prefs.get("weather_interval_min", 15)))
        tk.Spinbox(
            roww, from_=5, to=60, width=4, textvariable=self.weather_iv_var,
            font=("Consolas", 9), bg=self.card, fg=self.accent, buttonbackground=self.card,
        ).pack(side=tk.LEFT, padx=4)
        tk.Label(roww, text="phút", font=("Segoe UI", 8), fg=self.muted, bg=self.bg).pack(side=tk.LEFT)
        tk.Button(
            roww, text="Làm mới ngay", font=("Segoe UI", 7, "bold"),
            bg=self.card, fg=self.accent, bd=0, padx=8, cursor="hand2",
            command=self._refresh_weather,
        ).pack(side=tk.LEFT, padx=10)
        # live status
        wx_txt = "Chưa có dữ liệu"
        last = getattr(self.app, "_weather_last", None)
        if last is not None and getattr(last, "ok", False):
            wx_txt = last.detail_label() + f" → «{last.theme_name}»"
        elif last is not None and getattr(last, "error", ""):
            wx_txt = f"Lỗi: {last.error}"
        self.weather_status_lbl = tk.Label(
            body, text=wx_txt, font=("Segoe UI", 7), fg=self.muted, bg=self.bg,
            anchor="w", wraplength=360, justify="left",
        )
        self.weather_status_lbl.pack(fill=tk.X, pady=(0, 2))
        tk.Label(
            body,
            text="Map: dông→Sấm · mưa→Mưa · mây→Bão/Sương · quang→Bình minh/Hoàng hôn · đêm→Cực quang",
            font=("Segoe UI", 6), fg=self.muted, bg=self.bg, anchor="w", wraplength=360,
        ).pack(fill=tk.X)

        # ── Nghỉ mắt ──
        self._section(body, "Nhắc nghỉ · Ca dài")
        row = tk.Frame(body, bg=self.bg)
        row.pack(fill=tk.X, pady=2)
        self.break_en_var = tk.BooleanVar(value=bool(self.prefs.get("break_enabled", True)))
        tk.Checkbutton(
            row, text="Bật nhắc nghỉ mắt", variable=self.break_en_var,
            font=("Segoe UI", 8), fg=self.text, bg=self.bg,
            activebackground=self.bg, activeforeground=self.accent,
            selectcolor=self.card,
        ).pack(side=tk.LEFT)
        tk.Label(row, text="Mỗi", font=("Segoe UI", 8), fg=self.muted, bg=self.bg).pack(side=tk.LEFT, padx=(10, 2))
        self.break_iv_var = tk.IntVar(value=int(self.prefs.get("break_interval_min", 50)))
        tk.Spinbox(
            row, from_=15, to=120, width=4, textvariable=self.break_iv_var,
            font=("Consolas", 9), bg=self.card, fg=self.accent, buttonbackground=self.card,
        ).pack(side=tk.LEFT)
        tk.Label(row, text="phút · nghỉ", font=("Segoe UI", 8), fg=self.muted, bg=self.bg).pack(side=tk.LEFT, padx=2)
        self.break_min_var = tk.IntVar(value=int(self.prefs.get("break_min", 5)))
        tk.Spinbox(
            row, from_=1, to=30, width=3, textvariable=self.break_min_var,
            font=("Consolas", 9), bg=self.card, fg=self.accent, buttonbackground=self.card,
        ).pack(side=tk.LEFT)
        tk.Label(row, text="p", font=("Segoe UI", 8), fg=self.muted, bg=self.bg).pack(side=tk.LEFT, padx=2)

        # ── Cửa sổ (gọn) ──
        self._section(body, "Cửa sổ")
        snap_row = tk.Frame(body, bg=self.bg)
        snap_row.pack(fill=tk.X, pady=2)
        for text, side, fg in (
            ("◀", "left", self.accent),
            ("▶", "right", self.accent),
            ("◎", "center", self.muted),
            ("▣", "full", self.success),
        ):
            tk.Button(
                snap_row, text=text, font=("Segoe UI", 8, "bold"),
                bg=self.card, fg=fg, bd=0, padx=8, pady=2, cursor="hand2",
                command=lambda s=side: self._snap(s),
            ).pack(side=tk.LEFT, padx=(0, 3))
        tk.Button(
            snap_row, text="⇄", font=("Segoe UI", 8, "bold"),
            bg=self.card, fg=self.success, bd=0, padx=8, pady=2, cursor="hand2",
            command=self._cycle_monitor,
        ).pack(side=tk.LEFT, padx=(0, 3))

        btn_row = tk.Frame(body, bg=self.bg)
        btn_row.pack(fill=tk.X, pady=4)
        for text, cmd, fg in (
            ("Fit tab", self._fit_current_tab, self.accent),
            ("Reset size", self._reset_tab_sizes, self.muted),
            ("Backup", self._backup, self.success),
            ("Lịch sử", self._open_history, self.accent),
            ("Config", self._open_config_folder, self.muted),
        ):
            tk.Button(
                btn_row, text=text, font=("Segoe UI", 7, "bold"),
                bg=self.card, fg=fg, bd=0, padx=6, pady=3, cursor="hand2",
                command=cmd,
            ).pack(side=tk.LEFT, padx=(0, 3))

        # Hotkey hint
        tk.Label(
            body,
            text="Phím: Alt+E mở folder · Alt+V copy path folder · Alt+D diff · Alt+P pin · Ctrl+B auto",
            font=("Segoe UI", 7), fg=self.muted, bg=self.bg, wraplength=340, justify="left",
        ).pack(fill=tk.X, pady=(6, 0))

        # Footer
        foot = tk.Frame(win, bg=self.card)
        foot.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Button(
            foot, text="Áp dụng & Lưu", font=("Segoe UI", 9, "bold"),
            bg=self.accent, fg="#000", bd=0, padx=12, pady=6, cursor="hand2",
            command=self._apply_and_save,
        ).pack(side=tk.RIGHT, padx=8, pady=6)
        tk.Button(
            foot, text="Đóng", font=("Segoe UI", 8),
            bg=self.card, fg=self.muted, bd=0, padx=10, pady=6, cursor="hand2",
            command=win.destroy,
        ).pack(side=tk.RIGHT, pady=6)
        tk.Label(
            foot, text="Thay đổi cỡ chữ/theme áp dụng ngay",
            font=("Segoe UI", 7), fg=self.muted, bg=self.card,
        ).pack(side=tk.LEFT, padx=8)

        win.protocol("WM_DELETE_WINDOW", win.destroy)
        try:
            win.grab_set()
        except tk.TclError:
            pass

    def _section(self, parent, title: str) -> None:
        tk.Label(
            parent, text=title, font=("Segoe UI", 8, "bold"),
            fg=self.accent, bg=self.bg, anchor="w",
        ).pack(fill=tk.X, pady=(8, 2))
        tk.Frame(parent, bg=self.card, height=1).pack(fill=tk.X, pady=(0, 4))

    def _bump_size(self, delta: int) -> None:
        v = max(TEXT_SIZE_MIN, min(TEXT_SIZE_MAX, self.size_var.get() + delta))
        self.size_var.set(v)
        self.size_label.config(text=str(v))
        self._apply_text_live(v)

    def _on_size_scale(self, val) -> None:
        v = int(float(val))
        self.size_label.config(text=str(v))
        self._apply_text_live(v)

    def _apply_text_live(self, size: int) -> None:
        panel = getattr(self.app, "emb_panel", None)
        if panel and hasattr(panel, "set_text_size"):
            panel.set_text_size(size)
        elif panel and hasattr(panel, "_bump_text"):
            panel._text_size = size
            panel._apply_text_size()
            panel._save_text_size()

    def _on_console_scale(self, val) -> None:
        v = int(float(val))
        self.console_lbl.config(text=str(v))
        if hasattr(self.app, "set_console_height"):
            self.app.set_console_height(v)

    def _on_theme_pick(self, _e=None) -> None:
        name = self.theme_var.get()
        tid = self._theme_map.get(name)
        if tid and getattr(self.app, "theme_mgr", None):
            self.app.theme_mgr.set_theme(tid)

    def _on_fx_toggle(self) -> None:
        if hasattr(self.app, "set_fx_enabled"):
            self.app.set_fx_enabled(self.fx_var.get())

    def _on_night_toggle(self) -> None:
        if hasattr(self.app, "set_night_mode"):
            self.app.set_night_mode(self.night_var.get(), manual=True)

    def _refresh_weather(self) -> None:
        if hasattr(self.app, "refresh_weather_now"):
            self.app.refresh_weather_now()
        # refresh status label after short delay
        def _upd():
            last = getattr(self.app, "_weather_last", None)
            if last is not None and getattr(last, "ok", False) and hasattr(self, "weather_status_lbl"):
                try:
                    self.weather_status_lbl.config(
                        text=last.detail_label() + f" → «{last.theme_name}»",
                    )
                except tk.TclError:
                    pass
        try:
            self.root.after(1500, _upd)
        except Exception:
            pass

    def _on_top_toggle(self) -> None:
        try:
            self.root.attributes("-topmost", bool(self.top_var.get()))
        except tk.TclError:
            pass

    def _reset_tab_sizes(self) -> None:
        if hasattr(self.app, "reset_tab_sizes"):
            self.app.reset_tab_sizes()
            self.app.log("Đã reset size các tab về mặc định", "accent")

    def _fit_current_tab(self) -> None:
        tid = getattr(self.app, "active_tab", "produce")
        if hasattr(self.app, "_apply_tab_geometry"):
            self.app._apply_tab_geometry(tid, force_fit=True)
            self.app.log(f"Fit GUI tab: {tid}", "accent")

    def _open_config_folder(self) -> None:
        try:
            os.startfile(self.base_dir)
        except OSError:
            pass

    def _open_history(self) -> None:
        if hasattr(self.app, "open_history_file"):
            self.app.open_history_file()

    def _snap(self, side: str) -> None:
        if hasattr(self.app, "snap_window"):
            self.app.snap_window(side)

    def _cycle_monitor(self) -> None:
        if hasattr(self.app, "cycle_monitor_window"):
            self.app.cycle_monitor_window(1)

    def _backup(self) -> None:
        if hasattr(self.app, "backup_config"):
            self.app.backup_config()

    def _apply_and_save(self) -> None:
        updates = {
            "text_size": int(self.size_var.get()),
            "console_height": int(self.console_var.get()),
            "fx_enabled": bool(self.fx_var.get()),
            "always_on_top": bool(self.top_var.get()),
            "night_mode": bool(self.night_var.get()),
            "night_auto": bool(self.night_auto_var.get()),
            "night_from": int(self.night_from.get()),
            "night_to": int(self.night_to.get()),
            "night_contrast": bool(self.night_contrast_var.get()),
            "break_enabled": bool(self.break_en_var.get()),
            "break_interval_min": int(self.break_iv_var.get()),
            "break_min": int(self.break_min_var.get()),
            "weather_auto": bool(self.weather_auto_var.get()),
            "weather_interval_min": int(self.weather_iv_var.get()),
        }
        if hasattr(self.app, "set_night_mode"):
            self.app.set_night_mode(bool(self.night_var.get()), manual=True)
        if hasattr(self.app, "set_night_auto"):
            self.app.set_night_auto(
                bool(self.night_auto_var.get()),
                int(self.night_from.get()),
                int(self.night_to.get()),
            )
        if hasattr(self.app, "set_night_contrast"):
            self.app.set_night_contrast(bool(self.night_contrast_var.get()))
        if hasattr(self.app, "configure_break_reminder"):
            self.app.configure_break_reminder(
                enabled=bool(self.break_en_var.get()),
                interval_min=int(self.break_iv_var.get()),
                break_min=int(self.break_min_var.get()),
            )
        if hasattr(self.app, "set_weather_auto"):
            self.app.set_weather_auto(
                bool(self.weather_auto_var.get()),
                interval_min=int(self.weather_iv_var.get()),
            )
        name = self.theme_var.get()
        tid = self._theme_map.get(name)
        if tid:
            updates["theme"] = tid
            if getattr(self.app, "theme_mgr", None):
                self.app.theme_mgr.set_theme(tid)

        self._apply_text_live(updates["text_size"])
        if hasattr(self.app, "set_console_height"):
            self.app.set_console_height(updates["console_height"])
        if hasattr(self.app, "set_fx_enabled"):
            self.app.set_fx_enabled(updates["fx_enabled"])
        try:
            self.root.attributes("-topmost", updates["always_on_top"])
        except tk.TclError:
            pass

        _save_prefs(self.config_path, updates)
        if hasattr(self.app, "_save_ui_prefs"):
            try:
                self.app._save_ui_prefs()
            except Exception:
                pass
        self.app.log("Đã lưu cài đặt", "success")
        if self.win:
            self.win.destroy()
            self.win = None
