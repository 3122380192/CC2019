"""Tab Đóng gói — UI gọn + popup Cài đặt cấu hình (có ví dụ từng chức năng)."""

from __future__ import annotations

import os
import subprocess
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, simpledialog, ttk

from modules.pack_engine import (
    ACTION_TYPES,
    DEFAULT_EXTENSIONS,
    PS_EXTENSIONS,
    cleanup_folder,
    collect_files,
    create_profile,
    delete_profile,
    duplicate_profile,
    get_active_profile,
    get_pack_extensions,
    list_profiles,
    load_config,
    preview_output_path,
    rename_profile,
    resolve_output_parent,
    run_packaging,
    save_profile,
    set_active_profile,
    today_str,
    _desktop_base,
    normalize_action,
)

BG, CARD, TEXT, MUTED = "#0c0c14", "#141424", "#e8e8f0", "#82829c"
ACCENT, SUCCESS, GOLD, DANGER = "#00d2ff", "#00e676", "#fbbf24", "#ff6b8a"
PACK = "#34d399"

PS_EXE_CANDIDATES = (
    r"C:\Program Files\Adobe\Adobe Photoshop CC 2019\Photoshop.exe",
    r"C:\Program Files\Adobe\Adobe Photoshop 2020\Photoshop.exe",
    r"C:\Program Files\Adobe\Adobe Photoshop 2021\Photoshop.exe",
    r"C:\Program Files\Adobe\Adobe Photoshop 2022\Photoshop.exe",
    r"C:\Program Files\Adobe\Adobe Photoshop 2023\Photoshop.exe",
    r"C:\Program Files\Adobe\Adobe Photoshop 2024\Photoshop.exe",
    r"C:\Program Files\Adobe\Adobe Photoshop 2025\Photoshop.exe",
)
BATCH_IMG_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".psd", ".bmp", ".webp"}

# Ví dụ hiển thị cạnh từng chức năng
ACTION_EXAMPLES = {
    "pack_all_zip": "Nén MỌI file đã xử lý thành 1 ZIP.",
    "copy_all_folder": "Sao chép file đã xử lý vào folder (không nén).",
    "pack_left_match": "Nén theo nhóm N ký tự đầu (trái→phải) của tên file.",
    "pack_folder_name": "Nén tất cả → 1 ZIP mang tên folder Nguồn.",
    "pack_same_name": "Gom file trùng tên (stem) vào cùng 1 ZIP.",
    "pack_list_zip": "Mỗi dòng list tên = 1 ZIP.",
}

# Radio hành động trên form cấu hình (thứ tự như màn hình mẫu)
ACTION_RADIOS = (
    ("pack_all_zip", "Nén các file đã xử lý"),
    ("copy_all_folder", "Sao chép các file đã xử lý"),
    ("pack_left_match", "Nén theo nhóm ký tự trùng khớp"),
    ("pack_folder_name", "Nén theo danh sách tên từ thư mục Nguồn"),
)

def find_photoshop() -> str | None:
    for p in PS_EXE_CANDIDATES:
        if os.path.isfile(p):
            return p
    import shutil
    w = shutil.which("Photoshop.exe")
    return w if w and os.path.isfile(w) else None


def _posix(path: str) -> str:
    return path.replace("\\", "/")


class PackPanel:
    def __init__(self, parent: tk.Misc, app) -> None:
        self.parent = parent
        self.app = app
        self.base_dir = getattr(app, "base_dir", ".")
        self._busy = False
        self._selected: list[str] = []
        self._settings_win: tk.Toplevel | None = None
        self._list_paths: list[str] = []

        self.cfg = load_config(self.base_dir)
        self.profile_name, self.profile = get_active_profile(self.base_dir)

        # State vars (dùng chung main + settings)
        self.in_var = tk.StringVar()
        self.out_var = tk.StringVar()
        self.note_var = tk.StringVar()
        self.product_name_var = tk.StringVar()
        self.action_var = tk.StringVar(value="pack_left_match")  # id, không phải label
        self.prefix_var = tk.IntVar(value=17)
        self.kw_var = tk.StringVar()
        self.zip_name_var = tk.StringVar()
        self.custom_ext_var = tk.StringVar()
        self.del_after_var = tk.BooleanVar(value=True)
        self.del_src_var = tk.BooleanVar(value=True)
        self.auto_backup_var = tk.BooleanVar(value=True)
        self.auto_pack_var = tk.BooleanVar(value=False)
        self.daily_var = tk.BooleanVar(value=True)
        self.product_var = tk.StringVar(value="Print")
        self.open_after_var = tk.BooleanVar(value=True)
        self.ps_script_var = tk.StringVar()
        self.ps_action_set_var = tk.StringVar()
        self.ps_action_name_var = tk.StringVar()
        self.detect_kw_var = tk.StringVar()
        self.detect_col_var = tk.StringVar(value="B")
        self.pack_mode_var = tk.StringVar(value="all")  # all | selected
        # đuôi đóng gói
        self.ext_vars: dict[str, tk.BooleanVar] = {
            e: tk.BooleanVar(value=e in ("jpg", "png")) for e in ("jpg", "png", "tif")
        }
        # đuôi Photoshop xử lý
        self.ps_ext_vars: dict[str, tk.BooleanVar] = {
            e: tk.BooleanVar(value=e == "png") for e in ("jpg", "png", "tif")
        }
        self._name_list_text = ""

        self.frame = tk.Frame(parent, bg=BG)
        self.frame.pack(fill=tk.BOTH, expand=True)
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(4, weight=1)

        self._build_main()
        self._load_profile_ui()
        self._setup_drop()
        self._refresh_file_list()
        self._update_summary()
        self._refresh_profile_combo(self.profile_name)
        self._schedule_path_tick()

    # ═══════════════════════════════════════════════════════════════════════
    # MAIN UI (gọn)
    # ═══════════════════════════════════════════════════════════════════════

    def _build_main(self) -> None:
        # Header
        top = tk.Frame(self.frame, bg=CARD)
        top.grid(row=0, column=0, sticky="ew")
        tk.Label(
            top, text="📦 ĐÓNG GÓI", font=("Segoe UI", 9, "bold"),
            fg=PACK, bg=CARD,
        ).pack(side=tk.LEFT, padx=6, pady=4)
        self.status_var = tk.StringVar(value="Sẵn sàng")
        tk.Label(
            top, textvariable=self.status_var, font=("Segoe UI", 7),
            fg=MUTED, bg=CARD,
        ).pack(side=tk.LEFT, padx=4)

        tk.Button(
            top, text="⚙  Cấu hình SP", font=("Segoe UI", 8, "bold"),
            bg=PACK, fg="#000", bd=0, padx=10, pady=3, cursor="hand2",
            command=self.open_settings,
        ).pack(side=tk.RIGHT, padx=6, pady=3)
        tk.Button(
            top, text="🖼 Sắp xếp ảnh", font=("Segoe UI", 7, "bold"),
            bg=BG, fg=GOLD, bd=0, padx=8, pady=3, cursor="hand2",
            command=self._sort_images_stub,
        ).pack(side=tk.RIGHT, padx=2)
        tk.Button(
            top, text="?", font=("Segoe UI", 8, "bold"), bg=BG, fg=ACCENT,
            bd=0, padx=8, command=self._show_help_examples, cursor="hand2",
        ).pack(side=tk.RIGHT, padx=2)
        tk.Button(
            top, text="📂 Out", font=("Segoe UI", 7), bg=BG, fg=MUTED, bd=0, padx=4,
            command=self._open_output, cursor="hand2",
        ).pack(side=tk.RIGHT, padx=2)
        tk.Button(
            top, text="📂 In", font=("Segoe UI", 7), bg=BG, fg=MUTED, bd=0, padx=4,
            command=self._open_input, cursor="hand2",
        ).pack(side=tk.RIGHT, padx=2)

        # Profile combobox
        cfg = tk.Frame(self.frame, bg=CARD)
        cfg.grid(row=1, column=0, sticky="ew", padx=4, pady=(4, 2))
        tk.Label(
            cfg, text="Cấu hình đã lưu", font=("Segoe UI", 8, "bold"),
            fg=PACK, bg=CARD,
        ).pack(side=tk.LEFT, padx=(6, 4), pady=4)
        self.profile_var = tk.StringVar(value=self.profile_name)
        self.profile_combo = ttk.Combobox(
            cfg, textvariable=self.profile_var, state="readonly",
            values=list_profiles(self.base_dir), font=("Segoe UI", 9), width=24,
        )
        self.profile_combo.pack(side=tk.LEFT, padx=2)
        self.profile_combo.bind("<<ComboboxSelected>>", self._on_profile_pick)
        self.profile_combo.bind(
            "<Button-1>", lambda _e: self._refresh_profile_combo(self.profile_name),
        )
        self.profile_count_var = tk.StringVar(value="")
        tk.Label(
            cfg, textvariable=self.profile_count_var, font=("Segoe UI", 7),
            fg=MUTED, bg=CARD,
        ).pack(side=tk.LEFT, padx=4)
        tk.Label(
            cfg, text="VD: «Print DXF» · «Gói ca sáng» — bấm ⚙ để tạo/sửa",
            font=("Segoe UI", 6), fg=MUTED, bg=CARD,
        ).pack(side=tk.LEFT, padx=6)

        # Summary of current settings
        sum_fr = tk.Frame(self.frame, bg=BG)
        sum_fr.grid(row=2, column=0, sticky="ew", padx=4, pady=2)
        sum_fr.columnconfigure(0, weight=1)
        self.summary_var = tk.StringVar(value="")
        tk.Label(
            sum_fr, textvariable=self.summary_var, font=("Segoe UI", 7),
            fg=TEXT, bg=CARD, anchor="w", justify="left", padx=8, pady=6,
            wraplength=480,
        ).pack(fill=tk.X)
        self.out_preview_var = tk.StringVar(value="")
        tk.Label(
            sum_fr, textvariable=self.out_preview_var, font=("Consolas", 7),
            fg=ACCENT, bg=BG, anchor="w",
        ).pack(fill=tk.X, pady=(2, 0))
        self.example_var = tk.StringVar(value="")
        tk.Label(
            sum_fr, textvariable=self.example_var, font=("Segoe UI", 6),
            fg=GOLD, bg=BG, anchor="w", justify="left", wraplength=480,
        ).pack(fill=tk.X, pady=(1, 0))

        # Source + tên ZIP tùy ý
        src = tk.Frame(self.frame, bg=BG)
        src.grid(row=3, column=0, sticky="ew", padx=4, pady=2)
        src.columnconfigure(1, weight=1)
        tk.Label(src, text="Nguồn", font=("Segoe UI", 7), fg=MUTED, bg=BG, width=6).grid(
            row=0, column=0, sticky="w",
        )
        tk.Entry(
            src, textvariable=self.in_var, font=("Segoe UI", 8),
            bg=CARD, fg=TEXT, insertbackground=TEXT, bd=0,
        ).grid(row=0, column=1, sticky="ew", ipady=3, padx=2)
        tk.Button(
            src, text="…", font=("Segoe UI", 8, "bold"), bg=CARD, fg=ACCENT, bd=0, padx=8,
            command=self._browse_input, cursor="hand2",
        ).grid(row=0, column=2)
        tk.Label(
            src, text="Tên ZIP", font=("Segoe UI", 7, "bold"), fg=GOLD, bg=BG, width=6,
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))
        zip_ent = tk.Entry(
            src, textvariable=self.zip_name_var, font=("Segoe UI", 9),
            bg=CARD, fg=GOLD, insertbackground=TEXT, bd=0,
        )
        zip_ent.grid(row=1, column=1, sticky="ew", ipady=4, padx=2, pady=(3, 0))
        tk.Label(
            src, text=".zip", font=("Segoe UI", 8, "bold"), fg=MUTED, bg=BG,
        ).grid(row=1, column=2, sticky="w", pady=(3, 0))
        tk.Label(
            src, text="VD: DonHang_1207 · WhiteCoined · để trống = tự đặt theo kiểu gói",
            font=("Segoe UI", 6), fg=MUTED, bg=BG,
        ).grid(row=2, column=1, sticky="w", padx=2)

        # File list + actions
        body = tk.Frame(self.frame, bg=BG)
        body.grid(row=4, column=0, sticky="nsew", padx=4, pady=2)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        list_fr = tk.Frame(body, bg=BG)
        list_fr.grid(row=0, column=0, sticky="nsew")
        list_fr.columnconfigure(0, weight=1)
        list_fr.rowconfigure(0, weight=1)
        self.listbox = tk.Listbox(
            list_fr, bg="#07070a", fg=TEXT, font=("Consolas", 8),
            selectmode=tk.EXTENDED, selectbackground="#1a3a2a",
            selectforeground=SUCCESS, activestyle="none", bd=0, highlightthickness=0,
            exportselection=False,
        )
        self.listbox.grid(row=0, column=0, sticky="nsew")
        sb = tk.Scrollbar(list_fr, command=self.listbox.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.listbox.config(yscrollcommand=sb.set)

        act = tk.Frame(body, bg=CARD)
        act.grid(row=1, column=0, sticky="ew", pady=3)
        for text, cmd, fg in (
            ("↻ Quét", self._refresh_file_list, MUTED),
            ("✓ Chọn hết", self._select_all, ACCENT),
            ("Chỉ chọn", self._use_selection_only, GOLD),
            ("Bỏ chọn", self._clear_selection, MUTED),
            ("🖼 Sắp xếp ảnh", self._sort_images_stub, GOLD),
            ("📦 ĐÓNG GÓI", self._run_pack, SUCCESS),
            ("🗑 Dọn nguồn", self._cleanup_source, DANGER),
        ):
            tk.Button(
                act, text=text, font=("Segoe UI", 7, "bold"), bg=BG, fg=fg,
                bd=0, padx=6, pady=4, command=cmd, cursor="hand2",
            ).pack(side=tk.LEFT, padx=2, pady=2)

        # Mini PS bar
        ps = tk.Frame(body, bg=BG)
        ps.grid(row=2, column=0, sticky="ew", pady=(2, 0))
        tk.Label(ps, text="🎨 PS", font=("Segoe UI", 7, "bold"), fg=ACCENT, bg=BG).pack(
            side=tk.LEFT, padx=(0, 4),
        )
        scripts = self._list_scripts()
        self.ps_combo = ttk.Combobox(
            ps, textvariable=self.ps_script_var, values=scripts,
            font=("Segoe UI", 7), width=18, state="readonly" if scripts else "normal",
        )
        self.ps_combo.pack(side=tk.LEFT, padx=1)
        if scripts:
            self.ps_script_var.set(scripts[0])
        tk.Button(
            ps, text="▶ Script", font=("Segoe UI", 7, "bold"), bg=CARD, fg=SUCCESS,
            bd=0, padx=6, command=self._run_script_quick, cursor="hand2",
        ).pack(side=tk.LEFT, padx=2)
        tk.Button(
            ps, text="⚡ Batch", font=("Segoe UI", 7, "bold"), bg=CARD, fg=GOLD,
            bd=0, padx=6, command=self._run_ps_batch, cursor="hand2",
        ).pack(side=tk.LEFT, padx=2)
        tk.Label(
            ps, text="VD: chọn XuatFileCat.jsx → Batch folder nguồn",
            font=("Segoe UI", 6), fg=MUTED, bg=BG,
        ).pack(side=tk.LEFT, padx=6)

    # ═══════════════════════════════════════════════════════════════════════
    # SETTINGS DIALOG
    # ═══════════════════════════════════════════════════════════════════════


    def open_settings(self) -> None:
        """Form «Quản lý cấu hình sản phẩm» (theo mẫu UI)."""
        from modules.pack_settings_dialog import PackProductConfigDialog
        PackProductConfigDialog(self).show()

    def _sort_images_stub(self) -> None:
        """Mở tab Tiện ích — sắp xếp ảnh đã có ở đó."""
        app = self.app
        folder = (self.in_var.get() or "").strip()
        tools = getattr(app, "tools_panel", None)
        if tools is not None and folder:
            try:
                tools.folder_var.set(folder)
            except Exception:
                pass
        if hasattr(app, "show_tab"):
            try:
                app.show_tab("tools")
            except Exception:
                pass
        messagebox.showinfo(
            "Sắp xếp ảnh",
            "Đã mở tab «Tiện ích».\n\n"
            "Dùng mục «4 · Sắp xếp ảnh»:\n"
            "• Tách vào subfolder theo N ký tự đầu\n"
            "• Gom ảnh → _images\\",
            parent=self.frame,
        )
        if hasattr(app, "log"):
            app.log("🖼 Mở tab Tiện ích → Sắp xếp ảnh", "accent")


    def _settings_path_row(self, parent, label, var, browse_cmd, hint: str = "") -> None:
        row = tk.Frame(parent, bg=BG)
        row.pack(fill=tk.X, padx=10, pady=2)
        row.columnconfigure(1, weight=1)
        tk.Label(row, text=label, font=("Segoe UI", 8), fg=MUTED, bg=BG, width=8, anchor="w").grid(
            row=0, column=0, sticky="w",
        )
        tk.Entry(
            row, textvariable=var, font=("Segoe UI", 8),
            bg=CARD, fg=TEXT, insertbackground=TEXT, bd=0,
        ).grid(row=0, column=1, sticky="ew", ipady=2, padx=2)
        tk.Button(
            row, text="…", font=("Segoe UI", 8, "bold"), bg=CARD, fg=ACCENT, bd=0, padx=8,
            command=browse_cmd, cursor="hand2",
        ).grid(row=0, column=2)
        if hint:
            tk.Label(row, text=hint, font=("Segoe UI", 6), fg=MUTED, bg=BG).grid(
                row=0, column=3, sticky="w", padx=2,
            )

    def _settings_live_preview(self) -> None:
        try:
            if hasattr(self, "settings_preview_var"):
                self.settings_preview_var.set(f"→ {preview_output_path(self._profile_from_ui())}")
            self._update_action_example()
            self._update_summary()
        except Exception:
            pass

    def _apply_settings(self, win: tk.Toplevel | None = None) -> None:
        try:
            if hasattr(self, "name_list_txt") and self.name_list_txt.winfo_exists():
                self._name_list_text = self.name_list_txt.get("1.0", tk.END).strip()
        except Exception:
            pass
        self._save_profile()
        self._update_summary()
        self._refresh_file_list()
        if win:
            try:
                win.destroy()
            except tk.TclError:
                pass
            self._settings_win = None
        if hasattr(self.app, "log"):
            self.app.log(f"📦 Đã áp dụng cấu hình «{self.profile_name}»", "success")

    def _show_help_examples(self) -> None:
        """Popup tất cả ví dụ chức năng."""
        text = (
            "═══ VÍ DỤ CHỨC NĂNG ĐÓNG GÓI ═══\n\n"
            "📁 XUẤT FILE\n"
            f"  Desktop\\{today_str()}\\Print\\ten.zip\n"
            f"  VD: {_desktop_base()}\\{today_str()}\\Print\\\n\n"
            "⚙ CẤU HÌNH\n"
            "  Tạo nhiều profile: Print DXF, Gói ca sáng…\n"
            "  Chọn combo → dùng lại nguồn/kiểu/đuôi đã lưu.\n\n"
        )
        for aid, label in ACTION_TYPES.items():
            ex = ACTION_EXAMPLES.get(aid, "")
            text += f"▸ {label}\n{ex}\n\n"
        text += (
            "✏️ TÊN ZIP\n"
            "  Ô «Tên ZIP» = DonHang_01 → DonHang_01.zip\n\n"
            "📋 LIST TÊN\n"
            "  SP001\\nSP002 → 2 file ZIP riêng\n\n"
            "🗑 DỌN\n"
            "  Xóa file sau gói / dọn folder nguồn (cẩn thận)\n\n"
            "🎨 PHOTOSHOP\n"
            "  ▶ Script = chạy 1 lần · ⚡ Batch = từng ảnh trong Nguồn\n"
        )
        messagebox.showinfo("Ví dụ đóng gói", text, parent=self.frame)

    # ═══════════════════════════════════════════════════════════════════════
    # Summary / examples on main
    # ═══════════════════════════════════════════════════════════════════════

    def _action_id(self) -> str:
        raw = (self.action_var.get() or "").strip()
        if raw in ACTION_TYPES:
            return normalize_action(raw)
        for k, v in ACTION_TYPES.items():
            if v == raw:
                return k
        return normalize_action(raw) or "pack_all_zip"

    def _update_action_example(self) -> None:
        ex = ACTION_EXAMPLES.get(self._action_id(), "")
        if hasattr(self, "example_var"):
            self.example_var.set(ex.replace("\n", " · "))
        if hasattr(self, "settings_example_var"):
            self.settings_example_var.set(ex)

    def _update_summary(self) -> None:
        try:
            p = self._profile_from_ui()
            path = preview_output_path(p)
            if hasattr(self, "out_preview_var"):
                self.out_preview_var.set(f"→ Xuất: {path}")
            if hasattr(self, "settings_preview_var"):
                self.settings_preview_var.set(f"→ {path}")
            action = ACTION_TYPES.get(normalize_action(p.get("action_type", "")), "?")
            exts = ",".join(get_pack_extensions(p)[:6])
            note = (p.get("note") or "").strip()
            pname = (p.get("product_name") or "").strip()
            lines = [
                f"Cấu hình: «{self.profile_name}»"
                + (f" · SP: {pname}" if pname else "")
                + (f" — {note}" if note and note != pname else ""),
                f"Kiểu: {action}  ·  N={p.get('match_prefix_length', 17)}  ·  đuôi: {exts}",
            ]
            if p.get("zip_name"):
                lines.append(f"Tên ZIP: {p['zip_name']}.zip")
            if p.get("name_list"):
                n = len([x for x in p["name_list"].splitlines() if x.strip()])
                lines.append(f"List tên: {n} mục")
            flags = []
            if p.get("use_daily_folder", True):
                flags.append("folder ngày")
            if p.get("delete_after_packaging"):
                flags.append("xóa sau gói")
            if p.get("delete_source_folder_after_packaging"):
                flags.append("dọn nguồn")
            if p.get("auto_backup_before_delete", True) and (
                p.get("delete_after_packaging") or p.get("delete_source_folder_after_packaging")
            ):
                flags.append("backup trước xóa")
            if flags:
                lines.append(" · ".join(flags))
            if hasattr(self, "summary_var"):
                self.summary_var.set("\n".join(lines))
            self._update_action_example()
        except Exception:
            pass

    def _on_action_change(self) -> None:
        self._update_action_example()
        self._update_summary()
        self._refresh_file_list()

    # ═══════════════════════════════════════════════════════════════════════
    # Profile IO
    # ═══════════════════════════════════════════════════════════════════════

    def _refresh_profile_combo(self, select: str | None = None) -> None:
        names = list_profiles(self.base_dir)
        try:
            self.profile_combo["values"] = names
        except Exception:
            return
        name = select or self.profile_name
        if name not in names and names:
            name = names[0]
        self.profile_name = name
        self.profile_var.set(name)
        if hasattr(self, "profile_count_var"):
            self.profile_count_var.set(f"({len(names)} cấu hình)")

    def _schedule_path_tick(self) -> None:
        try:
            self._update_summary()
            self.frame.after(60_000, self._schedule_path_tick)
        except Exception:
            pass

    def _name_list_from_ui(self) -> str:
        try:
            if hasattr(self, "name_list_txt") and self.name_list_txt.winfo_exists():
                return self.name_list_txt.get("1.0", tk.END).strip()
        except Exception:
            pass
        return self._name_list_text or ""

    def _load_profile_ui(self) -> None:
        p = self.profile
        self.in_var.set(p.get("input_folder") or "")
        self.out_var.set(p.get("output_folder") or "")
        action = normalize_action(p.get("action_type", "pack_left_match"))
        if action not in ACTION_TYPES:
            action = "pack_left_match"
        self.action_var.set(action)
        self.prefix_var.set(int(p.get("match_prefix_length") or 17))
        self.kw_var.set(p.get("match_keyword") or "")
        self.custom_ext_var.set(p.get("pack_custom_extensions") or "")
        self.del_after_var.set(bool(p.get("delete_after_packaging", True)))
        self.del_src_var.set(bool(p.get("delete_source_folder_after_packaging", False)))
        self.auto_backup_var.set(bool(p.get("auto_backup_before_delete", True)))
        self.auto_pack_var.set(bool(p.get("auto_pack_after_action", False)))
        self.daily_var.set(bool(p.get("use_daily_folder", True)))
        self.product_var.set(p.get("product_subfolder") or "Print")
        self.product_name_var.set(p.get("product_name") or "")
        self.open_after_var.set(bool(p.get("open_after_pack", True)))
        self.note_var.set(p.get("note") or "")
        self.zip_name_var.set(p.get("zip_name") or "")
        self.ps_action_set_var.set(p.get("ps_action_set") or "")
        self.ps_action_name_var.set(p.get("ps_action_name") or "")
        self.detect_kw_var.set(p.get("detect_keywords") or "")
        self.detect_col_var.set(p.get("detect_column") or "B")
        self.pack_mode_var.set(p.get("pack_file_mode") or "all")
        self._name_list_text = p.get("name_list") or ""
        try:
            if hasattr(self, "name_list_txt") and self.name_list_txt.winfo_exists():
                self.name_list_txt.delete("1.0", tk.END)
                self.name_list_txt.insert("1.0", self._name_list_text)
        except Exception:
            pass
        # pack extensions (jpg/png/tif UI)
        saved = set(e.lower().lstrip(".") for e in (p.get("pack_extensions") or []))
        if not saved:
            saved = {"jpg", "png"}
        for e, v in self.ext_vars.items():
            v.set(e in saved or (e == "jpg" and "jpeg" in saved) or (e == "tif" and "tiff" in saved))
        # ps extensions
        ps_saved = set(e.lower().lstrip(".") for e in (p.get("ps_extensions") or []))
        if not ps_saved:
            ps_saved = {"png"}
        for e, v in self.ps_ext_vars.items():
            v.set(e in ps_saved or (e == "jpg" and "jpeg" in ps_saved) or (e == "tif" and "tiff" in ps_saved))
        self._selected = [x for x in (p.get("selected_files") or []) if os.path.isfile(x)]
        if self.pack_mode_var.get() == "selected" and not self._selected:
            self.pack_mode_var.set("all")
        ps_s = (p.get("ps_script") or "").strip()
        if ps_s:
            scripts = list(self.ps_combo["values"]) if getattr(self, "ps_combo", None) else []
            if ps_s not in scripts and scripts is not None:
                try:
                    self.ps_combo["values"] = list(scripts) + [ps_s]
                except Exception:
                    pass
            self.ps_script_var.set(ps_s)
        self.profile_var.set(self.profile_name)
        self._update_summary()

    def _profile_from_ui(self) -> dict:
        pack_exts = [e for e, v in self.ext_vars.items() if v.get()]
        # alias jpeg/tiff nếu user tick jpg/tif
        if "jpg" in pack_exts and "jpeg" not in pack_exts:
            pack_exts.append("jpeg")
        if "tif" in pack_exts and "tiff" not in pack_exts:
            pack_exts.append("tiff")
        ps_exts = [e for e, v in self.ps_ext_vars.items() if v.get()]
        selected = list(self._selected) if self.pack_mode_var.get() == "selected" else []
        pname = (self.product_name_var.get() or "").strip()
        return {
            "input_folder": self.in_var.get().strip(),
            "output_folder": self.out_var.get().strip(),
            "action_type": self._action_id(),
            "pack_extensions": pack_exts or ["jpg", "png"],
            "ps_extensions": ps_exts or ["png"],
            "pack_custom_extensions": self.custom_ext_var.get().strip(),
            "selected_files": selected,
            "pack_file_mode": self.pack_mode_var.get() or "all",
            "match_prefix_length": int(self.prefix_var.get() or 17),
            "match_keyword": self.kw_var.get().strip(),
            "zip_name": self.zip_name_var.get().strip(),
            "name_list": self._name_list_from_ui(),
            "delete_after_packaging": bool(self.del_after_var.get()),
            "delete_source_folder_after_packaging": bool(self.del_src_var.get()),
            "auto_backup_before_delete": bool(self.auto_backup_var.get()),
            "auto_pack_after_action": bool(self.auto_pack_var.get()),
            "use_daily_folder": bool(self.daily_var.get()),
            "product_subfolder": self.product_var.get().strip() or "Print",
            "product_name": pname,
            "open_after_pack": bool(self.open_after_var.get()),
            "note": self.note_var.get().strip() or pname,
            "ps_script": self.ps_script_var.get().strip(),
            "ps_action_set": self.ps_action_set_var.get().strip(),
            "ps_action_name": self.ps_action_name_var.get().strip(),
            "detect_keywords": self.detect_kw_var.get().strip(),
            "detect_column": self.detect_col_var.get().strip() or "B",
        }

    def _save_profile(self) -> None:
        profile = self._profile_from_ui()
        self.profile = profile
        name = self.profile_name or self.profile_var.get() or "Mặc định"
        ok, msg = save_profile(self.base_dir, name, profile)
        self.profile_name = name
        self._refresh_profile_combo(name)
        self.status_var.set(msg if ok else f"Lỗi: {msg}")
        self._update_summary()
        if hasattr(self.app, "log"):
            self.app.log(f"📦 {msg}", "accent" if ok else "danger")

    def _ask_name(self, title: str, initial: str = "") -> str | None:
        name = simpledialog.askstring(
            title, "Tên cấu hình đóng gói:\nVD: Print DXF · Gói ca sáng · KhachA",
            initialvalue=initial, parent=self.frame,
        )
        if name is None:
            return None
        name = name.strip()
        if not name:
            messagebox.showwarning("Cấu hình", "Tên không được trống", parent=self.frame)
            return None
        return name

    def _profile_new(self) -> None:
        name = self._ask_name("Cấu hình mới", f"Gói {datetime.now().strftime('%m%d_%H%M')}")
        if not name:
            return
        copy = messagebox.askyesno(
            "Cấu hình mới",
            f"Tạo «{name}»\n\nYes = copy từ «{self.profile_name}»\nNo = trống\n\n"
            "VD: copy «Print DXF» rồi đổi nguồn folder khác.",
            parent=self.frame,
        )
        from_p = self._profile_from_ui() if copy else None
        ok, msg = create_profile(self.base_dir, name, from_profile=from_p)
        if not ok:
            messagebox.showerror("Cấu hình", msg, parent=self.frame)
            return
        self.profile_name = name
        _, _, prof = set_active_profile(self.base_dir, name)
        self.profile = prof
        self._refresh_profile_combo(name)
        self._load_profile_ui()
        self._refresh_file_list()
        self.status_var.set(msg)
        if hasattr(self.app, "log"):
            self.app.log(f"📦 {msg}", "success")

    def _profile_save_as(self) -> None:
        name = self._ask_name("Lưu thành…", f"{self.profile_name}_copy")
        if not name:
            return
        data = load_config(self.base_dir)
        if name in (data.get("profiles") or {}):
            if not messagebox.askyesno("Ghi đè?", f"«{name}» đã có — ghi đè?", parent=self.frame):
                return
        profile = self._profile_from_ui()
        ok, msg = save_profile(self.base_dir, name, profile)
        if not ok:
            messagebox.showerror("Cấu hình", msg, parent=self.frame)
            return
        self.profile_name = name
        self.profile = profile
        self._refresh_profile_combo(name)
        self.status_var.set(f"Đã lưu thành «{name}»")
        self._update_summary()

    def _profile_duplicate(self) -> None:
        src = self.profile_name
        name = self._ask_name("Nhân bản", f"{src}_2")
        if not name:
            return
        save_profile(self.base_dir, src, self._profile_from_ui())
        ok, msg = duplicate_profile(self.base_dir, src, name)
        if not ok:
            messagebox.showerror("Cấu hình", msg, parent=self.frame)
            return
        self.profile_name = name
        _, _, prof = set_active_profile(self.base_dir, name)
        self.profile = prof
        self._refresh_profile_combo(name)
        self._load_profile_ui()
        self._refresh_file_list()
        self.status_var.set(msg)

    def _profile_rename(self) -> None:
        old = self.profile_name
        name = self._ask_name("Đổi tên", old)
        if not name or name == old:
            return
        save_profile(self.base_dir, old, self._profile_from_ui())
        ok, msg = rename_profile(self.base_dir, old, name)
        if not ok:
            messagebox.showerror("Cấu hình", msg, parent=self.frame)
            return
        self.profile_name = name
        self._refresh_profile_combo(name)
        self.status_var.set(msg)
        self._update_summary()

    def _profile_delete(self) -> None:
        name = self.profile_name
        if not messagebox.askyesno(
            "Xóa cấu hình",
            f"Xóa «{name}»?\n(Không xóa file ZIP đã tạo)\nVD: xóa profile test cũ.",
            parent=self.frame,
        ):
            return
        ok, msg = delete_profile(self.base_dir, name)
        if not ok:
            messagebox.showerror("Cấu hình", msg, parent=self.frame)
            return
        self.profile_name, self.profile = get_active_profile(self.base_dir)
        self._refresh_profile_combo(self.profile_name)
        self._load_profile_ui()
        self._refresh_file_list()
        self.status_var.set(msg)

    def _on_profile_pick(self, _e=None) -> None:
        name = self.profile_var.get()
        if not name or name == self.profile_name:
            return
        try:
            save_profile(self.base_dir, self.profile_name, self._profile_from_ui())
        except Exception:
            pass
        ok, msg, prof = set_active_profile(self.base_dir, name)
        if not ok:
            messagebox.showerror("Cấu hình", msg, parent=self.frame)
            self.profile_var.set(self.profile_name)
            return
        self.profile_name = name
        self.profile = prof
        self._load_profile_ui()
        self._refresh_file_list()
        self.status_var.set(f"Đang dùng «{name}»")
        if hasattr(self.app, "log"):
            note = (prof.get("note") or "").strip()
            self.app.log(f"📦 Cấu hình: {name}" + (f" · {note}" if note else ""), "accent")

    # ═══════════════════════════════════════════════════════════════════════
    # Files / pack / PS
    # ═══════════════════════════════════════════════════════════════════════

    def _list_scripts(self) -> list[str]:
        scripts_dir = os.path.join(self.base_dir, "Photoshop_Imports", "Scripts")
        out = []
        if os.path.isdir(scripts_dir):
            for n in sorted(os.listdir(scripts_dir)):
                if n.lower().endswith((".jsx", ".js")):
                    out.append(n)
        return out

    def _script_path(self) -> str | None:
        name = self.ps_script_var.get().strip()
        if not name:
            return None
        if os.path.isfile(name):
            return name
        p = os.path.join(self.base_dir, "Photoshop_Imports", "Scripts", name)
        return p if os.path.isfile(p) else None

    def _browse_input(self) -> None:
        d = filedialog.askdirectory(title="Thư mục nguồn (VD: Desktop\\DonCanGoi)", parent=self.frame)
        if d:
            self.in_var.set(d)
            self._selected.clear()
            self._refresh_file_list()
            self._update_summary()

    def _browse_output(self) -> None:
        d = filedialog.askdirectory(
            title="Base xuất (trống=Desktop → ...\\YYYY-MM-DD\\Print)", parent=self.frame,
        )
        if d:
            self.out_var.set(d)
            self._update_summary()

    def _open_input(self) -> None:
        p = self.in_var.get().strip()
        if p and os.path.isdir(p):
            os.startfile(p)
        else:
            messagebox.showinfo(
                "Nguồn",
                "Chưa chọn folder nguồn.\nVD: C:\\Users\\Tx\\Desktop\\DonCanGoi",
                parent=self.frame,
            )

    def _open_output(self) -> None:
        try:
            path = resolve_output_parent(self._profile_from_ui())
            os.startfile(path)
            self.status_var.set(f"Mở: {path}")
        except Exception as exc:
            messagebox.showerror("Mở folder", str(exc), parent=self.frame)

    def _browse_script(self) -> None:
        path = filedialog.askopenfilename(
            title="Script Photoshop (VD: XuatFileCat.jsx)",
            filetypes=[("JSX/JS", "*.jsx;*.js"), ("All", "*.*")],
            parent=self.frame,
        )
        if path:
            self.ps_script_var.set(path)
            try:
                vals = list(self.ps_combo["values"]) if self.ps_combo["values"] else []
                if path not in vals:
                    self.ps_combo["values"] = vals + [path]
            except Exception:
                pass

    def _refresh_file_list(self) -> None:
        profile = self._profile_from_ui()
        if self._selected:
            files = [p for p in self._selected if os.path.isfile(p)]
        else:
            files = collect_files(profile, keyword=self.kw_var.get().strip())
        self.listbox.delete(0, tk.END)
        for p in files:
            self.listbox.insert(tk.END, os.path.basename(p))
        self._list_paths = files
        mode = "chọn tay" if self._selected else "theo folder"
        self.status_var.set(f"{len(files)} file · {mode}")

    def _select_all(self) -> None:
        self.listbox.select_set(0, tk.END)

    def _use_selection_only(self) -> None:
        idxs = self.listbox.curselection()
        if not idxs:
            messagebox.showinfo(
                "Chỉ chọn",
                "Chọn 1+ file trong list trước.\n"
                "VD: Ctrl+click SP001.png + SP001.dxf → Chỉ chọn → Đóng gói.",
                parent=self.frame,
            )
            return
        paths = getattr(self, "_list_paths", [])
        self._selected = [paths[i] for i in idxs if 0 <= i < len(paths)]
        self._refresh_file_list()
        self.status_var.set(f"Chỉ gói {len(self._selected)} file đã chọn")

    def _clear_selection(self) -> None:
        self._selected.clear()
        self._refresh_file_list()

    def _setup_drop(self) -> None:
        def on_drop(files):
            try:
                paths = []
                for f in files or []:
                    p = _decode_drop_path(f)
                    if p and (os.path.isfile(p) or os.path.isdir(p)):
                        paths.append(p)
                if paths:
                    self.frame.after(0, lambda ps=list(paths): self._handle_drop(ps))
            except Exception:
                pass

        try:
            import windnd
            windnd.hook_dropfiles(self.frame, func=on_drop, force_unicode=True)
            windnd.hook_dropfiles(self.listbox, func=on_drop, force_unicode=True)
        except Exception:
            pass

    def _handle_drop(self, paths: list[str]) -> None:
        dirs = [p for p in paths if os.path.isdir(p)]
        files = [p for p in paths if os.path.isfile(p)]
        if dirs:
            self.in_var.set(dirs[0])
            self._selected.clear()
            self._refresh_file_list()
            if hasattr(self.app, "log"):
                self.app.log(f"📦 Nguồn: {dirs[0]}", "accent")
        if files:
            for f in files:
                if f not in self._selected:
                    self._selected.append(f)
            if not self.in_var.get().strip() and files:
                self.in_var.set(os.path.dirname(files[0]))
            self._refresh_file_list()
        self._update_summary()

    def _run_pack(self) -> None:
        if self._busy:
            return
        profile = self._profile_from_ui()
        if not profile.get("input_folder") or not os.path.isdir(profile["input_folder"]):
            if not self._selected:
                messagebox.showwarning(
                    "Đóng gói",
                    "Chọn thư mục nguồn hoặc file.\n"
                    "VD: Nguồn = Desktop\\DonCanGoi  rồi bấm ↻ Quét.",
                    parent=self.frame,
                )
                return
            profile["input_folder"] = os.path.dirname(self._selected[0]) or "."
            os.makedirs(profile["input_folder"], exist_ok=True)

        sel = list(self._selected) if self._selected else None
        if sel is None and not getattr(self, "_list_paths", []):
            messagebox.showinfo(
                "Đóng gói",
                "Không có file khớp.\nVD: tick đuôi png,dxf · kiểu Trùng tên · ↻ Quét.",
                parent=self.frame,
            )
            return

        self._busy = True
        self.status_var.set("Đang đóng gói…")
        self._save_profile()
        out_prev = preview_output_path(profile)
        if hasattr(self.app, "log"):
            self.app.log(f"📦 Xuất → {out_prev}", "accent")

        def work():
            def log(msg):
                self.frame.after(0, lambda m=msg: self._log_ui(m))

            result = run_packaging(
                profile,
                keyword=self.kw_var.get().strip(),
                selected_files=sel,
                log=log,
            )
            self.frame.after(0, lambda: self._on_pack_done(result))

        threading.Thread(target=work, daemon=True).start()

    def _log_ui(self, msg: str) -> None:
        if hasattr(self.app, "log"):
            self.app.log(f"📦 {msg}", "accent")

    def _on_pack_done(self, result) -> None:
        self._busy = False
        self._update_summary()
        if result.ok:
            out_dir = ""
            if result.archives:
                out_dir = os.path.dirname(result.archives[0])
            elif result.copied_dirs:
                out_dir = result.copied_dirs[0]
            msg = result.message
            if out_dir:
                msg = f"{result.message} → {out_dir}"
            self.status_var.set(msg[:120])
            if hasattr(self.app, "log"):
                self.app.log(f"📦 {msg}", "success")
            self._selected.clear()
            self._refresh_file_list()
            if bool(self.open_after_var.get()) and out_dir and os.path.isdir(out_dir):
                try:
                    os.startfile(out_dir)
                except OSError:
                    pass
        else:
            self.status_var.set(f"Lỗi: {result.message}")
            if hasattr(self.app, "log"):
                self.app.log(f"📦 {result.message}", "danger")
            messagebox.showerror("Đóng gói", result.message, parent=self.frame)

    def _cleanup_source(self) -> None:
        folder = self.in_var.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showinfo(
                "Dọn",
                "Chưa có thư mục nguồn.\nVD: chọn Nguồn = Desktop\\TempGoi rồi dọn.",
                parent=self.frame,
            )
            return
        profile = self._profile_from_ui()
        exts = get_pack_extensions(profile)
        if not messagebox.askyesno(
            "Dọn nguồn",
            f"Xóa file đuôi {', '.join(exts)} trong:\n{folder}?\n\n"
            "VD: xóa hết .png .dxf sau khi đã ZIP xong.",
            parent=self.frame,
        ):
            return
        n = cleanup_folder(folder, extensions=exts)
        self.status_var.set(f"Đã dọn {n} file")
        self._selected.clear()
        self._refresh_file_list()
        if hasattr(self.app, "log"):
            self.app.log(f"📦 Dọn {n} file trong nguồn", "accent")

    def _open_photoshop(self) -> None:
        ps = find_photoshop()
        if not ps:
            messagebox.showerror("Photoshop", "Không tìm thấy Photoshop.exe", parent=self.frame)
            return
        try:
            os.startfile(ps)
        except OSError as exc:
            messagebox.showerror("Photoshop", str(exc), parent=self.frame)

    def _run_script_quick(self) -> None:
        script = self._script_path()
        if not script:
            messagebox.showinfo(
                "Script",
                "Chọn file .jsx.\nVD: Photoshop_Imports\\Scripts\\XuatFileCat.jsx",
                parent=self.frame,
            )
            return
        ps = find_photoshop()
        if not ps:
            messagebox.showerror("Photoshop", "Không tìm thấy Photoshop.exe", parent=self.frame)
            return
        try:
            subprocess.Popen([ps, script], cwd=os.path.dirname(script) or None)
            self.status_var.set(f"Chạy script: {os.path.basename(script)}")
            if hasattr(self.app, "log"):
                self.app.log(f"🎨 Script: {os.path.basename(script)}", "accent")
        except Exception as exc:
            messagebox.showerror("Photoshop", str(exc), parent=self.frame)

    def _run_ps_batch(self) -> None:
        script = self._script_path()
        if not script:
            messagebox.showinfo(
                "Batch",
                "Chọn script .jsx trước.\nVD: DomMauW1.jsx rồi Batch folder ảnh nguồn.",
                parent=self.frame,
            )
            return
        folder = self.in_var.get().strip()
        if not folder or not os.path.isdir(folder):
            folder = filedialog.askdirectory(title="Folder ảnh batch", parent=self.frame)
            if not folder:
                return
            self.in_var.set(folder)
        ps = find_photoshop()
        if not ps:
            messagebox.showerror("Photoshop", "Không tìm thấy Photoshop.exe", parent=self.frame)
            return
        imgs = [
            os.path.join(folder, n)
            for n in sorted(os.listdir(folder))
            if os.path.isfile(os.path.join(folder, n))
            and os.path.splitext(n)[1].lower() in BATCH_IMG_EXTS
        ]
        if not imgs:
            messagebox.showinfo("Batch", "Không có ảnh trong folder", parent=self.frame)
            return
        if not messagebox.askyesno(
            "Batch Photoshop",
            f"Chạy «{os.path.basename(script)}» trên {len(imgs)} ảnh?\n"
            f"Folder: {folder}\n\n"
            "VD: mỗi ảnh mở → script → lưu → đóng.",
            parent=self.frame,
        ):
            return
        batch_dir = os.path.join(self.base_dir, "Photoshop_Imports")
        os.makedirs(batch_dir, exist_ok=True)
        batch_jsx = os.path.join(batch_dir, "_acc2019_batch_run.jsx")
        script_p = _posix(script)
        lines = [
            "#target photoshop",
            "app.displayDialogs = DialogModes.NO;",
            f'var userScript = new File("{script_p}");',
            "var files = [",
        ]
        for img in imgs:
            lines.append(f'  new File("{_posix(img)}"),')
        lines += [
            "];",
            "var ok=0, fail=0;",
            "for (var i=0; i<files.length; i++) {",
            "  try {",
            "    if (!files[i].exists) { fail++; continue; }",
            "    var doc = app.open(files[i]);",
            "    try { $.evalFile(userScript); } catch(e1) {}",
            "    try { doc.save(); } catch(e2) {}",
            "    try { doc.close(SaveOptions.SAVECHANGES); } catch(e3) {",
            "      try { doc.close(SaveOptions.DONOTSAVECHANGES); } catch(e4) {}",
            "    }",
            "    ok++;",
            "  } catch(e) { fail++; }",
            "}",
            "alert('ACC2019 Batch: ' + ok + ' OK / ' + fail + ' lỗi');",
        ]
        try:
            with open(batch_jsx, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            subprocess.Popen([ps, batch_jsx])
            self.status_var.set(f"Batch {len(imgs)} ảnh…")
            if hasattr(self.app, "log"):
                self.app.log(f"🎨 Batch PS {len(imgs)} ảnh", "accent")
        except Exception as exc:
            messagebox.showerror("Batch", str(exc), parent=self.frame)

    def destroy(self) -> None:
        try:
            save_profile(self.base_dir, self.profile_name, self._profile_from_ui())
        except Exception:
            pass
        if self._settings_win:
            try:
                self._settings_win.destroy()
            except Exception:
                pass


def _decode_drop_path(f) -> str:
    try:
        if isinstance(f, bytes):
            for enc in ("utf-16-le", "utf-8", "mbcs", "cp1258", "latin-1"):
                try:
                    p = f.decode(enc).replace("\x00", "").strip().strip("{}").strip('"')
                    if p and (os.path.exists(p) or "\\" in p or "/" in p):
                        return p
                except Exception:
                    continue
            return f.decode("utf-8", errors="ignore").replace("\x00", "").strip().strip("{}").strip('"')
        return str(f).replace("\x00", "").strip().strip("{}").strip('"')
    except Exception:
        return ""
