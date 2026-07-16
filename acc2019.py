"""ACC2019 — Adobe CC 2019 Hub.

Cấu trúc dễ mở rộng:
  • Thêm TAB     → modules/tabs/<ten>.py + khai báo trong modules/tabs/__init__.py
  • Thêm SẢN PHẨM → csv_reader/products_config.json  hoặc  csv_reader.config.add_product(...)
  • Sửa 1 panel  → chỉ mở file panel/tab đó (không cần đụng file này)
"""

import json
import os
import sys
import tkinter as tk
from tkinter import scrolledtext

from acc2019_core import (
    AdobeManagerApp,
    is_admin,
    COLOR_BG,
    COLOR_CARD,
    COLOR_TEXT,
    COLOR_MUTED,
    COLOR_ACCENT_PS,
    COLOR_ACCENT_AI,
    COLOR_SUCCESS,
    COLOR_DANGER,
)
from modules.csv_services import get_today_stats
from modules.emb_stats import get_emb_today_stats
from modules.sys_monitor import SysMonitorBar
from modules.window_chrome import FramelessChrome
from modules.theme_manager import (
    ThemeManager,
    AnimatedBackground,
    THEMES,
    CATEGORY_LABELS,
    apply_theme_to_module_colors,
    recolor_widget_tree,
    NIGHT_CONTRAST_BOOST,
)
from modules.settings_dialog import SettingsDialog
from modules.monitor_snap import apply_snap, cycle_monitor, list_monitors
from modules.backup_util import create_backup
from modules.break_reminder import BreakReminder
from modules.weather_live import WeatherThemeService, WeatherSnapshot
from modules.registry import (
    get_registry,
    COLOR_LINKS,
    COLOR_CSV,
    COLOR_GAME,
    COLOR_CHAT,
    COLOR_MUSIC,
    COLOR_PACK,
)

APP_NAME = "ACC2019"
VERSION = "3.6.2"
CONSOLE_H = 2
DXF_MIN_MATCH = 95.0

# Kích thước mặc định theo tab — lấy từ TabRegistry (modules/tabs/*)
_TAB_REG = get_registry()
TAB_SIZES: dict[str, tuple[int, int]] = _TAB_REG.default_sizes()
DEFAULT_TAB_ID = _TAB_REG.ids()[0] if _TAB_REG.ids() else "produce"


class ACC2019App(AdobeManagerApp):
    def __init__(self, root, *, chrome: FramelessChrome | None = None, theme_mgr: ThemeManager | None = None):
        self.chrome = chrome
        self.theme_mgr = theme_mgr
        self.ui_root = chrome.mount if chrome else root
        self.sys_monitor = None
        self.anim_bg: AnimatedBackground | None = None
        self._defer_drag_drop = True
        self._tab_sizes: dict[str, list[int]] = {
            tid: [w, h] for tid, (w, h) in TAB_SIZES.items()
        }
        self._last_tab = DEFAULT_TAB_ID
        self._resize_job = None
        self._suspend_resize_save = False
        # base_dir sớm để load prefs trước setup_ui
        if getattr(sys, "frozen", False):
            self.base_dir = os.path.dirname(sys.executable)
        else:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self._load_ui_prefs()
        if theme_mgr:
            apply_theme_to_module_colors(theme_mgr.colors)
        super().__init__(root)
        self.root.title(f"{APP_NAME} v{VERSION}")
        if not chrome:
            pw, ph = TAB_SIZES.get(DEFAULT_TAB_ID, (480, 460))
            self.root.geometry(f"{pw}x{ph}")
            self.root.minsize(360, 260)
        self.DXF_MIN_MATCH = DXF_MIN_MATCH
        self.history_path = os.path.join(self.base_dir, "acc2019_history.txt")
        if not hasattr(self, "emb_panel"):
            self.emb_panel = None
        if chrome:
            cfg = chrome._load()
            # khôi phục vị trí; size theo tab cuối (tránh height 680 → khoảng trắng)
            tab0 = self._last_tab if self._last_tab in self._tab_sizes else DEFAULT_TAB_ID
            w, h = self._tab_sizes.get(tab0, list(TAB_SIZES.get(DEFAULT_TAB_ID, (480, 460))))
            geom = f"{int(w)}x{int(h)}"
            if cfg.get("x") is not None and cfg.get("y") is not None:
                geom += f"+{int(cfg['x'])}+{int(cfg['y'])}"
            self.root.geometry(geom)
        if theme_mgr:
            theme_mgr.on_change(self._on_theme_changed)
            self._apply_theme_ui(theme_mgr.colors)
        # Ghi nhớ khi user kéo resize cửa sổ
        self.root.bind("<Configure>", self._on_root_configure, add="+")
        self.log(f"{APP_NAME} v{VERSION} sẵn sàng", "accent")
        self.refresh_daily_stats()
        if self.csv_panel:
            self.csv_panel.setup_drop()
    def _load_ui_prefs(self) -> None:
        path = os.path.join(self.base_dir, "acc2019_window.json")
        if not os.path.isfile(path):
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return
        raw = data.get("tab_sizes") or {}
        if isinstance(raw, dict):
            for tid, wh in raw.items():
                if tid in TAB_SIZES and isinstance(wh, (list, tuple)) and len(wh) >= 2:
                    try:
                        self._tab_sizes[tid] = [int(wh[0]), int(wh[1])]
                    except (TypeError, ValueError):
                        pass
        last = data.get("last_tab")
        if last in TAB_SIZES:
            self._last_tab = last

    def _save_ui_prefs(self) -> None:
        extra = {
            "tab_sizes": self._tab_sizes,
            "last_tab": getattr(self, "active_tab", self._last_tab) or "produce",
        }
        if self.theme_mgr:
            extra["theme"] = self.theme_mgr.theme_id
        if self.chrome:
            self.chrome.merge_save(extra)
        else:
            path = os.path.join(self.base_dir, "acc2019_window.json")
            try:
                data = {}
                if os.path.isfile(path):
                    with open(path, encoding="utf-8") as f:
                        data = json.load(f)
                data.update(extra)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except (OSError, json.JSONDecodeError):
                pass

    def _on_root_configure(self, event=None) -> None:
        if event is not None and event.widget is not self.root:
            return
        if self._suspend_resize_save:
            return
        # debounce — lưu size + sync layout khi user kéo xong
        if self._resize_job:
            try:
                self.root.after_cancel(self._resize_job)
            except Exception:
                pass
        self._resize_job = self.root.after(200, self._after_resize_debounce)

    def _after_resize_debounce(self) -> None:
        self._resize_job = None
        self._commit_tab_size()
        # sync layout thưa hơn khi kéo — tránh giật
        self._sync_layout_to_window()

    def _commit_tab_size(self) -> None:
        self._resize_job = None
        if self._suspend_resize_save:
            return
        tid = getattr(self, "active_tab", None)
        if not tid or tid not in self._tab_sizes:
            return
        try:
            w = self.root.winfo_width()
            h = self.root.winfo_height()
            if w < 100 or h < 100:
                return
            self._tab_sizes[tid] = [w, h]
            self._save_ui_prefs()
        except tk.TclError:
            pass

    def _measure_content_size(self) -> tuple[int, int]:
        """Đo kích thước cần thiết theo nội dung hiện tại (không khoảng trắng)."""
        self.root.update_idletasks()
        title_h = self.chrome.title_height() if self.chrome else 0
        mount = self.ui_root
        # Cộng reqheight các hàng grid đã map
        total_h = 0
        max_w = 0
        try:
            for child in mount.winfo_children():
                if not child.winfo_ismapped():
                    continue
                total_h += max(child.winfo_reqheight(), child.winfo_height())
                max_w = max(max_w, child.winfo_reqwidth(), child.winfo_width())
        except tk.TclError:
            pass
        # fallback
        try:
            max_w = max(max_w, mount.winfo_reqwidth())
            total_h = max(total_h, mount.winfo_reqheight())
        except tk.TclError:
            pass
        w = max(360, max_w + 6)
        h = max(260, title_h + total_h + 4)
        # trần hợp lý
        w = min(w, 900)
        h = min(h, 860)
        return w, h

    def _apply_tab_geometry(self, tab_id: str, *, force_fit: bool = False) -> None:
        """Áp size đã nhớ cho tab; nếu chưa có / force_fit → co theo nội dung."""
        self._suspend_resize_save = True
        try:
            self.root.update_idletasks()
            if force_fit or tab_id not in self._tab_sizes:
                w, h = self._measure_content_size()
                self._tab_sizes[tab_id] = [w, h]
            else:
                w, h = self._tab_sizes[tab_id]
                # nếu size đã nhớ cao bất thường so với nội dung → fit lại (bỏ khoảng trắng)
                fit_w, fit_h = self._measure_content_size()
                if h > fit_h + 40:
                    h = fit_h
                    self._tab_sizes[tab_id] = [w, h]
                w = max(w, min(fit_w, w))
            if self.chrome:
                self.chrome.set_size(w, h, keep_pos=True)
            else:
                try:
                    x, y = self.root.winfo_x(), self.root.winfo_y()
                    self.root.geometry(f"{w}x{h}+{x}+{y}")
                except tk.TclError:
                    self.root.geometry(f"{w}x{h}")
            self._last_tab = tab_id
            self._save_ui_prefs()
        finally:
            # cho phép save resize sau khi geometry ổn định
            self.root.after(400, self._unlock_resize_save)

    def _unlock_resize_save(self) -> None:
        self._suspend_resize_save = False

    def create_drop_zone(self, parent, text, fg, border_color, command, wraplength=170, height=1):
        zone = tk.Label(
            parent,
            text=text,
            font=("Segoe UI", 7, "bold"),
            fg=fg,
            bg=COLOR_CARD,
            bd=0,
            highlightthickness=0,
            height=height,
            cursor="hand2",
            wraplength=wraplength,
            justify="center",
        )
        zone.bind("<Button-1>", lambda _e: command())
        return zone

    def refresh_daily_stats(self) -> None:
        emb = get_emb_today_stats()
        csv_s = get_today_stats()
        if self.sys_monitor:
            self.sys_monitor.set_daily_summary(
                emb.get("orders", 0),
                emb.get("products", len(emb.get("items", []))),
                csv_s.get("files", 0),
            )

    def update_queue_status(self) -> None:
        if not hasattr(self, "queue_var") or not self.produce_queue:
            return
        n = self.produce_queue.pending
        records = self.produce_queue.get_records()
        running = sum(1 for r in records if r.state == "running")
        if n:
            self.queue_var.set(f"Hàng đợi: {n} chờ" + (f" · {running} đang chạy" if running else ""))
        else:
            done = sum(1 for r in records if r.state == "done")
            err = sum(1 for r in records if r.state in ("error", "skipped"))
            if records and (done or err):
                self.queue_var.set(f"Hàng đợi: xong · {done} OK" + (f" · {err} lỗi/bỏ qua" if err else ""))
            else:
                self.queue_var.set("Hàng đợi: trống")

    def refresh_queue_panel(self) -> None:
        pass

    def show_queue_summary(self, done, skipped, errors, low_match) -> None:
        if not low_match and not errors:
            return
        lines = []
        if low_match:
            lines.append("DXF khớp < 95%:")
            for r in low_match[:8]:
                lines.append(f"  {os.path.basename(r.path)} — {r.match_pct:.1f}%")
        if errors:
            lines.append("Lỗi:")
            for r in errors[:5]:
                lines.append(f"  {os.path.basename(r.path)} — {r.detail}")
        if lines:
            from tkinter import messagebox
            messagebox.showwarning("Hàng đợi — cần kiểm tra", "\n".join(lines), parent=self.root)

    def create_app_card(self, parent, app_name, accent):
        card = tk.Frame(parent, bg=COLOR_CARD, bd=0, highlightthickness=0)
        card.pack(fill=tk.X, pady=(0, 2))

        header = tk.Frame(card, bg=COLOR_CARD)
        header.pack(fill=tk.X, padx=4, pady=(2, 0))
        tk.Label(
            header, text=app_name, font=("Segoe UI", 8, "bold"), fg=accent, bg=COLOR_CARD,
        ).pack(side=tk.LEFT)
        status = tk.Label(
            header, text="Đang kiểm tra...", font=("Segoe UI", 7, "bold"),
            fg=COLOR_MUTED, bg=COLOR_CARD,
        )
        status.pack(side=tk.RIGHT)

        actions = tk.Frame(card, bg=COLOR_CARD)
        actions.pack(fill=tk.X, padx=4, pady=(0, 2))
        btn_install = self.create_flat_button(actions, text="Cài", bg=accent, padx=5, pady=1)
        btn_install.pack(side=tk.LEFT, padx=(0, 2))
        btn_uninstall = self.create_flat_button(actions, text="Gỡ", bg=COLOR_DANGER, padx=5, pady=1)
        btn_uninstall.pack(side=tk.LEFT, padx=(0, 2))
        btn_open = self.create_flat_button(actions, text="Mở", bg=COLOR_SUCCESS, padx=5, pady=1)
        btn_open.pack(side=tk.LEFT)

        progress_canvas = tk.Canvas(card, height=2, bg="#0d0d16", bd=0, highlightthickness=0)
        progress_canvas.pack(fill=tk.X, padx=4, pady=(0, 2))
        progress_rect = progress_canvas.create_rectangle(0, 0, 0, 2, fill=accent, width=0)

        return {
            "card": card,
            "status": status,
            "btn_install": btn_install,
            "btn_uninstall": btn_uninstall,
            "btn_open": btn_open,
            "progress_canvas": progress_canvas,
            "progress_rect": progress_rect,
        }

    def setup_ui(self):
        pad = 2
        c = self.theme_mgr.colors if self.theme_mgr else {
            "bg": COLOR_BG, "card": COLOR_CARD, "muted": COLOR_MUTED,
            "accent": COLOR_ACCENT_PS, "success": COLOR_SUCCESS, "danger": COLOR_DANGER,
            "csv": COLOR_CSV, "console_bg": "#07070a", "console_fg": "#a9b7c6",
        }
        bg = c["bg"]
        card = c["card"]
        muted = c["muted"]
        accent = c["accent"]
        success = c["success"]
        danger = c["danger"]
        csv_c = c.get("csv", COLOR_CSV)

        mount = self.ui_root
        mount.columnconfigure(0, weight=1)
        # content (row 3) giãn theo cửa sổ khi user kéo resize
        mount.rowconfigure(3, weight=1)

        # ── FX strip (cao hơn cho theme thời tiết / sấm sét) ──
        fx_h = self._fx_strip_height()
        fx_row = tk.Frame(mount, bg=bg, height=fx_h, bd=0, highlightthickness=0)
        fx_row.grid(row=0, column=0, sticky="ew")
        fx_row.grid_propagate(False)
        self._fx_row = fx_row
        if self.theme_mgr:
            try:
                flash_targets = [mount, fx_row]
                if self.chrome:
                    flash_targets.extend([self.chrome.shell, self.chrome.bg_layer, self.chrome.content])
                self.anim_bg = AnimatedBackground(
                    fx_row, self.root, self.theme_mgr, fps=8,
                    base_dir=self.base_dir,
                    flash_targets=flash_targets[:2],
                )
            except Exception:
                self.anim_bg = None

        # ── Header ──
        header = tk.Frame(mount, bg=bg, bd=0, highlightthickness=0)
        header.grid(row=1, column=0, sticky="ew", padx=pad)
        header.columnconfigure(0, weight=1)
        self._header_drag = header

        stats_row = tk.Frame(header, bg=bg)
        stats_row.pack(fill=tk.X)

        self.sys_monitor = SysMonitorBar(stats_row, self.root, bg=bg)

        # Header gọn: chỉ ⚙ 🎨 ?  (Night / Weather / Lịch sử → trong Cài đặt)
        self.btn_help = self.create_flat_button(
            stats_row, text="?", bg=card, fg=accent,
            border_color=card, padx=4, pady=0, command=self._show_help_popup,
        )
        self.btn_help.pack(side=tk.RIGHT, padx=(0, 0))
        self._bind_help_tooltip(self.btn_help)

        self._theme_var = tk.StringVar(value="")
        if self.theme_mgr:
            names = {tid: t["name"] for tid, t in THEMES.items()}
            self._theme_var.set(names.get(self.theme_mgr.theme_id, "Theme"))
            theme_btn = self.create_flat_button(
                stats_row, text="🎨", bg=card, fg=accent,
                border_color=card, padx=3, pady=0, command=self._show_theme_menu,
            )
            theme_btn.pack(side=tk.RIGHT, padx=(0, 1))
            self._theme_btn = theme_btn

        self.btn_settings = self.create_flat_button(
            stats_row, text="⚙", bg=card, fg=accent,
            border_color=card, padx=3, pady=0, command=self.open_settings,
        )
        self.btn_settings.pack(side=tk.RIGHT, padx=(0, 1))
        if self.chrome:
            self.chrome.bind_drag(header)

        # Night mode state
        self._night_mode = False
        self._night_auto = False
        self._night_from = 19
        self._night_to = 6
        self._theme_before_night = None
        self._night_contrast = True
        self._break_reminder: BreakReminder | None = None
        self._weather_auto = False
        self._weather_svc: WeatherThemeService | None = None
        self._weather_last: WeatherSnapshot | None = None
        self._weather_theme_applied: str | None = None

        # Áp prefs đã lưu (FX, topmost, console, night…)
        self.root.after(120, self._apply_startup_prefs)

        # ── Tabs (đăng ký tại modules/tabs/*) ──
        self._tab_registry = get_registry()
        tab_bar = tk.Frame(mount, bg=bg)
        tab_bar.grid(row=2, column=0, sticky="ew", padx=pad)

        self.tab_buttons = {}
        self.tab_frames = {}
        default_tab = self._tab_registry.ids()[0] if self._tab_registry.ids() else "produce"
        self.active_tab = default_tab

        for spec in self._tab_registry.enabled_tabs():
            tab_accent = spec.resolve_accent(c)
            btn = self.create_tab_button(tab_bar, spec.id, spec.label, tab_accent)
            btn.config(font=("Segoe UI", 7, "bold"), padx=4, pady=0)
            btn.pack(side=tk.LEFT, padx=(0, 1))
        if self.chrome:
            self.chrome.bind_drag(tab_bar)

        # ── Content — frame rỗng; panel load lazy khi mở tab ──
        content = tk.Frame(mount, bg=bg)
        content.grid(row=3, column=0, sticky="nsew", padx=pad)
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)
        self._content_frame = content

        self._tab_registry.prepare_frames(self, content, c)

        # ── Console ──
        console_wrap = tk.Frame(mount, bg=bg)
        console_wrap.grid(row=4, column=0, sticky="ew", padx=pad, pady=(1, 1))
        self._console_wrap = console_wrap

        log_hdr = tk.Frame(console_wrap, bg=card, bd=0, highlightthickness=0)
        log_hdr.pack(fill=tk.X)
        tk.Label(
            log_hdr, text=" Nhật ký ", font=("Segoe UI", 6, "bold"),
            fg=muted, bg=card, padx=2, pady=0,
        ).pack(side=tk.LEFT)
        # gợi ý resize
        tk.Label(
            log_hdr, text="kéo ⌞ góc để resize", font=("Segoe UI", 5),
            fg=muted, bg=card,
        ).pack(side=tk.RIGHT, padx=4)

        self.console = scrolledtext.ScrolledText(
            console_wrap,
            height=CONSOLE_H,
            bg=c.get("console_bg", "#07070a"),
            fg=c.get("console_fg", "#a9b7c6"),
            insertbackground="white",
            font=("Consolas", 7),
            bd=0,
            highlightthickness=0,
            state=tk.DISABLED,
            wrap=tk.WORD,
        )
        self.console.pack(fill=tk.BOTH, expand=True)
        self.console.tag_config("normal", foreground=c.get("console_fg", "#a9b7c6"))
        self.console.tag_config("success", foreground=success)
        self.console.tag_config("danger", foreground=danger)
        self.console.tag_config("accent", foreground=accent)
        self.console.tag_config("csv", foreground=csv_c)

        # Chỉ build tab khởi động → mở app nhanh hơn rõ rệt
        ids = self._tab_registry.ids()
        start = self._last_tab if self._last_tab in self.tab_frames else (ids[0] if ids else "produce")
        self._tab_registry.ensure_tab(self, start, c)
        for tid, frame in self.tab_frames.items():
            if tid == start:
                frame.pack(fill=tk.BOTH, expand=True, anchor="n")
            else:
                frame.pack_forget()
        self.active_tab = start
        for tid, meta in self.tab_buttons.items():
            a = meta["accent"]
            if tid == start:
                meta["btn"].config(fg=a, highlightbackground=a, highlightthickness=1)
            else:
                meta["btn"].config(fg=COLOR_MUTED, highlightthickness=0)

        self.refresh_daily_stats()

        if self.chrome:
            self.chrome.set_resize_callback(self._on_user_resize_end)

        self.root.after(100, lambda: self._apply_tab_geometry(start, force_fit=False))
        self.root.after(180, self._sync_layout_to_window)

    def _ui_colors(self) -> dict:
        if self.theme_mgr:
            return self.theme_mgr.colors
        return {
            "bg": COLOR_BG, "card": COLOR_CARD, "muted": COLOR_MUTED,
            "accent": COLOR_ACCENT_PS, "success": COLOR_SUCCESS, "danger": COLOR_DANGER,
            "csv": COLOR_CSV, "console_bg": "#07070a", "console_fg": "#a9b7c6",
        }

    def show_tab(self, tab_id):
        """Đổi tab → build lazy lần đầu; size theo tab đã nhớ."""
        prev = getattr(self, "active_tab", None)
        if prev and prev in self._tab_sizes and not self._suspend_resize_save:
            try:
                cw, ch = self.root.winfo_width(), self.root.winfo_height()
                if cw > 100 and ch > 100:
                    self._tab_sizes[prev] = [cw, ch]
            except tk.TclError:
                pass

        reg = getattr(self, "_tab_registry", None) or get_registry()
        reg.ensure_tab(self, tab_id, self._ui_colors())

        for tid, frame in self.tab_frames.items():
            if tid == tab_id:
                frame.pack(fill=tk.BOTH, expand=True, anchor="n")
            else:
                frame.pack_forget()

        for tid, meta in self.tab_buttons.items():
            accent = meta["accent"]
            if tid == tab_id:
                meta["btn"].config(fg=accent, highlightbackground=accent, highlightthickness=1)
            else:
                meta["btn"].config(fg=COLOR_MUTED, highlightthickness=0)

        self.active_tab = tab_id
        self._last_tab = tab_id
        self.root.after_idle(lambda: self._apply_tab_geometry(tab_id, force_fit=False))
        self.root.after(80, self._sync_layout_to_window)

    def _on_user_resize_end(self) -> None:
        """Sau khi kéo resize xong — lưu size tab + đồng bộ con."""
        tid = getattr(self, "active_tab", None)
        if tid and tid in self._tab_sizes:
            try:
                self._tab_sizes[tid] = [self.root.winfo_width(), self.root.winfo_height()]
                self._save_ui_prefs()
            except tk.TclError:
                pass
        self._sync_layout_to_window()

    def _sync_layout_to_window(self) -> None:
        """Thu/giãn widget con theo kích thước cửa sổ hiện tại."""
        try:
            self.root.update_idletasks()
            w = max(1, self.root.winfo_width())
            h = max(1, self.root.winfo_height())
        except tk.TclError:
            return
        # console lines theo chiều cao
        if hasattr(self, "console") and self.console:
            # ~14px/dòng; giữ 2–10 dòng
            ch = max(2, min(10, (h - 320) // 28))
            try:
                self.console.configure(height=ch)
            except tk.TclError:
                pass
        # emb panel scale
        panel = getattr(self, "emb_panel", None)
        if panel and hasattr(panel, "on_host_resize"):
            try:
                panel.on_host_resize(w, h)
            except Exception:
                pass
        # FX strip theo theme
        self._resize_fx_strip()

    # ── Settings ────────────────────────────────────────────────────────────

    def open_settings(self) -> None:
        SettingsDialog(self).show()

    def snap_window(self, side: str = "right", monitor_index: int | None = None) -> None:
        """Snap multi-monitor: left/right/center/full/… hoặc cycle."""
        if side == "cycle":
            self.cycle_monitor_window(1)
            return
        msg = apply_snap(self.root, side, monitor_index=monitor_index)
        self.log(msg, "accent")
        if self.chrome:
            try:
                self.chrome.save_geometry()
            except Exception:
                pass

    def cycle_monitor_window(self, direction: int = 1) -> None:
        msg = cycle_monitor(self.root, direction)
        self.log(msg, "accent")
        if self.chrome:
            try:
                self.chrome.save_geometry()
            except Exception:
                pass

    def backup_config(self) -> None:
        """Backup config → Desktop zip."""
        try:
            path = create_backup(self.base_dir)
            self.log(f"Backup: {os.path.basename(path)} → Desktop", "success")
            try:
                os.startfile(os.path.dirname(path))
            except OSError:
                pass
        except Exception as exc:
            self.log(f"Backup lỗi: {exc}", "danger")

    def set_console_height(self, lines: int) -> None:
        h = max(1, min(8, int(lines)))
        if hasattr(self, "console") and self.console:
            try:
                self.console.configure(height=h)
            except tk.TclError:
                pass
        # lưu
        try:
            path = os.path.join(self.base_dir, "acc2019_window.json")
            data = {}
            if os.path.isfile(path):
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            data["console_height"] = h
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def set_fx_enabled(self, enabled: bool) -> None:
        self._fx_enabled = bool(enabled)
        if self.anim_bg:
            if enabled:
                if not getattr(self.anim_bg, "_running", False):
                    self.anim_bg._running = True
                    self.anim_bg._tick()
            else:
                self.anim_bg.stop()
                try:
                    self.anim_bg.canvas.delete("fx")
                except tk.TclError:
                    pass
        try:
            path = os.path.join(self.base_dir, "acc2019_window.json")
            data = {}
            if os.path.isfile(path):
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            data["fx_enabled"] = bool(enabled)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    # ── Night mode ──────────────────────────────────────────────────────────

    def toggle_night_mode(self) -> None:
        self.set_night_mode(not getattr(self, "_night_mode", False), manual=True)

    def set_night_auto(self, enabled: bool, hour_from: int = 19, hour_to: int = 6) -> None:
        self._night_auto = bool(enabled)
        self._night_from = int(hour_from) % 24
        self._night_to = int(hour_to) % 24
        self._save_night_prefs()
        self._check_night_auto()

    def set_night_mode(self, enabled: bool, *, manual: bool = False) -> None:
        """Night Soft — dịu mắt; tắt thì khôi phục theme trước đó."""
        enabled = bool(enabled)
        if enabled == getattr(self, "_night_mode", False) and not manual:
            # vẫn cập nhật nút
            self._update_night_btn()
            return
        if enabled:
            if self.theme_mgr and self.theme_mgr.theme_id != "night_soft":
                self._theme_before_night = self.theme_mgr.theme_id
            if self.theme_mgr:
                # force apply even if already night_soft
                prev = self.theme_mgr.theme_id
                self.theme_mgr.theme_id = "night_soft"
                self.theme_mgr.save()
                if prev != "night_soft":
                    for cb in self.theme_mgr._listeners:
                        try:
                            cb(self.theme_mgr.colors)
                        except Exception:
                            pass
                else:
                    self._apply_theme_ui(self.theme_mgr.colors)
            self._apply_night_contrast()
            # FX nhẹ hơn ban đêm
            if self.anim_bg:
                self.anim_bg._sound_enabled = False
            self._night_mode = True
            self.log("🌙 Night mode bật — dịu mắt + contrast rõ chữ", "accent")
            if self._break_reminder:
                self._break_reminder.night_colors = True
        else:
            self._night_mode = False
            # Ưu tiên theme thời tiết Bắc Ninh nếu đang bật
            if getattr(self, "_weather_auto", False) and self._weather_last and self._weather_last.ok:
                self._apply_weather_theme(self._weather_last)
            else:
                restore = self._theme_before_night or "midnight"
                if restore == "night_soft":
                    restore = "midnight"
                if self.theme_mgr and restore in THEMES:
                    self.theme_mgr.set_theme(restore)
            if self.anim_bg:
                self.anim_bg._sound_enabled = True
            self.log("☀ Night mode tắt", "accent")
            if self._break_reminder:
                self._break_reminder.night_colors = False
        self._update_night_btn()
        self._save_night_prefs()

    def set_night_contrast(self, enabled: bool) -> None:
        """(18) Tăng độ tương phản chữ khi Night mode."""
        self._night_contrast = bool(enabled)
        self._save_night_prefs()
        if getattr(self, "_night_mode", False):
            self._apply_night_contrast()

    def _apply_night_contrast(self) -> None:
        if not self.theme_mgr or self.theme_mgr.theme_id != "night_soft":
            return
        if not getattr(self, "_night_contrast", True):
            return
        try:
            # boost palette live (dict may be shared from THEMES — copy-safe update)
            colors = dict(self.theme_mgr.colors)
            colors.update(NIGHT_CONTRAST_BOOST)
            apply_theme_to_module_colors(colors)
            self._apply_theme_ui(colors)
            # console bold + brighter
            if hasattr(self, "console") and self.console:
                self.console.config(
                    fg=colors.get("console_fg", "#c8d0dc"),
                    font=("Consolas", 7, "bold"),
                )
        except Exception:
            pass

    def set_music_status(self, title: str) -> None:
        if self.sys_monitor and hasattr(self.sys_monitor, "set_music_now"):
            self.sys_monitor.set_music_now(title)

    def configure_break_reminder(
        self,
        *,
        enabled: bool | None = None,
        interval_min: int | None = None,
        break_min: int | None = None,
    ) -> None:
        if not self._break_reminder:
            return
        self._break_reminder.configure(
            enabled=enabled if enabled is not None else self._break_reminder.enabled,
            interval_min=interval_min,
            break_min=break_min,
        )
        # persist
        try:
            path = os.path.join(self.base_dir, "acc2019_window.json")
            data = {}
            if os.path.isfile(path):
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            if enabled is not None:
                data["break_enabled"] = bool(enabled)
            if interval_min is not None:
                data["break_interval_min"] = int(interval_min)
            if break_min is not None:
                data["break_min"] = int(break_min)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def _update_night_btn(self) -> None:
        # Nút 🌙 đã gỡ khỏi header — Night bật/tắt trong ⚙
        return

    def _save_night_prefs(self) -> None:
        try:
            path = os.path.join(self.base_dir, "acc2019_window.json")
            data = {}
            if os.path.isfile(path):
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            data["night_mode"] = bool(getattr(self, "_night_mode", False))
            data["night_auto"] = bool(getattr(self, "_night_auto", False))
            data["night_from"] = int(getattr(self, "_night_from", 19))
            data["night_to"] = int(getattr(self, "_night_to", 6))
            data["night_contrast"] = bool(getattr(self, "_night_contrast", True))
            if self._theme_before_night:
                data["theme_before_night"] = self._theme_before_night
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def _in_night_hours(self) -> bool:
        from datetime import datetime
        h = datetime.now().hour
        a, b = self._night_from, self._night_to
        if a == b:
            return True
        if a < b:
            return a <= h < b
        # qua đêm: 19→6
        return h >= a or h < b

    def _check_night_auto(self) -> None:
        if not getattr(self, "_night_auto", False):
            return
        should = self._in_night_hours()
        if should and not self._night_mode:
            self.set_night_mode(True, manual=False)
        elif not should and self._night_mode:
            # chỉ auto-tắt nếu không ép tay gần đây — vẫn tôn trọng auto schedule
            self.set_night_mode(False, manual=False)

    def _schedule_night_check(self) -> None:
        try:
            self._check_night_auto()
        except Exception:
            pass
        try:
            self.root.after(60_000, self._schedule_night_check)
        except Exception:
            pass

    def reset_tab_sizes(self) -> None:
        self._tab_sizes = {tid: [w, h] for tid, (w, h) in TAB_SIZES.items()}
        self._save_ui_prefs()
        tid = getattr(self, "active_tab", "produce")
        self._apply_tab_geometry(tid, force_fit=True)

    def _apply_startup_prefs(self) -> None:
        path = os.path.join(self.base_dir, "acc2019_window.json")
        data = {}
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        if "console_height" in data:
            self.set_console_height(int(data["console_height"]))
        if data.get("fx_enabled") is False:
            self.set_fx_enabled(False)
        if data.get("always_on_top"):
            try:
                self.root.attributes("-topmost", True)
            except tk.TclError:
                pass
        # night
        self._night_auto = bool(data.get("night_auto", False))
        self._night_from = int(data.get("night_from", 19))
        self._night_to = int(data.get("night_to", 6))
        self._theme_before_night = data.get("theme_before_night")
        self._night_contrast = bool(data.get("night_contrast", True))
        if data.get("night_mode"):
            self.set_night_mode(True, manual=True)
        elif self._night_auto:
            self._check_night_auto()
        self._schedule_night_check()
        panel = getattr(self, "emb_panel", None)
        if panel and hasattr(panel, "apply_settings"):
            panel.apply_settings(data)
        # (17) Break reminder
        br_en = bool(data.get("break_enabled", True))
        br_iv = int(data.get("break_interval_min", 50))
        br_min = int(data.get("break_min", 5))

        def _on_break_tick(rem):
            if self.sys_monitor and hasattr(self.sys_monitor, "set_break_remaining"):
                self.sys_monitor.set_break_remaining(rem)

        if self._break_reminder is None:
            self._break_reminder = BreakReminder(
                self.root,
                interval_min=br_iv,
                break_min=br_min,
                enabled=br_en,
                on_tick=_on_break_tick,
                night_colors=bool(getattr(self, "_night_mode", False)),
            )
        else:
            self._break_reminder.configure(
                interval_min=br_iv, break_min=br_min, enabled=br_en,
            )
        # Theme thời tiết thật — Bắc Ninh
        wx_en = bool(data.get("weather_auto", False))
        wx_iv = int(data.get("weather_interval_min", 15))
        self._init_weather_service(enabled=wx_en, interval_min=wx_iv)
        self._update_weather_btn()

    # ── Weather theme · Bắc Ninh ─────────────────────────────────────────────

    def _init_weather_service(self, *, enabled: bool = False, interval_min: int = 15) -> None:
        def on_update(snap: WeatherSnapshot) -> None:
            try:
                self.root.after(0, lambda s=snap: self._on_weather_update(s))
            except Exception:
                pass

        if self._weather_svc is None:
            self._weather_svc = WeatherThemeService(
                interval_sec=max(2, int(interval_min)) * 60,
                enabled=enabled,
                on_update=on_update,
            )
            self._weather_svc.start()
        else:
            self._weather_svc.set_interval_min(interval_min)
            self._weather_svc.set_enabled(enabled)
        self._weather_auto = bool(enabled)
        if enabled:
            self._weather_svc.refresh_now()

    def toggle_weather_theme(self) -> None:
        """Nút 🌤 — bật/tắt theme theo thời tiết Bắc Ninh."""
        self.set_weather_auto(not getattr(self, "_weather_auto", False))

    def set_weather_auto(self, enabled: bool, interval_min: int | None = None) -> None:
        enabled = bool(enabled)
        self._weather_auto = enabled
        iv = interval_min
        if iv is None:
            iv = 15
            try:
                path = os.path.join(self.base_dir, "acc2019_window.json")
                if os.path.isfile(path):
                    with open(path, encoding="utf-8") as f:
                        iv = int(json.load(f).get("weather_interval_min", 15))
            except Exception:
                iv = 15
        self._init_weather_service(enabled=enabled, interval_min=int(iv))
        self._save_weather_prefs()
        self._update_weather_btn()
        if enabled:
            # nếu đang night mode thì chỉ hiện status, không đổi theme
            if getattr(self, "_night_mode", False):
                self.log("🌤 Thời tiết Bắc Ninh bật — Night mode ưu tiên, sẽ áp theme khi tắt Night", "accent")
            else:
                self.log("🌤 Theme theo thời tiết thật · Bắc Ninh", "accent")
            if self._weather_svc:
                self._weather_svc.refresh_now()
        else:
            self.log("🌤 Tắt theme thời tiết tự động", "accent")

    def refresh_weather_now(self) -> None:
        if self._weather_svc:
            self._weather_svc.refresh_now()
            self.log("🌤 Đang lấy thời tiết Bắc Ninh…", "accent")

    def _save_weather_prefs(self) -> None:
        try:
            path = os.path.join(self.base_dir, "acc2019_window.json")
            data = {}
            if os.path.isfile(path):
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            data["weather_auto"] = bool(getattr(self, "_weather_auto", False))
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def _update_weather_btn(self) -> None:
        # Nút 🌤 đã gỡ khỏi header — bật trong ⚙ / status BN trên monitor
        return

    def _on_weather_update(self, snap: WeatherSnapshot) -> None:
        self._weather_last = snap
        # header status
        if self.sys_monitor and hasattr(self.sys_monitor, "set_weather_summary"):
            if snap.ok:
                self.sys_monitor.set_weather_summary(snap.short_label())
            else:
                self.sys_monitor.set_weather_summary("BN:?")
        if not snap.ok:
            if getattr(self, "_weather_auto", False):
                self.log(f"🌤 Bắc Ninh: không lấy được thời tiết ({snap.error})", "danger")
            return
        # luôn log gọn khi auto
        if getattr(self, "_weather_auto", False):
            self.log(
                f"🌤 {snap.detail_label()} → theme «{snap.theme_name}»",
                "accent",
            )
        self._apply_weather_theme(snap)

    def _apply_weather_theme(self, snap: WeatherSnapshot | None = None) -> None:
        """Áp theme weather nếu auto bật và không bị Night mode chặn."""
        if not getattr(self, "_weather_auto", False):
            return
        if getattr(self, "_night_mode", False):
            return
        snap = snap or self._weather_last
        if not snap or not snap.ok or not self.theme_mgr:
            return
        tid = snap.theme_id
        if tid not in THEMES:
            return
        if self.theme_mgr.theme_id == tid:
            self._weather_theme_applied = tid
            return
        # nhớ theme user trước khi weather takeover (một lần)
        if not getattr(self, "_theme_before_weather", None):
            prev = self.theme_mgr.theme_id
            if prev not in (
                "lightning", "storm", "wind", "sunrise", "sunset_sky",
                "rain", "snow", "fog", "aurora_night", "night_soft",
            ):
                self._theme_before_weather = prev
        self.theme_mgr.set_theme(tid)
        self._weather_theme_applied = tid

    # ── Theme UI ────────────────────────────────────────────────────────────

    def _show_theme_menu(self) -> None:
        if not self.theme_mgr:
            return
        c = self.theme_mgr.colors
        menu = tk.Menu(
            self.root, tearoff=0, font=("Segoe UI", 8),
            bg=c["card"], fg=c["text"],
            activebackground=c["hover"], activeforeground=c["accent"], bd=0,
        )
        by_cat = self.theme_mgr.themes_by_category()
        order = ("classic", "weather", "hero", "anime", "game")
        for cat in order:
            items = by_cat.get(cat) or []
            if not items:
                continue
            sub = tk.Menu(
                menu, tearoff=0, font=("Segoe UI", 8),
                bg=c["card"], fg=c["text"],
                activebackground=c["hover"], activeforeground=c["accent"], bd=0,
            )
            for tid, name in items:
                mark = "● " if tid == self.theme_mgr.theme_id else "   "
                effect = THEMES[tid].get("effect", "")
                sub.add_command(
                    label=f"{mark}{name}  · {effect}",
                    command=lambda t=tid: self.theme_mgr.set_theme(t),
                )
            menu.add_cascade(label=CATEGORY_LABELS.get(cat, cat), menu=sub)
        try:
            x = self._theme_btn.winfo_rootx()
            y = self._theme_btn.winfo_rooty() + self._theme_btn.winfo_height()
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _fx_strip_height(self) -> int:
        """Sấm sét / thời tiết → dải FX cao hơn để vẽ tia sét đẹp."""
        if not self.theme_mgr:
            return 12
        eff = self.theme_mgr.colors.get("effect", "")
        if eff == "lightning":
            return 56
        if eff in ("storm", "sunrise", "rain", "snow", "wind", "fog"):
            return 36
        return 12

    def _resize_fx_strip(self) -> None:
        if not getattr(self, "_fx_row", None):
            return
        h = self._fx_strip_height()
        try:
            self._fx_row.configure(height=h)
        except tk.TclError:
            pass

    def _on_theme_changed(self, colors: dict) -> None:
        apply_theme_to_module_colors(colors)
        self._apply_theme_ui(colors)
        self._resize_fx_strip()
        if self.anim_bg:
            self.anim_bg.flash_targets = [self.ui_root, self._fx_row]
            if self.chrome:
                self.anim_bg.flash_targets.extend([
                    self.chrome.shell, self.chrome.bg_layer, self.chrome.content,
                ])
        if self.theme_mgr:
            names = {tid: t["name"] for tid, t in THEMES.items()}
            self._theme_var.set(names.get(self.theme_mgr.theme_id, "Theme"))
            name = colors.get("name", "?")
            eff = colors.get("effect", "")
            extra = " · ⚡ sét + tiếng sấm" if eff == "lightning" else ""
            self.log(f"Theme: {name}{extra}", "accent")
        else:
            self.log(f"Theme: {colors.get('name', '?')}", "accent")

    # ── Help tooltip (?) ────────────────────────────────────────────────────

    HELP_HOTKEYS = (
        "── PHÍM TẮT ACC2019 ──\n"
        "Ctrl+B     Auto workflow EMB\n"
        "Alt+E      Mở folder đơn đang làm\n"
        "Alt+V      Copy đường dẫn folder\n"
        "Alt+D      Diff thumbnail 2 đơn\n"
        "Alt+P      Pin / bỏ pin đơn\n"
        "\n"
        "── NÚT GIAO DIỆN ──\n"
        "⚙          Cài đặt (Night · Weather · chữ…)\n"
        "🎨          Chọn theme\n"
        "?           Xem phím tắt (hover)\n"
        "⌞          Kéo góc/cạnh = resize tự do\n"
        "📌 ⚖ ⬇    Pin · Diff · Tải ảnh Desktop\n"
        "\n"
        "── THEME THỜI TIẾT ──\n"
        "⚙ → bật theme theo thời tiết Bắc Ninh\n"
        "Sấm / Bão / Mưa / Bình minh… (tự map)\n"
        "\n"
        "── GAME LAN ──\n"
        "Tab Game   Tài xỉu · Xóc đĩa · Bầu cua · Slot · Vòng quay\n"
        "🔒 + pass TX = Admin · Sòng live 20s\n"
        "\n"
        "── CHAT LAN ──\n"
        "Gửi text (màu) · Ảnh · File · online LAN\n"
        "\n"
        "── SẢN XUẤT ──\n"
        "Click ảnh = phóng to · 👁 review folder\n"
        "🔍 zoom · 🗑 reset dữ liệu tab\n"
        "\n"
        "── NIGHT MODE ──\n"
        "⚙ Night mode · tự theo giờ (vd 19→6)\n"
        "Night Soft dịu mắt · contrast chữ rõ\n"
        "\n"
        "── WILCOM · NGHỈ · CHAT ──\n"
        "W:ON/off  Chỉ báo ES/Wilcom đang chạy\n"
        "☕ Np      Nhắc nghỉ mắt ~50 phút (⚙)\n"
        "Chat      Tự báo «đang làm mã…» khi nhận đơn\n"
        "\n"
        "── NHẠC YOUTUBE ──\n"
        "Tab Nhạc  Dán link → audio only (không video)\n"
        "⏯ ⏭ ⏹   Phát / next / dừng · playlist · volume\n"
        "\n"
        "── ĐÓNG GÓI · PHOTOSHOP ──\n"
        "Tab Đóng gói  ZIP/copy theo folder · chọn file\n"
        "Xóa sau gói · dọn nguồn · kéo thả folder\n"
        "▶ Script JSX · ⚡ Batch folder ảnh PS\n"
        "\n"
        "Hover ? để xem lại · Click ? mở popup"
    )

    def _bind_help_tooltip(self, widget: tk.Misc) -> None:
        self._help_tip: tk.Toplevel | None = None

        def show(_e=None):
            self._show_help_tip(widget)

        def hide(_e=None):
            self._hide_help_tip()

        widget.bind("<Enter>", show)
        widget.bind("<Leave>", hide)

    def _show_help_tip(self, anchor: tk.Misc) -> None:
        self._hide_help_tip()
        tip = tk.Toplevel(self.root)
        tip.wm_overrideredirect(True)
        tip.attributes("-topmost", True)
        c = self.theme_mgr.colors if self.theme_mgr else {
            "card": "#141424", "text": "#fff", "accent": "#00d2ff", "bg": "#0c0c14",
        }
        frm = tk.Frame(tip, bg=c.get("card", "#141424"), bd=1, highlightthickness=1,
                       highlightbackground=c.get("accent", "#00d2ff"))
        frm.pack(fill=tk.BOTH, expand=True)
        tk.Label(
            frm, text=self.HELP_HOTKEYS, justify="left",
            font=("Consolas", 8), fg=c.get("text", "#fff"),
            bg=c.get("card", "#141424"), padx=10, pady=8,
        ).pack()
        try:
            x = anchor.winfo_rootx() - 200
            y = anchor.winfo_rooty() + anchor.winfo_height() + 4
            tip.geometry(f"+{max(0, x)}+{y}")
        except tk.TclError:
            pass
        self._help_tip = tip

    def _hide_help_tip(self) -> None:
        if getattr(self, "_help_tip", None):
            try:
                self._help_tip.destroy()
            except tk.TclError:
                pass
            self._help_tip = None

    def _show_help_popup(self) -> None:
        """Click ? — popup cố định (không biến mất khi rời chuột)."""
        self._hide_help_tip()
        c = self.theme_mgr.colors if self.theme_mgr else {
            "bg": "#0c0c14", "card": "#141424", "text": "#fff",
            "accent": "#00d2ff", "muted": "#888",
        }
        win = tk.Toplevel(self.root)
        win.title("Phím tắt & chức năng")
        win.configure(bg=c["bg"])
        win.geometry("360x380")
        win.attributes("-topmost", True)
        tk.Label(
            win, text="?  Phím tắt & chức năng", font=("Segoe UI", 10, "bold"),
            fg=c["accent"], bg=c["card"], padx=8, pady=6,
        ).pack(fill=tk.X)
        txt = tk.Text(
            win, font=("Consolas", 9), bg=c["card"], fg=c["text"],
            bd=0, padx=10, pady=10, wrap=tk.WORD, height=18,
        )
        txt.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        txt.insert("1.0", self.HELP_HOTKEYS)
        txt.configure(state=tk.DISABLED)
        tk.Button(
            win, text="Đóng", font=("Segoe UI", 8), bg=c["card"], fg=c.get("muted", "#888"),
            bd=0, padx=12, pady=4, cursor="hand2", command=win.destroy,
        ).pack(pady=6)

    def _apply_theme_ui(self, colors: dict) -> None:
        bg = colors["bg"]
        try:
            self.root.configure(bg=bg)
        except tk.TclError:
            pass
        if self.chrome:
            self.chrome.apply_colors(colors)
        # recolor whole tree from mount
        target = self.ui_root
        try:
            recolor_widget_tree(target, colors)
        except Exception:
            pass
        # console tags
        if hasattr(self, "console") and self.console:
            try:
                self.console.configure(
                    bg=colors.get("console_bg", "#07070a"),
                    fg=colors.get("console_fg", "#a9b7c6"),
                    insertbackground=colors["text"],
                )
                self.console.tag_config("normal", foreground=colors.get("console_fg", "#a9b7c6"))
                self.console.tag_config("success", foreground=colors["success"])
                self.console.tag_config("danger", foreground=colors["danger"])
                self.console.tag_config("accent", foreground=colors["accent"])
                self.console.tag_config("csv", foreground=colors.get("csv", COLOR_CSV))
            except tk.TclError:
                pass
        # emb treeview style
        try:
            from tkinter import ttk
            style = ttk.Style()
            style.configure(
                "Emb.Treeview",
                background=colors["table_bg"],
                foreground=colors["text"],
                fieldbackground=colors["table_bg"],
            )
            style.configure(
                "Emb.Treeview.Heading",
                background=colors["card"],
                foreground=colors["muted"],
            )
            style.map(
                "Emb.Treeview",
                background=[("selected", colors["table_sel"])],
                foreground=[("selected", colors["success"])],
            )
        except Exception:
            pass

    def _clear_queue_finished(self) -> None:
        if not self.produce_queue:
            return
        n = self.produce_queue.clear_finished()
        self.refresh_queue_panel()
        self.update_queue_status()
        if n:
            self.log(f"Đã xóa {n} mục đã xong khỏi hàng đợi", "accent")

    def log_action(self, app_name, action, detail=""):
        import time

        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"{app_name} | {action}"
        if detail:
            log_msg += f" ({detail})"

        tag = "normal"
        if app_name == "CSV Loki":
            tag = "csv"
        elif "THÀNH CÔNG" in action or "thành công" in action or "ĐỌC FILE" in action:
            tag = "success"
        elif "THẤT BẠI" in action or "LỖI" in action or "lỗi" in action:
            tag = "danger"

        self.log(log_msg, tag)

        try:
            if not os.path.exists(self.history_path):
                with open(self.history_path, "w", encoding="utf-8") as f:
                    f.write(f"=== LỊCH SỬ HOẠT ĐỘNG {APP_NAME} ===\n\n")
            with open(self.history_path, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {log_msg}\n")
        except Exception as e:
            self.log(f"Lỗi ghi lịch sử: {e}")


if __name__ == "__main__":
    if not is_admin():
        print("[*] Requesting administrator rights...")
        try:
            if getattr(sys, "frozen", False):
                ctypes = __import__("ctypes")
                ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, None, None, 1)
            else:
                ctypes = __import__("ctypes")
                ctypes.windll.shell32.ShellExecuteW(
                    None, "runas", sys.executable, f'"{os.path.abspath(__file__)}"', None, 1
                )
        except Exception as e:
            print(f"[!] Failed to elevate privileges: {e}")
        sys.exit(0)

    base_dir = os.path.dirname(os.path.abspath(__file__)) if not getattr(sys, "frozen", False) else os.path.dirname(sys.executable)
    root = tk.Tk()
    app_holder: list = []

    theme_mgr = ThemeManager(base_dir)
    apply_theme_to_module_colors(theme_mgr.colors)

    def on_closing():
        app = app_holder[0] if app_holder else None
        if app:
            app.stop_monitoring = True
            if app.sys_monitor:
                app.sys_monitor.stop()
            if getattr(app, "anim_bg", None):
                app.anim_bg.stop()
            # cleanup mọi tab đã đăng ký
            try:
                get_registry().cleanup_all(app)
            except Exception:
                pass
            if getattr(app, "_break_reminder", None):
                try:
                    app._break_reminder.stop()
                except Exception:
                    pass
            if getattr(app, "_weather_svc", None):
                try:
                    app._weather_svc.stop()
                except Exception:
                    pass
            try:
                app._commit_tab_size()
            except Exception:
                pass
            try:
                app._save_ui_prefs()
            except Exception:
                pass
            if app.theme_mgr:
                app.theme_mgr.save()
            if app.chrome:
                app.chrome.merge_save({
                    "tab_sizes": getattr(app, "_tab_sizes", {}),
                    "last_tab": getattr(app, "active_tab", "produce"),
                    "theme": app.theme_mgr.theme_id if app.theme_mgr else None,
                })
        root.destroy()

    chrome = FramelessChrome(
        root, base_dir, APP_NAME, VERSION,
        default_size=TAB_SIZES.get(DEFAULT_TAB_ID, (480, 460)),
        on_close=on_closing,
    )
    chrome.apply_colors(theme_mgr.colors)
    app = ACC2019App(root, chrome=chrome, theme_mgr=theme_mgr)
    app_holder.append(app)
    chrome.set_snap_callback(app.snap_window)

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()
