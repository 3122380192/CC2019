"""Panel nhận & hiển thị dữ liệu EMB (GodGroup portal → ACC2019)."""

from __future__ import annotations

import io
import os
import threading
import urllib.request
from datetime import datetime

import tkinter as tk
from tkinter import ttk

from modules.emb_bridge import (
    EmbWorkflowGuiAdapter,
    load_auto_workflow,
    load_emb_logic,
)
from modules.emb_positions import CHECKBOX_ORDER, detect_position_codes, sort_for_display
from modules.emb_server import EmbDataServer
from modules.emb_stats import (
    copy_today_ids_text,
    get_emb_today_stats,
    get_last_folder,
    get_today_orders_folder,
    open_today_history_log,
    open_today_ids_file,
    open_today_stats_folder,
    record_emb_order,
    record_last_folder,
)
from modules.file_status import (
    COLOR_IDLE,
    COLOR_MISS,
    COLOR_OK,
    COLOR_WIP,
    FolderFileStatus,
    check_folder,
    required_exts,
)
from modules.image_viewer import ImageLightbox, collect_images_in_folder

COLOR_BG = "#0c0c14"
COLOR_CARD = "#141424"
COLOR_TEXT = "#ffffff"
COLOR_MUTED = "#82829c"
COLOR_ACCENT = "#00d2ff"
COLOR_SUCCESS = "#00e676"
COLOR_DANGER = "#ff1744"
COLOR_EMB = "#ff003c"
COLOR_TABLE_BG = "#0a0a12"
COLOR_TABLE_HEAD = "#141424"
COLOR_TABLE_SEL = "#1a3a2a"
MAX_HISTORY = 50
TABLE_HEIGHT = 3
THUMB_SIZE = 96
COMPARE_SIZE = 180
FILE_POLL_MS = 2800
TEXT_SIZE_MIN = 5
TEXT_SIZE_MAX = 11
TEXT_SIZE_DEFAULT = 6


def _desktop_base() -> str:
    for p in (
        os.path.join(os.path.expanduser("~"), "Desktop"),
        os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop"),
    ):
        if os.path.isdir(p):
            return p
    return os.path.expanduser("~")


def _image_similarity(a: bytes, b: bytes) -> float | None:
    """% giống nhau (0–100) qua MSE ảnh thu nhỏ — None nếu lỗi."""
    try:
        from PIL import Image

        def to_arr(raw: bytes):
            im = Image.open(io.BytesIO(raw)).convert("RGB").resize((48, 48), Image.Resampling.LANCZOS)
            return list(im.getdata())

        pa, pb = to_arr(a), to_arr(b)
        if not pa or len(pa) != len(pb):
            return None
        mse = sum(
            (pa[i][0] - pb[i][0]) ** 2
            + (pa[i][1] - pb[i][1]) ** 2
            + (pa[i][2] - pb[i][2]) ** 2
            for i in range(len(pa))
        ) / (len(pa) * 3 * 255.0 * 255.0)
        return max(0.0, min(100.0, (1.0 - mse) * 100.0))
    except Exception:
        return None


class EmbProducePanel:
    def __init__(self, parent: tk.Misc, app) -> None:
        self.parent = parent
        self.app = app
        self._logic = None
        self._auto_cls = None
        self._workflow_host: EmbWorkflowGuiAdapter | None = None
        self._current: dict = {}
        self._current_folder: str | None = None
        self._history: list[dict] = []
        self._photo = None
        self._photo_b = None
        self._img_bytes: bytes | None = None
        self._server: EmbDataServer | None = None
        self._save_folder = _desktop_base()
        self._row_seq = 0
        self._chk_vars: dict[str, tk.BooleanVar] = {}
        self._chk_widgets: dict[str, tk.Checkbutton] = {}
        self._hotkey_handlers: list = []
        # So sánh 2 đơn
        self._pin_a: dict | None = None
        self._pin_b: dict | None = None
        self._pin_a_bytes: bytes | None = None
        self._pin_b_bytes: bytes | None = None
        self._compare_win: tk.Toplevel | None = None
        self._file_status: FolderFileStatus | None = None
        self._ext_labels: dict[str, tk.Label] = {}
        self._poll_job = None
        self._text_size = TEXT_SIZE_DEFAULT
        self._font_widgets: list[tuple[tk.Misc, str, bool]] = []  # widget, role, bold?
        # Pin đơn ưu tiên (fingerprint → order snapshot)
        self._pinned: dict[str, dict] = {}
        self._pins_path = os.path.join(
            getattr(app, "base_dir", os.path.dirname(os.path.abspath(__file__))),
            "emb_pins.json",
        )
        self._lightbox = ImageLightbox(app.root)

        self.frame = tk.Frame(parent, bg=COLOR_BG)
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(2, weight=1)  # split history/files giãn theo chiều cao

        self._load_text_size()
        self._load_pins()
        self._build_ui()
        self._start_file_poll()

    def on_host_resize(self, win_w: int, win_h: int) -> None:
        """Đồng bộ UI con khi cửa sổ kéo resize (bảng, thumb)."""
        # tree height: ~13px/row; chừa header+body ~220px
        avail = max(80, win_h - 280)
        rows = max(2, min(12, avail // 14))
        try:
            if hasattr(self, "tree"):
                self.tree.configure(height=rows)
        except tk.TclError:
            pass
        # thumb scale nhẹ theo width
        tw = max(72, min(140, win_w // 5))
        self._thumb_px = tw
        try:
            if hasattr(self, "_img_holder"):
                self._img_holder.configure(width=tw, height=tw)
            if hasattr(self, "_img_holder_b"):
                self._img_holder_b.configure(width=tw, height=max(24, tw // 3))
            if self._img_bytes:
                self._set_thumbnail(self._img_bytes, (self._current or {}).get("order_id", ""))
        except Exception:
            pass

    def start_backend(self) -> None:
        """Khởi động server sau khi UI/console của app đã sẵn sàng."""
        if self._server is not None:
            return
        self._init_backend()

    def _reg_font(self, widget: tk.Misc, role: str = "ui", bold: bool = False) -> None:
        self._font_widgets.append((widget, role, bold))

    def _load_text_size(self) -> None:
        try:
            import json
            path = os.path.join(
                getattr(self.app, "base_dir", os.path.dirname(os.path.abspath(__file__))),
                "acc2019_window.json",
            )
            if os.path.isfile(path):
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                sz = int(data.get("text_size", TEXT_SIZE_DEFAULT))
                self._text_size = max(TEXT_SIZE_MIN, min(TEXT_SIZE_MAX, sz))
        except Exception:
            self._text_size = TEXT_SIZE_DEFAULT

    def _save_text_size(self) -> None:
        try:
            import json
            path = os.path.join(
                getattr(self.app, "base_dir", ""),
                "acc2019_window.json",
            )
            if not path or not os.path.isdir(os.path.dirname(path) or "."):
                return
            data = {}
            if os.path.isfile(path):
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            data["text_size"] = self._text_size
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def _apply_text_size(self) -> None:
        sz = self._text_size
        for widget, role, bold in self._font_widgets:
            try:
                if role == "mono":
                    widget.configure(font=("Consolas", sz, "bold" if bold else "normal"))
                elif role == "title":
                    widget.configure(font=("Segoe UI", sz + 1, "bold"))
                else:
                    widget.configure(font=("Segoe UI", sz, "bold" if bold else "normal"))
            except tk.TclError:
                pass
        try:
            style = ttk.Style()
            style.configure("Emb.Treeview", font=("Consolas", max(5, sz - 1)), rowheight=max(11, sz + 6))
            style.configure("Emb.Treeview.Heading", font=("Segoe UI", max(5, sz - 1), "bold"))
        except tk.TclError:
            pass
        if hasattr(self, "_txt_size_var"):
            self._txt_size_var.set(str(sz))

    def _bump_text(self, delta: int) -> None:
        self.set_text_size(self._text_size + delta)

    def set_text_size(self, size: int) -> None:
        """API public — Settings / A±."""
        self._text_size = max(TEXT_SIZE_MIN, min(TEXT_SIZE_MAX, int(size)))
        self._apply_text_size()
        self._save_text_size()

    def apply_settings(self, prefs: dict) -> None:
        """Áp tùy chọn từ Settings dialog."""
        if "text_size" in prefs:
            self.set_text_size(int(prefs["text_size"]))
        if "auto_copy_stem" in prefs and hasattr(self, "_auto_copy_var"):
            try:
                self._auto_copy_var.set(bool(prefs["auto_copy_stem"]))
            except Exception:
                pass
        if "file_poll_ms" in prefs:
            try:
                import modules.emb_panel as _ep
                _ep.FILE_POLL_MS = max(500, min(10000, int(prefs["file_poll_ms"])))
            except Exception:
                pass
        self._settings_prefs = dict(prefs)
        if prefs.get("file_poll_enabled") is False:
            if self._poll_job:
                try:
                    self.app.root.after_cancel(self._poll_job)
                except Exception:
                    pass
                self._poll_job = None
        elif not self._poll_job:
            self._start_file_poll()

    def _build_ui(self) -> None:
        sz = self._text_size
        # ── Header ──
        hdr = tk.Frame(self.frame, bg=COLOR_CARD, bd=0, highlightthickness=0)
        hdr.grid(row=0, column=0, sticky="ew")
        lbl_emb = tk.Label(hdr, text="EMB", font=("Segoe UI", sz + 1, "bold"), fg=COLOR_EMB, bg=COLOR_CARD)
        lbl_emb.pack(side=tk.LEFT, padx=2)
        self._reg_font(lbl_emb, "title", True)

        # cỡ chữ A− A+
        fs = tk.Frame(hdr, bg=COLOR_CARD)
        fs.pack(side=tk.LEFT, padx=(4, 0))
        for txt, d, fg in (("A−", -1, COLOR_MUTED), ("A+", 1, COLOR_ACCENT)):
            b = tk.Button(
                fs, text=txt, font=("Segoe UI", 6, "bold"), bg=COLOR_BG, fg=fg,
                activebackground=COLOR_CARD, bd=0, padx=3, pady=0, cursor="hand2",
                command=lambda x=d: self._bump_text(x),
            )
            b.pack(side=tk.LEFT, padx=1)
        self._txt_size_var = tk.StringVar(value=str(sz))
        lbl_sz = tk.Label(fs, textvariable=self._txt_size_var, font=("Consolas", 6), fg=COLOR_MUTED, bg=COLOR_CARD)
        lbl_sz.pack(side=tk.LEFT, padx=2)
        self._reg_font(lbl_sz, "mono")

        self.status_var = tk.StringVar(value="…")
        lbl_st = tk.Label(hdr, textvariable=self.status_var, font=("Segoe UI", sz), fg=COLOR_MUTED, bg=COLOR_CARD)
        lbl_st.pack(side=tk.RIGHT, padx=2)
        self._reg_font(lbl_st)
        self._pin_status = tk.StringVar(value="")
        lbl_pin = tk.Label(hdr, textvariable=self._pin_status, font=("Segoe UI", sz), fg=COLOR_ACCENT, bg=COLOR_CARD)
        lbl_pin.pack(side=tk.RIGHT, padx=(0, 3))
        self._reg_font(lbl_pin)

        # ── Body: thumb + info ──
        body = tk.Frame(self.frame, bg=COLOR_BG)
        body.grid(row=1, column=0, sticky="ew")
        body.columnconfigure(1, weight=1)

        img_col = tk.Frame(body, bg=COLOR_BG)
        img_col.grid(row=0, column=0, rowspan=3, sticky="n", padx=(0, 2))

        img_box = tk.Frame(img_col, bg=COLOR_CARD, bd=0, highlightthickness=0)
        img_box.pack()
        self._img_holder = tk.Frame(
            img_box, width=THUMB_SIZE, height=THUMB_SIZE, bg="#07070a",
            bd=0, highlightthickness=0,
        )
        self._img_holder.pack(padx=1, pady=1)
        self._img_holder.pack_propagate(False)
        self.lbl_image = tk.Label(
            self._img_holder, text="Ảnh", bg="#07070a", fg=COLOR_MUTED, font=("Segoe UI", sz),
            cursor="hand2",
        )
        self.lbl_image.place(relx=0.5, rely=0.5, anchor="center")
        # Click ảnh = phóng to (không tải)
        self.lbl_image.bind("<Button-1>", lambda _e: self._zoom_current_image())
        self._img_holder.bind("<Button-1>", lambda _e: self._zoom_current_image())
        self._reg_font(self.lbl_image)

        mini = tk.Frame(img_col, bg=COLOR_CARD, bd=0, highlightthickness=0)
        mini.pack(fill=tk.X)
        self._img_holder_b = tk.Frame(mini, width=THUMB_SIZE, height=28, bg="#07070a", bd=0, highlightthickness=0)
        self._img_holder_b.pack(padx=1, pady=1)
        self._img_holder_b.pack_propagate(False)
        self.lbl_image_b = tk.Label(
            self._img_holder_b, text="B", bg="#07070a", fg=COLOR_MUTED, font=("Segoe UI", max(5, sz - 1)),
        )
        self.lbl_image_b.place(relx=0.5, rely=0.5, anchor="center")
        self.lbl_image_b.bind("<Button-1>", lambda _e: self._open_compare())
        self._reg_font(self.lbl_image_b)

        info = tk.Frame(body, bg=COLOR_BG)
        info.grid(row=0, column=1, sticky="ew")
        info.columnconfigure(1, weight=1)

        rows = (
            ("order_id", "Mã", COLOR_SUCCESS),
            ("product_name", "SP", COLOR_ACCENT),
            ("variant_info", "BT", COLOR_TEXT),
            ("badge", "Loại", COLOR_EMB),
        )
        self._copy_labels: dict[str, tk.Label] = {}
        for i, (key, title, fg) in enumerate(rows):
            lt = tk.Label(info, text=title, font=("Segoe UI", sz), fg=COLOR_MUTED, bg=COLOR_BG, width=3)
            lt.grid(row=i, column=0, sticky="w")
            self._reg_font(lt)
            val = tk.Label(
                info, text="—", font=("Segoe UI", sz, "bold"), fg=fg, bg=COLOR_CARD,
                anchor="w", padx=2, pady=0, cursor="hand2", bd=0, highlightthickness=0,
            )
            val.grid(row=i, column=1, sticky="ew")
            val.bind("<Button-1>", lambda e, k=key: self._copy_field(k))
            self._copy_labels[key] = val
            self._reg_font(val, "ui", True)

        btns = tk.Frame(body, bg=COLOR_BG)
        btns.grid(row=1, column=1, sticky="w")
        for text, cmd, fg in (
            ("⬇", self._download_portal_image, "#f472b6"),
            ("👁", self._review_folder_images, "#38bdf8"),
            ("🔍", self._zoom_current_image, "#a78bfa"),
            ("📌", self._toggle_pin_current, "#ffd60a"),
            ("A", self._pin_as_a, "#00d2ff"),
            ("B", self._pin_as_b, "#ff9d00"),
            ("⚖", self._open_compare, "#c77dff"),
            ("⚡", self._run_auto, "#ff9900"),
            ("📸", self._take_screenshot, "#cc66ff"),
            ("📋", self._copy_folder_path, COLOR_SUCCESS),
            ("📂", self._open_current_folder, COLOR_ACCENT),
            ("📊", self._open_order_stats, "#fbbf24"),
            ("📝", self._copy_order_to_log, "#34d399"),
            ("↻", self._refresh_file_status, COLOR_MUTED),
            ("🗑", self._reset_produce_data, COLOR_DANGER),
        ):
            b = tk.Button(
                btns, text=text, font=("Segoe UI", sz), bg=COLOR_CARD, fg=fg,
                activebackground=COLOR_CARD, bd=0, padx=2, pady=0, cursor="hand2", command=cmd,
            )
            b.pack(side=tk.LEFT, padx=(0, 1))
            self._reg_font(b)

        pos_row = tk.Frame(body, bg=COLOR_BG)
        pos_row.grid(row=2, column=1, sticky="ew")
        lt_vt = tk.Label(pos_row, text="VT", font=("Segoe UI", sz), fg=COLOR_MUTED, bg=COLOR_BG, width=3)
        lt_vt.pack(side=tk.LEFT)
        self._reg_font(lt_vt)
        self._pos_box = tk.Frame(pos_row, bg=COLOR_BG)
        self._pos_box.pack(side=tk.LEFT)
        for code in CHECKBOX_ORDER:
            var = tk.BooleanVar(value=False)
            chk = tk.Checkbutton(
                self._pos_box, text=code, variable=var,
                font=("Consolas", sz, "bold"), fg=COLOR_ACCENT, bg=COLOR_BG,
                activebackground=COLOR_BG, activeforeground=COLOR_SUCCESS,
                selectcolor=COLOR_CARD, padx=0,
                command=lambda c=code: self._on_position_click(c),
            )
            chk.pack(side=tk.LEFT)
            chk.pack_forget()
            self._chk_vars[code] = var
            self._chk_widgets[code] = chk
            self._reg_font(chk, "mono", True)

        self._auto_copy_var = tk.BooleanVar(value=False)
        chk_copy = tk.Checkbutton(
            pos_row, text="Copy", variable=self._auto_copy_var,
            font=("Segoe UI", sz), fg=COLOR_MUTED, bg=COLOR_BG,
            activebackground=COLOR_BG, activeforeground=COLOR_SUCCESS,
            selectcolor=COLOR_CARD, padx=0,
        )
        chk_copy.pack(side=tk.LEFT, padx=(1, 0))
        self._reg_font(chk_copy)
        b_copy = tk.Button(
            pos_row, text="📋", font=("Segoe UI", sz), bg=COLOR_CARD, fg=COLOR_SUCCESS,
            activebackground=COLOR_CARD, bd=0, padx=2, pady=0, cursor="hand2",
            command=self._copy_formatted_stem,
        )
        b_copy.pack(side=tk.LEFT)
        self._reg_font(b_copy)
        self._stem_var = tk.StringVar(value="")
        lbl_stem = tk.Label(pos_row, textvariable=self._stem_var, font=("Consolas", sz), fg=COLOR_MUTED, bg=COLOR_BG)
        lbl_stem.pack(side=tk.LEFT, padx=(1, 0))
        self._reg_font(lbl_stem, "mono")

        # ── Bottom split: trái lịch sử | phải check file (giãn theo cửa sổ) ──
        split = tk.Frame(self.frame, bg=COLOR_BG)
        split.grid(row=2, column=0, sticky="nsew")
        split.columnconfigure(0, weight=3)
        split.columnconfigure(1, weight=2)
        split.rowconfigure(0, weight=1)

        # LEFT — history
        table_box = tk.Frame(split, bg=COLOR_TABLE_BG, bd=0, highlightthickness=0)
        table_box.grid(row=0, column=0, sticky="nsew", padx=(0, 2))
        table_box.columnconfigure(0, weight=1)
        table_box.rowconfigure(0, weight=1)

        cols = ("st", "time", "order_id", "product", "ftype")
        self.tree = ttk.Treeview(
            table_box, columns=cols, show="headings", height=TABLE_HEIGHT,
            selectmode="extended",
        )
        for c, w, t in (
            ("st", 18, "●"),
            ("time", 36, "Giờ"),
            ("order_id", 70, "Mã"),
            ("product", 90, "SP"),
            ("ftype", 28, "Loại"),
        ):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w", stretch=(c == "product"))
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<ButtonRelease-1>", self._on_row_select)
        self.tree.bind("<Control-ButtonRelease-1>", self._on_row_multi)
        self.tree.bind("<Double-1>", lambda _e: self._open_compare())

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Emb.Treeview",
            background=COLOR_TABLE_BG, foreground=COLOR_TEXT,
            fieldbackground=COLOR_TABLE_BG, font=("Consolas", max(5, sz - 1)),
            rowheight=max(11, sz + 6), borderwidth=0,
        )
        style.configure(
            "Emb.Treeview.Heading",
            background=COLOR_TABLE_HEAD, foreground=COLOR_MUTED,
            font=("Segoe UI", max(5, sz - 1), "bold"), relief="flat", borderwidth=0,
        )
        style.map(
            "Emb.Treeview",
            background=[("selected", COLOR_TABLE_SEL)],
            foreground=[("selected", COLOR_SUCCESS)],
        )
        self.tree.tag_configure("st_green", foreground=COLOR_OK)
        self.tree.tag_configure("st_yellow", foreground=COLOR_WIP)
        self.tree.tag_configure("st_red", foreground=COLOR_MISS)
        self.tree.tag_configure("st_idle", foreground=COLOR_MUTED)
        self.tree.configure(style="Emb.Treeview")
        sb = ttk.Scrollbar(table_box, orient=tk.VERTICAL, command=self.tree.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=sb.set)

        # RIGHT — file check
        right = tk.Frame(split, bg=COLOR_CARD, bd=0, highlightthickness=0)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(1, weight=1)

        rh = tk.Frame(right, bg=COLOR_CARD)
        rh.pack(fill=tk.X, padx=2, pady=1)
        self._files_title = tk.StringVar(value="Files —")
        lbl_ft = tk.Label(rh, textvariable=self._files_title, font=("Segoe UI", sz, "bold"), fg=COLOR_ACCENT, bg=COLOR_CARD)
        lbl_ft.pack(side=tk.LEFT)
        self._reg_font(lbl_ft, "ui", True)
        self._files_sum = tk.StringVar(value="")
        lbl_sum = tk.Label(rh, textvariable=self._files_sum, font=("Consolas", sz, "bold"), fg=COLOR_MUTED, bg=COLOR_CARD)
        lbl_sum.pack(side=tk.RIGHT)
        self._reg_font(lbl_sum, "mono", True)
        self._overall_dot = tk.Label(rh, text="●", font=("Segoe UI", sz + 2), fg=COLOR_IDLE, bg=COLOR_CARD)
        self._overall_dot.pack(side=tk.RIGHT, padx=2)

        # chips required
        self._ext_box = tk.Frame(right, bg=COLOR_CARD)
        self._ext_box.pack(fill=tk.X, padx=2, pady=1)
        self._build_ext_chips("TBF")

        # DXF nút riêng
        dxf_row = tk.Frame(right, bg=COLOR_CARD)
        dxf_row.pack(fill=tk.X, padx=2, pady=(0, 2))
        self.btn_dxf = tk.Button(
            dxf_row, text="DXF ✗", font=("Segoe UI", sz, "bold"),
            bg="#2a1010", fg=COLOR_MISS, activebackground=COLOR_CARD,
            bd=0, padx=6, pady=1, cursor="hand2", command=self._open_dxf_if_any,
        )
        self.btn_dxf.pack(side=tk.LEFT)
        self._reg_font(self.btn_dxf, "ui", True)
        self._dxf_hint = tk.StringVar(value="tùy chọn")
        lbl_dx = tk.Label(dxf_row, textvariable=self._dxf_hint, font=("Segoe UI", max(5, sz - 1)), fg=COLOR_MUTED, bg=COLOR_CARD)
        lbl_dx.pack(side=tk.LEFT, padx=4)
        self._reg_font(lbl_dx)

        legend = tk.Label(
            right, text="● đủ  ● làm  ● thiếu", font=("Segoe UI", max(5, sz - 1)),
            fg=COLOR_MUTED, bg=COLOR_CARD,
        )
        legend.pack(anchor="w", padx=2)
        # color the legend parts roughly via main colors in title already
        self._reg_font(legend)

        self._apply_text_size()

    def _build_ext_chips(self, file_type: str) -> None:
        for w in self._ext_box.winfo_children():
            w.destroy()
        self._ext_labels.clear()
        sz = self._text_size
        for ext in required_exts(file_type):
            lbl = tk.Label(
                self._ext_box, text=ext, font=("Consolas", max(5, sz - 1), "bold"),
                fg=COLOR_IDLE, bg="#0a0a12", padx=3, pady=0,
            )
            lbl.pack(side=tk.LEFT, padx=1, pady=1)
            self._ext_labels[ext.upper()] = lbl
            self._reg_font(lbl, "mono", True)

    def _start_file_poll(self) -> None:
        self._poll_file_status()

    def _poll_file_status(self) -> None:
        prefs = getattr(self, "_settings_prefs", None) or {}
        if prefs.get("file_poll_enabled", True) is False:
            self._poll_job = None
            return
        try:
            self._refresh_file_status(silent=True)
        except Exception:
            pass
        ms = int(prefs.get("file_poll_ms", FILE_POLL_MS))
        ms = max(500, min(10000, ms))
        try:
            self._poll_job = self.app.root.after(ms, self._poll_file_status)
        except Exception:
            self._poll_job = None

    def _refresh_file_status(self, silent: bool = False) -> None:
        ftype = (self._current or {}).get("file_type", "TBF") or "TBF"
        stem = self.get_formatted_stem()
        oid = (self._current or {}).get("order_id", "")
        folder = self._current_folder
        if not folder and oid and self._logic:
            try:
                folder, _ = self._logic.create_order_folder(self._save_folder, oid)
                self._current_folder = folder
            except Exception:
                folder = None

        # rebuild chips if type changed
        req = required_exts(ftype)
        if set(self._ext_labels.keys()) != set(e.upper() for e in req):
            self._build_ext_chips(ftype)

        st = check_folder(
            folder, ftype, stem=stem, order_id=oid,
            also_desktop=_desktop_base(),
        )
        self._file_status = st
        self._files_title.set(f"{st.file_type}")
        self._files_sum.set(st.summary)
        self._overall_dot.config(fg=st.overall_color)

        for s in st.required:
            lbl = self._ext_labels.get(s.ext.upper())
            if not lbl:
                continue
            if s.present:
                lbl.config(fg=COLOR_OK, bg="#0a1a12", text=s.ext)
            else:
                # yellow if some progress overall, else red
                col = COLOR_WIP if st.found > 0 else COLOR_MISS
                lbl.config(fg=col, bg="#1a0a0a" if col == COLOR_MISS else "#1a1608", text=s.ext)

        if st.dxf and st.dxf.present:
            self.btn_dxf.config(text="DXF ✓", fg=COLOR_OK, bg="#0a1a12")
            self._dxf_hint.set(os.path.basename(st.dxf.path or "")[:18])
        else:
            self.btn_dxf.config(text="DXF ✗", fg=COLOR_MISS, bg="#2a1010")
            self._dxf_hint.set("chưa có")

        # cập nhật chấm màu trên dòng history hiện tại
        self._update_history_status_dot(st)
        if not silent and st.overall != "idle":
            self.app.log(
                f"Files {st.file_type}: {st.summary} · DXF={'có' if st.dxf and st.dxf.present else 'không'}",
                "success" if st.overall == "green" else ("accent" if st.overall == "yellow" else "danger"),
            )

    def _update_history_status_dot(self, st: FolderFileStatus) -> None:
        if not self._current:
            return
        fp = self._order_fingerprint(self._current)
        tag = f"st_{st.overall}" if st.overall in ("green", "yellow", "red") else "st_idle"
        dot = {"green": "●", "yellow": "●", "red": "●", "idle": "○"}.get(st.overall, "○")
        for item in self._history:
            if item.get("_fingerprint") == fp or item.get("order_id") == self._current.get("order_id"):
                item["_file_overall"] = st.overall
                rid = item.get("_row_id")
                if rid and self.tree.exists(rid):
                    vals = list(self.tree.item(rid, "values"))
                    if vals:
                        vals[0] = dot
                        self.tree.item(rid, values=vals, tags=(tag,))
                break

    def _open_dxf_if_any(self) -> None:
        st = self._file_status
        if st and st.dxf and st.dxf.present and st.dxf.path:
            try:
                os.startfile(st.dxf.path)
                self.app.log(f"Mở DXF: {os.path.basename(st.dxf.path)}", "accent")
                return
            except OSError as exc:
                self.app.log(f"Mở DXF lỗi: {exc}", "danger")
                return
        # không có → mở folder
        folder = self.ensure_folder()
        if folder:
            self._open_folder(folder, "Folder (chưa có DXF)")
        else:
            self.app.log("Chưa có DXF trong folder", "danger")

    def _init_backend(self) -> None:
        try:
            self._logic = load_emb_logic()
            self._auto_cls = load_auto_workflow()
            self._workflow_host = EmbWorkflowGuiAdapter(self)
            self.status_var.set(":5000 · WS:5001 · clip")
            self._refresh_today_stat()
            self.app.log("EMB receiver sẵn sàng (HTTP:5000 · WS:5001 · clip)", "accent")
        except Exception as exc:
            self.status_var.set(f"Lỗi ChestEMB: {exc}")
            self.app.log(f"EMB: {exc}", "danger")
            return

        self._server = EmbDataServer(self._on_raw_data, self.app.root)
        self._server.start()
        self._setup_hotkeys()

    def _setup_hotkeys(self) -> None:
        if self._hotkey_handlers:
            return
        try:
            import keyboard
        except ImportError:
            self.app.log("EMB: thiếu keyboard — không đăng ký phím tắt", "danger")
            return

        def emit(action: str) -> None:
            self.app.root.after(0, lambda a=action: self._on_hotkey(a))

        bindings = (
            ("ctrl+b", "ctrl+b"),
            ("alt+e", "alt+e"),
            ("alt+v", "alt+v"),
            ("alt+d", "alt+d"),
            ("alt+p", "alt+p"),
        )
        try:
            for combo, action in bindings:
                handler = keyboard.add_hotkey(combo, lambda a=action: emit(a), suppress=False)
                self._hotkey_handlers.append(handler)
            self.app.log(
                "Phím: Ctrl+B auto · Alt+E mở folder · Alt+V copy path folder · "
                "Alt+D diff · Alt+P pin",
                "accent",
            )
        except Exception as exc:
            self.app.log(f"EMB phím tắt lỗi: {exc}", "danger")

    def _on_hotkey(self, action: str) -> None:
        try:
            if action == "ctrl+b":
                self._run_auto()
            elif action == "alt+e":
                # Mở folder đơn đang làm
                self._open_current_folder()
            elif action == "alt+v":
                # Copy đường dẫn folder đã tạo
                self._copy_folder_path()
            elif action == "alt+d":
                self._open_compare()
            elif action == "alt+p":
                self._toggle_pin_current()
        except Exception as exc:
            self.app.log(f"Phím tắt lỗi ({action}): {exc}", "danger")

    def _teardown_hotkeys(self) -> None:
        if not self._hotkey_handlers:
            return
        try:
            import keyboard

            for handler in self._hotkey_handlers:
                try:
                    keyboard.remove_hotkey(handler)
                except Exception:
                    pass
        except ImportError:
            pass
        self._hotkey_handlers.clear()

    @staticmethod
    def _strip_num_suffix(path: str) -> str:
        """Bỏ _1/_2 trước phần mở rộng (vd. stem_2.dxf → stem.dxf)."""
        folder = os.path.dirname(path)
        base = os.path.basename(path)
        name, ext = os.path.splitext(base)
        if name.endswith("_1") or name.endswith("_2"):
            name = name[:-2]
        return os.path.join(folder, name + ext)

    def _find_po_dxf_paths(self) -> tuple[str | None, str | None]:
        stem = self.get_formatted_stem()
        if not stem:
            return None, None

        folder = self.ensure_folder()
        search_dirs: list[str] = []
        if folder:
            search_dirs.append(folder)
        search_dirs.append(_desktop_base())

        po_path = None
        dxf_path = None
        ftype = (self._current or {}).get("file_type", "TBF").upper()

        for directory in search_dirs:
            for ext in (ftype, "TBF", "DST"):
                candidate = os.path.join(directory, f"{stem}.{ext}")
                if os.path.isfile(candidate):
                    po_path = candidate
                    break
            if po_path:
                break

        for directory in search_dirs:
            for name in (f"{stem}.dxf", f"{stem}_2.dxf", f"{stem}_1.dxf"):
                candidate = os.path.join(directory, name)
                if os.path.isfile(candidate):
                    dxf_path = candidate
                    break
            if dxf_path:
                break

        return po_path, dxf_path

    def _copy_po_dxf_paths(self) -> None:
        po_path, dxf_path = self._find_po_dxf_paths()
        lines: list[str] = []
        if po_path:
            lines.append(os.path.abspath(self._strip_num_suffix(po_path)))
        if dxf_path:
            lines.append(os.path.abspath(self._strip_num_suffix(dxf_path)))

        if not lines:
            self.app.log("Chưa có file PO/DXF để copy", "danger")
            return

        payload = "\n".join(lines)
        self._copy_text(payload, "PO+DXF")

    def _open_current_folder(self) -> None:
        """Alt+E — mở folder đơn đang làm (tạo nếu chưa có)."""
        path = self.ensure_folder()
        if path:
            self._open_folder(path, "Đơn đang làm")
            self.app.log(f"📂 Mở folder: {os.path.basename(path)}", "accent")
        else:
            self.app.log("Alt+E: chưa có đơn / folder", "danger")

    def _open_order_stats(self) -> None:
        """📊 Thống kê + mở folder ngày (Desktop\\YYYY-MM-DD) chứa ma_don.txt."""
        from tkinter import messagebox

        st = get_emb_today_stats()
        folder = open_today_stats_folder()
        n = st.get("ids_in_text") or st.get("orders") or 0
        fc = st.get("folder_count", 0)
        msg = (
            f"Hôm nay ({st.get('date')}):\n"
            f"  • {n} đơn tool (ma_don.txt, không trùng)\n"
            f"  • {fc} folder trên Desktop\\ngày\n"
            f"  • {st.get('orders', 0)} đơn app · Patch/DXF {st.get('patch_dxf', 0)}\n"
            f"  • Telegram: đơn mới tự gửi (trùng = không gửi)\n\n"
            f"Folder:\n{folder}\n\n"
            f"  ma_don.txt       — chỉ mã\n"
            f"  lich_su_don.txt  — giờ + mã + SP\n"
            f"  thong_ke_don.txt — tóm tắt"
        )
        self.app.log(f"📊 Thống kê: tool={n} · folder={fc} · {folder}", "accent")
        messagebox.showinfo("Thống kê đơn hôm nay", msg, parent=self.app.root)

    def _copy_order_to_log(self) -> None:
        """📝 Ghi mã đơn đang làm (nếu mới: +1 + Telegram; trùng: chỉ copy)."""
        oid = ""
        prod = ""
        if self._current:
            oid = str(self._current.get("order_id") or "").strip()
            prod = str(self._current.get("product_name") or "").strip()
        if not oid or oid == "—":
            self.app.log("📝 Chưa có mã đơn để ghi", "danger")
            return
        rec = record_emb_order(
            oid,
            prod,
            merged=False,
            notify_telegram=True,
            base_dir=getattr(self.app, "base_dir", None),
        )
        try:
            self.app.root.clipboard_clear()
            self.app.root.clipboard_append(oid)
        except Exception:
            pass
        if hasattr(self.app, "refresh_daily_stats"):
            try:
                self.app.refresh_daily_stats()
            except Exception:
                pass
        self._refresh_today_stat()
        if rec.get("new"):
            self.app.log(
                f"📝 Đơn mới {oid} · tool={rec.get('tool_count')} · folder={rec.get('folder_count')} · Telegram",
                "success",
            )
        else:
            self.app.log(f"📝 Trùng {oid} — không +1 / không gửi lại Telegram (đã copy mã)", "accent")

    def _copy_all_today_ids(self) -> None:
        """Copy toàn bộ mã hôm nay từ ma_don.txt."""
        text = copy_today_ids_text()
        if not text:
            self.app.log("Chưa có mã trong ma_don.txt hôm nay", "danger")
            return
        try:
            self.app.root.clipboard_clear()
            self.app.root.clipboard_append(text)
            n = len([x for x in text.splitlines() if x.strip()])
            self.app.log(f"📋 Đã copy {n} mã hôm nay", "success")
        except Exception as e:
            self.app.log(f"Copy lỗi: {e}", "danger")

    def _on_raw_data(self, data: dict) -> None:
        if "__error__" in data:
            self.status_var.set(str(data["__error__"]))
            self.app.log(f"EMB server: {data['__error__']}", "danger")
            return
        try:
            parsed = self._logic.parse_details(data)
            oid = parsed.get("order_id", "")
            if not oid or oid == "Unknown":
                return
            parsed["_received_at"] = datetime.now().strftime("%H:%M:%S")
            parsed["_raw_image_url"] = parsed.get("image_url", "")
            merged = self._show_order(parsed, add_history=True)
            base = getattr(self.app, "base_dir", None)

            def _tg_done(ok: bool, detail: str, order=oid) -> None:
                def _ui():
                    if ok:
                        self.app.log(f"✈ Telegram OK: {order}", "success")
                        try:
                            self.status_var.set(f"TG ✓ {order[:20]}")
                        except Exception:
                            pass
                    else:
                        self.app.log(f"✈ Telegram LỖI: {order} — {detail}", "danger")
                try:
                    self.app.root.after(0, _ui)
                except Exception:
                    pass

            # TỰ ĐỘNG: +1 (nếu mới) + gửi Telegram — không cần phím tắt / bấm nút
            rec = record_emb_order(
                oid,
                parsed.get("product_name", ""),
                merged=merged,
                notify_telegram=True,
                base_dir=base,
                on_telegram_done=_tg_done,
            )
            self._refresh_today_stat()
            if hasattr(self.app, "refresh_daily_stats"):
                self.app.root.after(0, self.app.refresh_daily_stats)
            if not rec.get("new"):
                cnt = parsed.get("_dup_count", 1)
                self.app.log(
                    f"EMB trùng: {oid}"
                    + (f" (gộp ×{cnt})" if merged else "")
                    + " — không +1, không gửi Telegram lại",
                    "accent",
                )
            else:
                self.app.log(
                    f"EMB nhận: {oid} · {parsed.get('product_name', '-')} "
                    f"· tool={rec.get('tool_count', 0)} · folder={rec.get('folder_count', 0)} "
                    f"· đang gửi Telegram…",
                    "success",
                )
            # Tùy chọn: tự tải ảnh Desktop
            prefs = getattr(self, "_settings_prefs", None)
            if prefs is None:
                try:
                    import json
                    path = os.path.join(getattr(self.app, "base_dir", ""), "acc2019_window.json")
                    if os.path.isfile(path):
                        with open(path, encoding="utf-8") as f:
                            prefs = json.load(f)
                            self._settings_prefs = prefs
                except Exception:
                    prefs = {}
            if prefs and prefs.get("auto_download_image"):
                self.app.root.after(200, self._download_portal_image)
        except Exception as exc:
            self.app.log(f"EMB parse lỗi: {exc}", "danger")

    def _order_fingerprint(self, order: dict) -> str:
        """Khóa gộp — cùng mã đơn + SP + size + loại = 1 dòng."""
        parts = (
            order.get("order_id", ""),
            order.get("product_name", ""),
            order.get("size", ""),
            order.get("file_type", ""),
            order.get("variant_info", ""),
        )
        return "|".join(str(p).strip().lower() for p in parts)

    def _show_order(self, order: dict, *, add_history: bool = False) -> bool:
        """Hiển thị đơn. Trả về True nếu gộp vào dòng đã có (trùng)."""
        merged = False
        self._current = order
        self._current_folder = None
        if self._workflow_host:
            self._workflow_host.current_folder = None

        oid = order.get("order_id", "—")
        prod = order.get("product_name", "—")
        variant = order.get("variant_info", "—")
        ftype = order.get("file_type", "UNK")
        size = order.get("size", "-")
        dims = order.get("dims", "")
        badge = f"{ftype} | {size}"
        if dims:
            badge += f" | {dims}"

        self._copy_labels["order_id"].config(text=oid[:28] + ("…" if len(oid) > 28 else ""))
        self._copy_labels["product_name"].config(text=prod[:36] + ("…" if len(prod) > 36 else ""))
        self._copy_labels["variant_info"].config(text=variant[:32] + ("…" if len(variant) > 32 else ""))
        self._copy_labels["badge"].config(text=badge)

        # Không ghi/Telegram ở đây — chỉ khi nhận đơn (record_emb_order)
        path, _created = self._logic.create_order_folder(self._save_folder, oid)
        if path:
            self._current_folder = path
            record_last_folder(path)
            if self._workflow_host:
                self._workflow_host.current_folder = path

        self._update_position_checkboxes(order)
        self._refresh_stem_preview()
        if add_history:
            merged = self._add_history_row(order)
        self._load_image_async(order.get("image_url", ""), oid)
        self._refresh_file_status(silent=True)
        # (11) Chat LAN: đang làm mã…
        try:
            chat = getattr(self.app, "chat_panel", None)
            if chat and hasattr(chat, "broadcast_work_status") and oid and oid != "—":
                chat.broadcast_work_status(str(oid), str(prod or ""))
        except Exception:
            pass
        return merged

    def _update_position_checkboxes(self, order: dict) -> None:
        codes = detect_position_codes(
            order.get("product_name", ""),
            order.get("variant_info", ""),
        )
        order["_position_codes"] = codes
        visible = sort_for_display(codes)

        for code, chk in self._chk_widgets.items():
            chk.pack_forget()
            self._chk_vars[code].set(False)

        for code in visible:
            chk = self._chk_widgets.get(code)
            if chk:
                chk.pack(side=tk.LEFT)

        if len(visible) == 1:
            self._chk_vars[visible[0]].set(True)
        elif "4" in visible:
            self._chk_vars["4"].set(True)
        self._refresh_stem_preview()
        if self._auto_copy_var.get():
            self._copy_formatted_stem()

    def _on_position_click(self, selected: str) -> None:
        if not self._chk_vars[selected].get():
            return
        for code, var in self._chk_vars.items():
            if code != selected:
                var.set(False)
        self._refresh_stem_preview()
        if self._auto_copy_var.get():
            self._copy_formatted_stem()

    def get_formatted_stem(self) -> str | None:
        oid = self.get_order_id_for_patch()
        if not oid:
            return None
        pos = self.get_selected_position() or "4"
        return f"{oid}_({pos})"

    def _refresh_stem_preview(self) -> None:
        stem = self.get_formatted_stem()
        self._stem_var.set(stem[:22] + ("…" if stem and len(stem) > 22 else "") if stem else "")
        # stem đổi → recheck file
        if self._current:
            try:
                self._refresh_file_status(silent=True)
            except Exception:
                pass

    def _copy_formatted_stem(self) -> None:
        stem = self.get_formatted_stem()
        if stem:
            self._copy_text(stem, "mã_(VT)")
            self._refresh_stem_preview()
        else:
            self.app.log("Chưa có mã đơn để copy", "danger")

    def get_selected_position(self) -> str | None:
        for code, var in self._chk_vars.items():
            if var.get() and self._chk_widgets[code].winfo_ismapped():
                return code
        return None

    def get_order_id_for_patch(self) -> str | None:
        oid = (self._current or {}).get("order_id", "")
        if oid and oid not in ("—", "Unknown", ""):
            return oid.replace("/", "-").replace("\\", "-").replace(":", "-")
        return None

    def get_patch_output_dir(self) -> str | None:
        return self.ensure_folder()

    def _row_values(self, order: dict) -> tuple[str, str, str, str, str]:
        time_txt = order.get("_received_at", "")
        dup = int(order.get("_dup_count", 1))
        if dup > 1:
            time_txt = f"{time_txt}×{dup}"
        prod = (order.get("product_name", "") or "")[:18]
        if len((order.get("product_name", "") or "")) > 18:
            prod += "…"
        overall = order.get("_file_overall", "idle")
        dot = {"green": "●", "yellow": "●", "red": "●"}.get(overall, "○")
        return (
            dot,
            time_txt,
            order.get("order_id", ""),
            prod,
            order.get("file_type", ""),
        )

    def _add_history_row(self, order: dict) -> bool:
        """Thêm hoặc gộp dòng trùng. Trả về True nếu gộp."""
        fp = self._order_fingerprint(order)
        order["_fingerprint"] = fp

        for i, item in enumerate(self._history):
            if item.get("_fingerprint") == fp:
                row_id = item["_row_id"]
                order["_row_id"] = row_id
                order["_dup_count"] = int(item.get("_dup_count", 1)) + 1
                order["_file_overall"] = item.get("_file_overall", order.get("_file_overall", "idle"))
                self._history.pop(i)
                self._history.insert(0, order)
                if self.tree.exists(row_id):
                    tag = f"st_{order.get('_file_overall', 'idle')}"
                    if tag not in ("st_green", "st_yellow", "st_red"):
                        tag = "st_idle"
                    self.tree.item(row_id, values=self._row_values(order), tags=(tag,))
                    self.tree.move(row_id, "", 0)
                return True

        self._row_seq += 1
        order["_row_id"] = f"r{self._row_seq}"
        order["_dup_count"] = 1
        self._history.insert(0, order)
        self._history = self._history[:MAX_HISTORY]
        # rebuild để pin luôn trên đầu
        try:
            self._rebuild_history_tree()
        except Exception:
            tag = f"st_{order.get('_file_overall', 'idle')}"
            if tag not in ("st_green", "st_yellow", "st_red"):
                tag = "st_idle"
            vals = list(self._row_values(order))
            if self._is_pinned(order):
                vals[0] = "📌"
            self.tree.insert("", 0, iid=order["_row_id"], values=tuple(vals), tags=(tag,))

        children = self.tree.get_children()
        if len(children) > MAX_HISTORY + len(self._pinned):
            for iid in children[MAX_HISTORY + len(self._pinned):]:
                self.tree.delete(iid)
                self._history = [h for h in self._history if h.get("_row_id") != iid]
        return False

    def _on_row_select(self, _event=None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        # multi-select 2 dòng → tự pin A/B (diff)
        if len(sel) >= 2:
            self._pin_from_row_ids(sel[0], sel[1])
        row_id = sel[0]
        item = self._find_by_row(row_id)
        if item:
            self._show_order(item, add_history=False)

    def _on_row_multi(self, _event=None) -> None:
        sel = self.tree.selection()
        if len(sel) >= 2:
            self._pin_from_row_ids(sel[0], sel[1])

    def _find_by_row(self, row_id: str) -> dict | None:
        for item in self._history:
            if item.get("_row_id") == row_id:
                return item
        for o in self._pinned.values():
            if o.get("_row_id") == row_id:
                return o
        return None

    def _pin_from_row_ids(self, id_a: str, id_b: str) -> None:
        a, b = self._find_by_row(id_a), self._find_by_row(id_b)
        if a:
            self._pin_a = dict(a)
            self._pin_a_bytes = a.get("_img_bytes")
        if b:
            self._pin_b = dict(b)
            self._pin_b_bytes = b.get("_img_bytes")
            self._update_mini_b()
        self._refresh_pin_status()
        if a and b:
            self.app.log(
                f"⚖ Pin A={a.get('order_id','?')[:16]} · B={b.get('order_id','?')[:16]}",
                "accent",
            )

    def _pin_as_a(self) -> None:
        if not self._current:
            self.app.log("Chưa có đơn để pin A", "danger")
            return
        self._pin_a = dict(self._current)
        self._pin_a_bytes = self._img_bytes or self._current.get("_img_bytes")
        if self._pin_a_bytes:
            self._pin_a["_img_bytes"] = self._pin_a_bytes
        self._refresh_pin_status()
        self.app.log(f"Pin A: {self._pin_a.get('order_id', '?')}", "accent")

    def _pin_as_b(self) -> None:
        if not self._current:
            self.app.log("Chưa có đơn để pin B", "danger")
            return
        self._pin_b = dict(self._current)
        self._pin_b_bytes = self._img_bytes or self._current.get("_img_bytes")
        if self._pin_b_bytes:
            self._pin_b["_img_bytes"] = self._pin_b_bytes
        self._update_mini_b()
        self._refresh_pin_status()
        self.app.log(f"Pin B: {self._pin_b.get('order_id', '?')}", "accent")

    def _refresh_pin_status(self) -> None:
        parts = []
        if self._pin_a:
            parts.append(f"A:{str(self._pin_a.get('order_id', ''))[:10]}")
        if self._pin_b:
            parts.append(f"B:{str(self._pin_b.get('order_id', ''))[:10]}")
        self._pin_status.set(" · ".join(parts))

    def _update_mini_b(self) -> None:
        raw = self._pin_b_bytes or (self._pin_b or {}).get("_img_bytes")
        if not raw:
            self.lbl_image_b.config(image="", text="Pin B — chọn đơn rồi bấm B")
            self._photo_b = None
            return
        try:
            from PIL import Image, ImageTk

            img = Image.open(io.BytesIO(raw)).convert("RGB")
            img.thumbnail((THUMB_SIZE, 34), Image.Resampling.LANCZOS)
            self._photo_b = ImageTk.PhotoImage(img)
            self.lbl_image_b.config(image=self._photo_b, text="")
        except Exception:
            self.lbl_image_b.config(image="", text="B: lỗi ảnh")
            self._photo_b = None

    def _resolve_compare_pair(self) -> tuple[dict | None, dict | None, bytes | None, bytes | None]:
        """Ưu tiên pin A/B; nếu thiếu → 2 dòng tree / current + history[1]."""
        a, b = self._pin_a, self._pin_b
        ba, bb = self._pin_a_bytes, self._pin_b_bytes

        sel = list(self.tree.selection())
        if (not a or not b) and len(sel) >= 2:
            ra, rb = self._find_by_row(sel[0]), self._find_by_row(sel[1])
            if ra and not a:
                a, ba = ra, ra.get("_img_bytes")
            if rb and not b:
                b, bb = rb, rb.get("_img_bytes")

        if not a and self._current:
            a = self._current
            ba = self._img_bytes or self._current.get("_img_bytes")
        if not b and len(self._history) > 1:
            for h in self._history:
                if h.get("order_id") != (a or {}).get("order_id"):
                    b = h
                    bb = h.get("_img_bytes")
                    break
        return a, b, ba, bb

    def _open_compare(self) -> None:
        """Diff thumbnail 2 đơn (Alt+D)."""
        a, b, ba, bb = self._resolve_compare_pair()
        if not a or not b:
            # auto: current + history[1] hoặc pin A/B
            if self._current and len(self._history) > 1:
                a = self._current
                ba = self._img_bytes or self._current.get("_img_bytes")
                for h in self._history:
                    if h.get("order_id") != a.get("order_id"):
                        b = h
                        bb = h.get("_img_bytes")
                        break
            if not a or not b:
                self.app.log("⚖ Diff: cần 2 đơn — bấm A/B hoặc chọn 2 dòng", "danger")
                return

        def ensure_and_show():
            nonlocal ba, bb
            ba = ba or self._fetch_image_bytes(a)
            bb = bb or self._fetch_image_bytes(b)
            self.app.root.after(0, lambda: self._show_compare_window(a, b, ba, bb))

        threading.Thread(target=ensure_and_show, daemon=True).start()
        self.app.log(
            f"⚖ Diff: {a.get('order_id','?')[:18]} ↔ {b.get('order_id','?')[:18]}",
            "accent",
        )

    def _fetch_image_bytes(self, order: dict) -> bytes | None:
        if order.get("_img_bytes"):
            return order["_img_bytes"]
        url = order.get("_raw_image_url") or order.get("image_url") or ""
        if url:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "ACC2019/2.9"})
                with urllib.request.urlopen(req, timeout=20) as resp:
                    data = resp.read()
                    order["_img_bytes"] = data
                    return data
            except Exception:
                pass
        oid = order.get("order_id", "")
        if oid and self._logic:
            try:
                folder, _ = self._logic.create_order_folder(self._save_folder, oid)
                if folder:
                    for name in (f"{oid}.png", "1.png", f"{oid}.jpg", "1.jpg"):
                        p = os.path.join(folder, name)
                        if os.path.isfile(p):
                            with open(p, "rb") as f:
                                data = f.read()
                            order["_img_bytes"] = data
                            return data
            except Exception:
                pass
        return None

    def _show_compare_window(
        self, a: dict, b: dict, ba: bytes | None, bb: bytes | None,
    ) -> None:
        if self._compare_win is not None:
            try:
                self._compare_win.destroy()
            except tk.TclError:
                pass

        colors = {}
        if getattr(self.app, "theme_mgr", None):
            colors = self.app.theme_mgr.colors
        bg = colors.get("bg", COLOR_BG)
        card = colors.get("card", COLOR_CARD)
        text = colors.get("text", COLOR_TEXT)
        muted = colors.get("muted", COLOR_MUTED)
        accent = colors.get("accent", COLOR_ACCENT)
        success = colors.get("success", COLOR_SUCCESS)
        emb = colors.get("emb", COLOR_EMB)

        win = tk.Toplevel(self.app.root)
        self._compare_win = win
        win.title("So sánh thumbnail 2 đơn")
        win.configure(bg=bg)
        win.geometry("460x320")
        win.minsize(400, 280)
        win.attributes("-topmost", True)

        tk.Label(
            win, text="⚖ So sánh 2 đơn", font=("Segoe UI", 9, "bold"),
            fg=accent, bg=bg,
        ).pack(pady=(4, 2))

        sim = None
        if ba and bb:
            sim = _image_similarity(ba, bb)
        sim_txt = f"Giống ~{sim:.0f}%" if sim is not None else "Không tính được %"
        sim_fg = success if (sim or 0) >= 85 else (emb if (sim or 0) < 50 else accent)
        tk.Label(win, text=sim_txt, font=("Segoe UI", 8, "bold"), fg=sim_fg, bg=bg).pack()

        row = tk.Frame(win, bg=bg)
        row.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

        photos: list = []

        def side(parent, order, raw, label, col):
            box = tk.Frame(parent, bg=card, bd=0, highlightthickness=1, highlightbackground=accent)
            box.grid(row=0, column=col, sticky="nsew", padx=3)
            parent.columnconfigure(col, weight=1)
            tk.Label(box, text=label, font=("Segoe UI", 7, "bold"), fg=accent, bg=card).pack(pady=(2, 0))
            holder = tk.Frame(box, width=COMPARE_SIZE, height=COMPARE_SIZE, bg="#07070a")
            holder.pack(padx=4, pady=2)
            holder.pack_propagate(False)
            lbl = tk.Label(holder, text="Không ảnh", bg="#07070a", fg=muted, font=("Segoe UI", 7))
            lbl.place(relx=0.5, rely=0.5, anchor="center")
            if raw:
                try:
                    from PIL import Image, ImageTk

                    im = Image.open(io.BytesIO(raw)).convert("RGB")
                    im.thumbnail((COMPARE_SIZE, COMPARE_SIZE), Image.Resampling.LANCZOS)
                    ph = ImageTk.PhotoImage(im)
                    photos.append(ph)
                    lbl.config(image=ph, text="")
                except Exception:
                    pass
            oid = str(order.get("order_id", "—"))
            prod = str(order.get("product_name", "—"))
            badge = f"{order.get('file_type', '')} | {order.get('size', '')}"
            for line, fg in (
                (oid[:32], success),
                (prod[:36], text),
                (badge, emb),
            ):
                tk.Label(box, text=line, font=("Segoe UI", 7), fg=fg, bg=card, wraplength=200).pack(
                    anchor="w", padx=4,
                )
            def copy_oid(o=oid):
                try:
                    self.app.root.clipboard_clear()
                    self.app.root.clipboard_append(o)
                    self.app.log(f"Copy mã: {o[:40]}", "accent")
                except Exception:
                    pass
            tk.Button(
                box, text="Copy mã", font=("Segoe UI", 7), bg=bg, fg=success,
                bd=0, cursor="hand2", command=copy_oid,
            ).pack(pady=(0, 4))

        side(row, a, ba, "A", 0)
        side(row, b, bb, "B", 1)
        win._photos = photos  # noqa: keep ref

        btns = tk.Frame(win, bg=bg)
        btns.pack(fill=tk.X, pady=(0, 6))
        tk.Button(
            btns, text="Swap A↔B", font=("Segoe UI", 7), bg=card, fg=accent,
            bd=0, padx=8, cursor="hand2",
            command=lambda: (
                self._show_compare_window(b, a, bb, ba),
            ),
        ).pack(side=tk.LEFT, padx=6)
        tk.Button(
            btns, text="Đóng", font=("Segoe UI", 7), bg=card, fg=muted,
            bd=0, padx=8, cursor="hand2", command=win.destroy,
        ).pack(side=tk.RIGHT, padx=6)

        win.protocol("WM_DELETE_WINDOW", win.destroy)

    def _copy_field(self, field: str) -> None:
        if not self._current:
            return
        text = ""
        if field == "order_id":
            text = self._current.get("order_id", "")
        elif field == "product_name":
            text = self._current.get("product_name", "")
        elif field == "variant_info":
            text = self._current.get("variant_info", "")
        elif field == "badge":
            text = self._current.get("size", "")
        if text and text != "—":
            self._copy_text(text, field)

    def _copy_text(self, text: str, label: str = "") -> None:
        try:
            self.app.root.clipboard_clear()
            self.app.root.clipboard_append(text)
            self.app.log(f"Đã copy {label or 'text'}: {text[:40]}", "accent")
        except Exception as exc:
            self.app.log(f"Copy lỗi: {exc}", "danger")

    def _copy_folder_path(self) -> None:
        """Copy đường dẫn folder đơn đã tạo (Alt+V)."""
        path = self.ensure_folder()
        if path:
            abs_path = os.path.abspath(path)
            self._copy_text(abs_path, "folder")
            self.app.log(f"📋 Folder: {abs_path}", "success")
        else:
            self.app.log("Alt+V: chưa có folder đơn", "danger")

    # ── Pin đơn ─────────────────────────────────────────────────────────────

    def _load_pins(self) -> None:
        try:
            import json
            if os.path.isfile(self._pins_path):
                with open(self._pins_path, encoding="utf-8") as f:
                    data = json.load(f)
                pins = data.get("pins", [])
                if isinstance(pins, list):
                    for item in pins[:20]:
                        if isinstance(item, dict) and item.get("order_id"):
                            fp = item.get("_fingerprint") or self._order_fingerprint(item)
                            item["_fingerprint"] = fp
                            self._pinned[fp] = item
        except Exception:
            self._pinned = {}

    def _save_pins(self) -> None:
        try:
            import json
            # chỉ lưu field an toàn (không bytes ảnh)
            out = []
            for fp, o in list(self._pinned.items())[:20]:
                out.append({
                    "order_id": o.get("order_id", ""),
                    "product_name": o.get("product_name", ""),
                    "file_type": o.get("file_type", ""),
                    "size": o.get("size", ""),
                    "variant_info": o.get("variant_info", ""),
                    "image_url": o.get("image_url") or o.get("_raw_image_url", ""),
                    "_fingerprint": fp,
                    "_pinned_at": o.get("_pinned_at", ""),
                })
            with open(self._pins_path, "w", encoding="utf-8") as f:
                json.dump({"pins": out}, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            self.app.log(f"Lưu pin lỗi: {exc}", "danger")

    def _toggle_pin_current(self) -> None:
        if not self._current:
            self.app.log("Chưa có đơn để pin", "danger")
            return
        fp = self._order_fingerprint(self._current)
        if fp in self._pinned:
            del self._pinned[fp]
            self.app.log(f"Bỏ pin: {self._current.get('order_id', '')}", "accent")
        else:
            snap = dict(self._current)
            snap["_fingerprint"] = fp
            snap["_pinned_at"] = datetime.now().strftime("%H:%M:%S")
            # không lưu bytes lớn
            snap.pop("_img_bytes", None)
            self._pinned[fp] = snap
            self.app.log(f"📌 Pin: {snap.get('order_id', '')}", "success")
        self._save_pins()
        self._rebuild_history_tree()

    def _is_pinned(self, order: dict) -> bool:
        fp = order.get("_fingerprint") or self._order_fingerprint(order)
        return fp in self._pinned

    def _rebuild_history_tree(self) -> None:
        """Sắp lại: pin trước, rồi history thường."""
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        # pinned first (not already in history top)
        seen = set()
        for fp, o in self._pinned.items():
            o = dict(o)
            o["_fingerprint"] = fp
            if not o.get("_row_id"):
                self._row_seq += 1
                o["_row_id"] = f"p{self._row_seq}"
            # merge live data from history if exists
            for h in self._history:
                if (h.get("_fingerprint") or self._order_fingerprint(h)) == fp:
                    o = dict(h)
                    o["_pinned_at"] = self._pinned[fp].get("_pinned_at", "")
                    break
            tag = f"st_{o.get('_file_overall', 'idle')}"
            if tag not in ("st_green", "st_yellow", "st_red"):
                tag = "st_idle"
            vals = list(self._row_values(o))
            # mark pin in st col
            vals[0] = "📌"
            self.tree.insert("", "end", iid=o["_row_id"], values=tuple(vals), tags=(tag, "pinned"))
            seen.add(fp)
        self.tree.tag_configure("pinned", foreground="#ffd60a")
        for h in self._history:
            fp = h.get("_fingerprint") or self._order_fingerprint(h)
            if fp in seen:
                continue
            rid = h.get("_row_id")
            if not rid:
                continue
            tag = f"st_{h.get('_file_overall', 'idle')}"
            if tag not in ("st_green", "st_yellow", "st_red"):
                tag = "st_idle"
            try:
                self.tree.insert("", "end", iid=rid, values=self._row_values(h), tags=(tag,))
            except tk.TclError:
                # iid exists
                try:
                    self.tree.item(rid, values=self._row_values(h), tags=(tag,))
                    self.tree.move(rid, "", "end")
                except tk.TclError:
                    pass

    def ensure_folder(self) -> str | None:
        if self._current_folder and os.path.isdir(self._current_folder):
            return self._current_folder
        oid = self._current.get("order_id", "")
        if not oid or oid == "Unknown" or not self._logic:
            self.app.log("Chưa có mã đơn — không tạo folder", "danger")
            return None
        path, _ = self._logic.create_order_folder(self._save_folder, oid)
        if path:
            self._current_folder = path
            record_last_folder(path)
            if self._workflow_host:
                self._workflow_host.current_folder = path
        return path

    def _open_folder(self, path: str, label: str) -> None:
        if not path:
            self.app.log(f"Không có {label}", "danger")
            return
        if not os.path.isdir(path):
            try:
                os.makedirs(path, exist_ok=True)
            except OSError as exc:
                self.app.log(f"Tạo folder lỗi: {exc}", "danger")
                return
        try:
            os.startfile(os.path.abspath(path))
            self.app.log(f"📂 {label}: {os.path.basename(path)}", "accent")
        except OSError as exc:
            self.app.log(f"Mở folder lỗi: {exc}", "danger")

    def _open_last_folder(self) -> None:
        path = get_last_folder()
        if not path and len(self._history) > 1:
            for item in self._history[1:]:
                oid = item.get("order_id", "")
                if oid and self._logic:
                    p, _ = self._logic.create_order_folder(self._save_folder, oid)
                    if p and os.path.isdir(p):
                        path = p
                        break
        self._open_folder(path, "Đơn trước")

    def _open_today_folder(self) -> None:
        self._open_folder(get_today_orders_folder(), "Hôm nay")

    def _run_auto(self) -> None:
        """Auto gốc: PNG → EMB → Export TBF/DST (modules.emb_auto)."""
        # luôn load emb_auto chuẩn
        try:
            from modules.emb_auto import AutoWorkflow
        except Exception as exc:
            self.app.log(f"Không load emb_auto: {exc}", "danger")
            return
        if not self._workflow_host:
            try:
                from modules.emb_bridge import EmbWorkflowGuiAdapter
                self._workflow_host = EmbWorkflowGuiAdapter(self)
            except Exception as exc:
                self.app.log(f"Auto adapter lỗi: {exc}", "danger")
                return

        oid = self._current.get("order_id", "")
        if not oid or oid == "Unknown":
            self.app.log("Chưa có dữ liệu đơn hàng", "danger")
            return
        folder = self.ensure_folder()
        if not folder:
            return

        pos_suffix = self.get_selected_position() or "4"
        final_id = f"{oid}_({pos_suffix})"
        ftype = (self._current.get("file_type") or "TBF").upper()
        if ftype not in ("DST", "TBF"):
            ftype = "TBF"

        context = {
            "order_id": oid,
            "final_id": final_id,
            "folder_path": folder,
            "file_type": ftype,
        }
        self._workflow_host.current_folder = folder
        workflow = AutoWorkflow(self._workflow_host, context)

        def run():
            import time
            time.sleep(0.25)
            try:
                ok = workflow.run()
                tag = "success" if ok else "danger"
                msg = f"⚡ Auto {'OK' if ok else 'FAIL'}: {final_id}"
                self.app.root.after(0, lambda: self.app.log(msg, tag))
            except Exception as exc:
                self.app.root.after(0, lambda e=exc: self.app.log(f"Auto lỗi: {e}", "danger"))

        threading.Thread(target=run, daemon=True).start()
        self.app.log(f"⚡ Auto chạy: {final_id} · {ftype} → {os.path.basename(folder)}", "accent")

    def _download_portal_image(self) -> None:
        """Tải ảnh portal: 1) WS → Tampermonkey click nút Download Image  2) fallback URL."""
        # XPath portal (Download Image):
        # /html/body/.../table/tbody/tr/td[2]/div/div/div/button
        server = self._server
        ws_ok = False
        if server is not None:
            try:
                ws_ok = bool(server.request_download_image())
            except Exception:
                ws_ok = False

        if ws_ok:
            n = server.ws_client_count()
            self.app.log(f"⬇ Ảnh: đã gửi Download Image → browser ({n} client)", "success")
        else:
            self.app.log("⬇ Ảnh: không có WS client — tải trực tiếp URL…", "accent")

        # Lưu ảnh ra Desktop (không vào folder đơn)
        url = ""
        if self._current:
            url = (
                self._current.get("_raw_image_url")
                or self._current.get("image_url")
                or ""
            )
        # Ưu tiên bytes đã cache (thumbnail) nếu không có URL
        cached = self._img_bytes or (self._current or {}).get("_img_bytes")
        if not url and not cached:
            if not ws_ok:
                self.app.log("⬇ Ảnh: chưa có image_url — mở portal rồi bấm TX", "danger")
            return

        oid = (self._current or {}).get("order_id", "design")
        name = str(oid).replace("/", "-").replace("\\", "-").replace(":", "-")[:60]
        desktop = _desktop_base()

        def worker(u=url, base=name, raw=cached):
            data = raw
            ctype = ""
            if not data and u:
                try:
                    req = urllib.request.Request(u, headers={"User-Agent": "ACC2019/2.9"})
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        data = resp.read()
                        ctype = (resp.headers.get("Content-Type") or "").lower()
                except Exception as exc:
                    self.app.root.after(
                        0, lambda: self.app.log(f"⬇ Ảnh URL lỗi: {exc}", "danger"),
                    )
                    return
            if not data:
                self.app.root.after(
                    0, lambda: self.app.log("⬇ Ảnh: không có dữ liệu để lưu", "danger"),
                )
                return

            ext = ".png"
            if "jpeg" in ctype or "jpg" in ctype:
                ext = ".jpg"
            elif "webp" in ctype:
                ext = ".webp"
            elif "gif" in ctype:
                ext = ".gif"
            elif u and u.lower().endswith((".jpg", ".jpeg")):
                ext = ".jpg"

            # Chỉ lưu Desktop
            path = os.path.join(desktop, f"{base}{ext}")
            try:
                with open(path, "wb") as f:
                    f.write(data)
                self.app.root.after(
                    0,
                    lambda p=path: self.app.log(
                        f"⬇ Đã lưu Desktop: {os.path.basename(p)}", "success",
                    ),
                )
            except OSError as exc:
                self.app.root.after(
                    0, lambda e=exc: self.app.log(f"⬇ Ảnh: không ghi Desktop — {e}", "danger"),
                )

        threading.Thread(target=worker, daemon=True).start()

    def _take_screenshot(self) -> None:
        if not self._auto_cls or not self._workflow_host:
            return
        folder = self.ensure_folder()
        if not folder:
            return
        oid = self._current.get("order_id", "shot")
        name = oid.replace("/", "-").replace("\\", "-")[:50]

        try:
            wf = self._auto_cls(self._workflow_host, {})
            if not wf.activate_embroidery_window():
                self.app.log("Không tìm thấy cửa sổ Wilcom", "danger")
                return
            shot = wf.capture_window_screenshot()
            filepath = os.path.join(folder, f"{name}.png")
            shot.save(filepath)
            self.app.log(f"📸 Đã chụp: {os.path.basename(filepath)}", "success")
        except Exception as exc:
            try:
                path = self._logic.take_screenshot(name, folder)
                if path:
                    self.app.log(f"📸 Chụp màn hình: {os.path.basename(path)}", "success")
                    return
            except Exception:
                pass
            self.app.log(f"Chụp ảnh lỗi: {exc}", "danger")

    def _load_image_async(self, url: str, oid: str) -> None:
        def worker():
            img_bytes = None
            if url:
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "ACC2019/2.4"})
                    with urllib.request.urlopen(req, timeout=20) as resp:
                        img_bytes = resp.read()
                except Exception:
                    img_bytes = None

            if not img_bytes and self._current_folder:
                for name in (f"{oid}.png", "1.png"):
                    local = os.path.join(self._current_folder, name)
                    if os.path.isfile(local):
                        try:
                            with open(local, "rb") as f:
                                img_bytes = f.read()
                            break
                        except Exception:
                            pass

            if img_bytes:
                self.app.root.after(0, lambda b=img_bytes, o=oid: self._set_thumbnail(b, o))
            else:
                self.app.root.after(0, lambda: (
                    self.lbl_image.config(image="", text="Không ảnh"),
                    self.lbl_image.place(relx=0.5, rely=0.5, anchor="center"),
                ))

        threading.Thread(target=worker, daemon=True).start()

    def _set_thumbnail(self, img_bytes: bytes, oid: str = "") -> None:
        self._img_bytes = img_bytes
        if self._current and (
            not oid or self._current.get("order_id") == oid
            or str(self._current.get("order_id", "")).startswith(str(oid)[:8])
        ):
            self._current["_img_bytes"] = img_bytes
        # cache vào history
        for h in self._history:
            if oid and h.get("order_id") == oid:
                h["_img_bytes"] = img_bytes
        try:
            from PIL import Image, ImageTk

            img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            sz = int(getattr(self, "_thumb_px", THUMB_SIZE) or THUMB_SIZE)
            img.thumbnail((sz, sz), Image.Resampling.LANCZOS)
            self._photo = ImageTk.PhotoImage(img)
            self.lbl_image.config(image=self._photo, text="")
            self.lbl_image.place(relx=0.5, rely=0.5, anchor="center")
        except Exception:
            self.lbl_image.config(image="", text="Lỗi ảnh")
            self.lbl_image.place(relx=0.5, rely=0.5, anchor="center")

    def _zoom_current_image(self) -> None:
        """Click ảnh — xem phóng to (không viền/nền, lăn zoom, kéo pan, Esc tắt)."""
        if self._img_bytes:
            self._lightbox.show_bytes(
                self._img_bytes,
                title=(self._current or {}).get("order_id", "Ảnh"),
            )
            return
        folder = self._current_folder or self.ensure_folder()
        paths = collect_images_in_folder(folder) if folder else []
        if paths:
            self._lightbox.show_paths(paths, 0)
            return
        self.app.log("Không có ảnh để phóng to", "danger")

    def _review_folder_images(self) -> None:
        """👁 Review ảnh trong folder đơn đang làm / hôm nay."""
        folder = self._current_folder
        if not folder or not os.path.isdir(folder):
            folder = self.ensure_folder()
        paths = collect_images_in_folder(folder) if folder else []
        if not paths:
            # fallback today folder
            today = get_today_orders_folder()
            if today and os.path.isdir(today):
                # scan subfolders lightly
                for root, _dirs, files in os.walk(today):
                    for name in files:
                        if os.path.splitext(name)[1].lower() in (
                            ".png", ".jpg", ".jpeg", ".bmp", ".webp",
                        ):
                            paths.append(os.path.join(root, name))
                    if len(paths) > 40:
                        break
        if not paths:
            self.app.log("👁 Folder không có ảnh để review", "danger")
            return
        self._lightbox.show_paths(paths, 0)
        self.app.log(f"👁 Review {len(paths)} ảnh · {os.path.basename(folder or '')}", "accent")

    def _reset_produce_data(self) -> None:
        """🗑 Reset dữ liệu tab sản xuất (history, pin A/B, ảnh, status)."""
        from tkinter import messagebox
        if not messagebox.askyesno(
            "Reset sản xuất",
            "Xóa lịch sử đơn trên bảng, pin A/B, ảnh hiện tại?\n"
            "(Không xóa file trên ổ đĩa / folder đơn)",
            parent=self.app.root,
        ):
            return
        try:
            for iid in self.tree.get_children():
                self.tree.delete(iid)
        except Exception:
            pass
        self._history.clear()
        self._current = {}
        self._current_folder = None
        self._img_bytes = None
        self._photo = None
        self._pin_a = self._pin_b = None
        self._pin_a_bytes = self._pin_b_bytes = None
        self._pinned.clear()
        try:
            self._save_pins()
        except Exception:
            pass
        for key, lab in self._copy_labels.items():
            lab.config(text="—")
        try:
            self.lbl_image.config(image="", text="Ảnh")
            self.lbl_image_b.config(image="", text="B")
            self._stem_var.set("")
            self._pin_status.set("")
            self._files_title.set("Files —")
            self._files_sum.set("")
            self._overall_dot.config(fg=COLOR_IDLE)
            self.btn_dxf.config(text="DXF ✗", fg=COLOR_MISS, bg="#2a1010")
        except Exception:
            pass
        for code, var in self._chk_vars.items():
            var.set(False)
            try:
                self._chk_widgets[code].pack_forget()
            except Exception:
                pass
        self.app.log("🗑 Đã reset dữ liệu tab Sản xuất", "accent")

    def _refresh_today_stat(self) -> None:
        if hasattr(self.app, "refresh_daily_stats"):
            self.app.refresh_daily_stats()

    def destroy(self) -> None:
        self._teardown_hotkeys()
        try:
            self._lightbox.close()
        except Exception:
            pass
        if self._poll_job:
            try:
                self.app.root.after_cancel(self._poll_job)
            except Exception:
                pass
            self._poll_job = None
        if self._server:
            self._server.stop()