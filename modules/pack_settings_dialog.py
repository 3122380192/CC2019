"""Dialog «Quản lý cấu hình sản phẩm» — form đóng gói theo mẫu UI."""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Callable

from modules.pack_engine import (
    ACTION_TYPES,
    list_profiles,
    preview_output_path,
)

BG, CARD, TEXT, MUTED = "#1a1a22", "#252532", "#e8e8f0", "#9a9ab0"
ACCENT, SUCCESS, GOLD, DANGER = "#38bdf8", "#22c55e", "#fbbf24", "#ef4444"
PACK = "#14b8a6"
BTN_RED = "#dc2626"
BTN_BLUE = "#2563eb"
BTN_TEAL = "#0d9488"

ACTION_RADIOS = (
    ("pack_all_zip", "Nén các file đã xử lý"),
    ("copy_all_folder", "Sao chép các file đã xử lý"),
    ("pack_left_match", "Nén theo nhóm ký tự trùng khớp"),
    ("pack_folder_name", "Nén theo danh sách tên từ thư mục Nguồn"),
)


class PackProductConfigDialog:
    """Popup quản lý cấu hình SP — Xóa / Thêm mới / Lưu."""

    def __init__(self, panel: Any) -> None:
        self.panel = panel
        self.win: tk.Toplevel | None = None
        self._canvas: tk.Canvas | None = None
        self._body: tk.Frame | None = None

    def show(self) -> None:
        p = self.panel
        if p._settings_win is not None:
            try:
                p._settings_win.lift()
                p._settings_win.focus_force()
                return
            except tk.TclError:
                p._settings_win = None

        win = tk.Toplevel(p.frame)
        p._settings_win = win
        self.win = win
        win.title("Cấu hình Chi Tiết Sản Phẩm")
        win.configure(bg=BG)
        win.geometry("460x640")
        win.minsize(420, 520)
        try:
            win.attributes("-topmost", True)
            root = getattr(p.app, "root", None)
            if root is not None:
                win.transient(root)
        except tk.TclError:
            pass

        # ── Header ──
        hdr = tk.Frame(win, bg=CARD)
        hdr.pack(fill=tk.X)
        tk.Label(
            hdr, text="QUẢN LÝ CẤU HÌNH SẢN PHẨM",
            font=("Segoe UI", 11, "bold"), fg=TEXT, bg=CARD, pady=10,
        ).pack()

        # ── Scroll body ──
        outer = tk.Frame(win, bg=BG)
        outer.pack(fill=tk.BOTH, expand=True)
        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0, bd=0)
        self._canvas = canvas
        sb = tk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        body = tk.Frame(canvas, bg=BG)
        self._body = body
        win_id = canvas.create_window((0, 0), window=body, anchor="nw")

        def _cfg_body(_e=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _cfg_canvas(e):
            canvas.itemconfig(win_id, width=e.width)

        body.bind("<Configure>", _cfg_body)
        canvas.bind("<Configure>", _cfg_canvas)

        def _wheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _wheel)

        pad_x = 14

        def label(text: str, *, bold: bool = False) -> None:
            tk.Label(
                body, text=text,
                font=("Segoe UI", 8, "bold" if bold else "normal"),
                fg=MUTED if not bold else ACCENT, bg=BG, anchor="w",
            ).pack(fill=tk.X, padx=pad_x, pady=(8, 2))

        def entry(var: tk.StringVar, *, show: str | None = None) -> tk.Entry:
            e = tk.Entry(
                body, textvariable=var, font=("Segoe UI", 9),
                bg=CARD, fg=TEXT, insertbackground=TEXT,
                bd=0, relief=tk.FLAT,
            )
            e.pack(fill=tk.X, padx=pad_x, ipady=6)
            return e

        def card_box() -> tk.Frame:
            fr = tk.Frame(body, bg=CARD, bd=0, highlightthickness=1, highlightbackground="#333344")
            fr.pack(fill=tk.X, padx=pad_x, pady=6)
            return fr

        # ── Chọn cấu hình ──
        label("Chọn cấu hình chỉnh sửa:")
        row = tk.Frame(body, bg=BG)
        row.pack(fill=tk.X, padx=pad_x)
        row.columnconfigure(0, weight=1)
        p.profile_var.set(p.profile_name)
        combo = ttk.Combobox(
            row, textvariable=p.profile_var, state="readonly",
            values=list_profiles(p.base_dir), font=("Segoe UI", 9),
        )
        combo.grid(row=0, column=0, sticky="ew", ipady=2)
        combo.bind("<<ComboboxSelected>>", lambda _e: self._on_pick_profile())
        p._settings_profile_combo = combo

        # ── Tên SP ──
        label("Tên Sản Phẩm:")
        entry(p.product_name_var)

        # ── PS Action ──
        label("Photoshop Action Set:")
        entry(p.ps_action_set_var)
        label("Photoshop Action Name:")
        entry(p.ps_action_name_var)

        # ── Thư mục nguồn ──
        label("Thư Mục Đầu Vào Chứa Ảnh Gốc:")
        path_row = tk.Frame(body, bg=BG)
        path_row.pack(fill=tk.X, padx=pad_x)
        path_row.columnconfigure(0, weight=1)
        tk.Entry(
            path_row, textvariable=p.in_var, font=("Segoe UI", 9),
            bg=CARD, fg=TEXT, insertbackground=TEXT, bd=0,
        ).grid(row=0, column=0, sticky="ew", ipady=6, padx=(0, 4))
        tk.Button(
            path_row, text="Chọn 📁", font=("Segoe UI", 8, "bold"),
            bg=CARD, fg=ACCENT, bd=0, padx=10, pady=4, cursor="hand2",
            command=p._browse_input,
        ).grid(row=0, column=1)

        # ── Loại file PS ──
        box = card_box()
        tk.Label(
            box, text="Loại file sẽ xử lý (Photoshop)",
            font=("Segoe UI", 8, "bold"), fg=TEXT, bg=CARD,
        ).pack(anchor="w", padx=10, pady=(8, 4))
        er = tk.Frame(box, bg=CARD)
        er.pack(fill=tk.X, padx=10, pady=(0, 8))
        for e, v in p.ps_ext_vars.items():
            tk.Checkbutton(
                er, text=f".{e}", variable=v, font=("Segoe UI", 9),
                fg=TEXT, bg=CARD, selectcolor=BG, activebackground=CARD,
                activeforeground=TEXT,
            ).pack(side=tk.LEFT, padx=8)

        # ── Loại file đóng gói ──
        box2 = card_box()
        tk.Label(
            box2, text="Loại file sẽ đóng gói",
            font=("Segoe UI", 8, "bold"), fg=TEXT, bg=CARD,
        ).pack(anchor="w", padx=10, pady=(8, 4))
        er2 = tk.Frame(box2, bg=CARD)
        er2.pack(fill=tk.X, padx=10, pady=2)
        for e, v in p.ext_vars.items():
            tk.Checkbutton(
                er2, text=f".{e}", variable=v, font=("Segoe UI", 9),
                fg=TEXT, bg=CARD, selectcolor=BG, activebackground=CARD,
                activeforeground=TEXT, command=p._refresh_file_list,
            ).pack(side=tk.LEFT, padx=8)
        mode_row = tk.Frame(box2, bg=CARD)
        mode_row.pack(fill=tk.X, padx=10, pady=(4, 8))
        tk.Button(
            mode_row, text="Tùy chọn file cần đóng gói…",
            font=("Segoe UI", 8), bg=BG, fg=MUTED, bd=0, padx=8, pady=4,
            cursor="hand2", command=self._pick_pack_mode,
        ).pack(side=tk.LEFT)
        self._mode_lbl = tk.StringVar(
            value="Đã chọn: Toàn bộ (Mặc định)" if p.pack_mode_var.get() == "all"
            else "Đã chọn: Chỉ file đã tick trong list"
        )
        tk.Label(
            mode_row, textvariable=self._mode_lbl, font=("Segoe UI", 7),
            fg=MUTED, bg=CARD,
        ).pack(side=tk.LEFT, padx=8)

        # ── Hành động ──
        box3 = card_box()
        tk.Label(
            box3, text="Hành động", font=("Segoe UI", 8, "bold"),
            fg=TEXT, bg=CARD,
        ).pack(anchor="w", padx=10, pady=(8, 4))
        # ensure action id
        if p.action_var.get() not in dict(ACTION_RADIOS):
            # có thể đang là label cũ
            label_map = {v: k for k, v in ACTION_TYPES.items()}
            p.action_var.set(label_map.get(p.action_var.get(), "pack_left_match"))

        for aid, alabel in ACTION_RADIOS:
            tk.Radiobutton(
                box3, text=alabel, variable=p.action_var, value=aid,
                font=("Segoe UI", 9), fg=TEXT, bg=CARD, selectcolor=BG,
                activebackground=CARD, activeforeground=TEXT,
                anchor="w", command=self._on_action,
            ).pack(fill=tk.X, padx=14, pady=1)

        pref = tk.Frame(box3, bg=CARD)
        pref.pack(fill=tk.X, padx=28, pady=(2, 2))
        tk.Label(
            pref, text="Số ký tự khớp (từ trái qua phải):",
            font=("Segoe UI", 8), fg=MUTED, bg=CARD,
        ).pack(side=tk.LEFT)
        tk.Spinbox(
            pref, from_=1, to=80, width=5, textvariable=p.prefix_var,
            font=("Consolas", 9), bg=BG, fg=ACCENT, buttonbackground=CARD,
        ).pack(side=tk.LEFT, padx=6)
        zn = tk.Frame(box3, bg=CARD)
        zn.pack(fill=tk.X, padx=14, pady=(6, 4))
        tk.Label(
            zn, text="Tên file ZIP (tùy ý):",
            font=("Segoe UI", 8), fg=MUTED, bg=CARD,
        ).pack(side=tk.LEFT)
        tk.Entry(
            zn, textvariable=p.zip_name_var, font=("Segoe UI", 9),
            bg=BG, fg=GOLD, insertbackground=TEXT, bd=0, width=28,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6, ipady=4)
        tk.Label(
            zn, text=".zip", font=("Segoe UI", 8, "bold"), fg=MUTED, bg=CARD,
        ).pack(side=tk.LEFT)
        tk.Label(
            box3, text="Để trống = tự đặt tên theo kiểu gói (folder nguồn / prefix / giờ…)",
            font=("Segoe UI", 7), fg=MUTED, bg=CARD,
        ).pack(anchor="w", padx=14, pady=(0, 8))

        # ── Tùy chọn sau xử lý ──
        box4 = card_box()
        tk.Label(
            box4, text="Tùy chọn sau xử lý", font=("Segoe UI", 8, "bold"),
            fg=TEXT, bg=CARD,
        ).pack(anchor="w", padx=10, pady=(8, 4))
        tk.Checkbutton(
            box4, text="Xóa các file gốc sau khi đóng gói",
            variable=p.del_after_var, font=("Segoe UI", 9),
            fg=SUCCESS, bg=CARD, selectcolor=BG, activebackground=CARD,
        ).pack(anchor="w", padx=14, pady=1)
        tk.Checkbutton(
            box4, text="Tự động đóng gói sau khi chạy Action",
            variable=p.auto_pack_var, font=("Segoe UI", 9),
            fg=TEXT, bg=CARD, selectcolor=BG, activebackground=CARD,
        ).pack(anchor="w", padx=14, pady=1)
        tk.Checkbutton(
            box4, text="Xóa thư mục nguồn sau khi đóng gói",
            variable=p.del_src_var, font=("Segoe UI", 9),
            fg=DANGER, bg=CARD, selectcolor=BG, activebackground=CARD,
        ).pack(anchor="w", padx=14, pady=1)
        tk.Checkbutton(
            box4, text="Auto backup trước khi xóa (Desktop\\_ACC_Backup)",
            variable=p.auto_backup_var, font=("Segoe UI", 9),
            fg=GOLD, bg=CARD, selectcolor=BG, activebackground=CARD,
        ).pack(anchor="w", padx=14, pady=(1, 8))

        # ── Nhận dạng Excel/CSV ──
        box5 = card_box()
        tk.Label(
            box5, text="Nhận dạng sản phẩm Excel/CSV",
            font=("Segoe UI", 8, "bold"), fg=TEXT, bg=CARD,
        ).pack(anchor="w", padx=10, pady=(8, 4))
        det = tk.Frame(box5, bg=CARD)
        det.pack(fill=tk.X, padx=10, pady=(0, 8))
        det.columnconfigure(0, weight=1)
        det.columnconfigure(1, weight=0)
        tk.Label(
            det, text="Từ khóa nhận dạng (ví dụ: canvas):",
            font=("Segoe UI", 7), fg=MUTED, bg=CARD,
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            det, text="Cột quét nhận dạng (ví dụ B):",
            font=("Segoe UI", 7), fg=MUTED, bg=CARD,
        ).grid(row=0, column=1, sticky="w", padx=(8, 0))
        tk.Entry(
            det, textvariable=p.detect_kw_var, font=("Segoe UI", 9),
            bg=BG, fg=TEXT, insertbackground=TEXT, bd=0,
        ).grid(row=1, column=0, sticky="ew", ipady=4, padx=(0, 6))
        tk.Entry(
            det, textvariable=p.detect_col_var, font=("Segoe UI", 9), width=6,
            bg=BG, fg=TEXT, insertbackground=TEXT, bd=0,
        ).grid(row=1, column=1, sticky="w", ipady=4)

        # ── Xuất / ghi chú phụ ──
        label("Folder con xuất (Desktop\\ngày\\…):")
        sub = tk.Frame(body, bg=BG)
        sub.pack(fill=tk.X, padx=pad_x)
        tk.Entry(
            sub, textvariable=p.product_var, font=("Segoe UI", 9), width=16,
            bg=CARD, fg=GOLD, insertbackground=TEXT, bd=0,
        ).pack(side=tk.LEFT, ipady=4)
        tk.Checkbutton(
            sub, text="Folder theo ngày", variable=p.daily_var,
            font=("Segoe UI", 8), fg=TEXT, bg=BG, selectcolor=CARD,
            activebackground=BG,
        ).pack(side=tk.LEFT, padx=10)
        tk.Checkbutton(
            sub, text="Mở folder sau gói", variable=p.open_after_var,
            font=("Segoe UI", 8), fg=TEXT, bg=BG, selectcolor=CARD,
            activebackground=BG,
        ).pack(side=tk.LEFT)

        self._preview = tk.StringVar()
        tk.Label(
            body, textvariable=self._preview, font=("Consolas", 7),
            fg=ACCENT, bg=BG, anchor="w", wraplength=400, justify="left",
        ).pack(fill=tk.X, padx=pad_x, pady=4)
        self._refresh_preview()

        # spacer
        tk.Frame(body, bg=BG, height=12).pack()

        # ── Footer ──
        foot = tk.Frame(win, bg=BG)
        foot.pack(fill=tk.X, side=tk.BOTTOM, pady=8, padx=10)
        tk.Button(
            foot, text="Xóa 🗑", font=("Segoe UI", 9, "bold"),
            bg=BTN_RED, fg="#fff", bd=0, padx=16, pady=8, cursor="hand2",
            command=self._delete,
        ).pack(side=tk.LEFT, padx=2)
        tk.Button(
            foot, text="Thêm Mới ＋", font=("Segoe UI", 9, "bold"),
            bg=BTN_BLUE, fg="#fff", bd=0, padx=16, pady=8, cursor="hand2",
            command=self._add_new,
        ).pack(side=tk.LEFT, padx=2)
        tk.Button(
            foot, text="Lưu Cấu Hình 💾", font=("Segoe UI", 9, "bold"),
            bg=BTN_TEAL, fg="#fff", bd=0, padx=16, pady=8, cursor="hand2",
            command=self._save,
        ).pack(side=tk.RIGHT, padx=2)

        def _on_close():
            try:
                canvas.unbind_all("<MouseWheel>")
            except Exception:
                pass
            p._settings_win = None
            self.win = None
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", _on_close)
        for v in (p.product_var, p.out_var, p.daily_var, p.in_var, p.action_var):
            try:
                v.trace_add("write", lambda *_: self._refresh_preview())
            except Exception:
                pass

    def _on_pick_profile(self) -> None:
        p = self.panel
        name = p.profile_var.get()
        if not name:
            return
        from modules.pack_engine import set_active_profile

        ok, _, prof = set_active_profile(p.base_dir, name)
        if not ok:
            return
        p.profile_name = name
        p.profile = prof
        p._load_profile_ui()
        p._refresh_file_list()
        p._refresh_profile_combo(name)
        try:
            p._settings_profile_combo["values"] = list_profiles(p.base_dir)
        except Exception:
            pass
        self._refresh_preview()
        self._sync_mode_lbl()

    def _on_action(self) -> None:
        self.panel._update_summary()
        self._refresh_preview()

    def _sync_mode_lbl(self) -> None:
        p = self.panel
        if not hasattr(self, "_mode_lbl"):
            return
        if p.pack_mode_var.get() == "selected" and p._selected:
            self._mode_lbl.set(f"Đã chọn: {len(p._selected)} file trong list")
        else:
            p.pack_mode_var.set("all")
            self._mode_lbl.set("Đã chọn: Toàn bộ (Mặc định)")

    def _pick_pack_mode(self) -> None:
        p = self.panel
        choice = messagebox.askyesnocancel(
            "Tùy chọn file đóng gói",
            "Yes = Toàn bộ file khớp đuôi (mặc định)\n"
            "No  = Chỉ file đang chọn trong list tab chính\n"
            "Cancel = giữ nguyên",
            parent=self.win,
        )
        if choice is None:
            return
        if choice:
            p.pack_mode_var.set("all")
            p._selected = []
        else:
            p.pack_mode_var.set("selected")
            # lấy selection hiện tại nếu có
            try:
                idxs = p.listbox.curselection()
                if idxs and hasattr(p, "_list_paths"):
                    p._selected = [p._list_paths[i] for i in idxs if i < len(p._list_paths)]
            except Exception:
                pass
            if not p._selected:
                messagebox.showinfo(
                    "Tùy chọn",
                    "Chưa có file chọn trên list — sẽ dùng toàn bộ cho đến khi chọn.",
                    parent=self.win,
                )
                p.pack_mode_var.set("all")
        self._sync_mode_lbl()
        p._refresh_file_list()

    def _refresh_preview(self) -> None:
        try:
            path = preview_output_path(self.panel._profile_from_ui())
            self._preview.set(f"→ Xuất: {path}")
        except Exception:
            if hasattr(self, "_preview"):
                self._preview.set("")

    def _save(self) -> None:
        p = self.panel
        # đồng bộ tên SP → product_subfolder / note nếu trống
        name = (p.product_name_var.get() or "").strip()
        if name and not (p.product_var.get() or "").strip():
            safe = name.replace(" ", "_")[:32]
            p.product_var.set(safe)
        if name and p.profile_name in ("Mặc định", "Mac dinh", ""):
            # gợi ý đổi tên profile theo SP — không ép
            pass
        p._save_profile()
        p._update_summary()
        p._refresh_file_list()
        messagebox.showinfo(
            "Lưu cấu hình",
            f"Đã lưu «{p.profile_name}»",
            parent=self.win,
        )
        if hasattr(p.app, "log"):
            p.app.log(f"📦 Đã lưu cấu hình «{p.profile_name}»", "success")

    def _add_new(self) -> None:
        p = self.panel
        name = simpledialog.askstring(
            "Thêm mới",
            "Tên cấu hình sản phẩm mới:\nVD: White Coined Napkins",
            initialvalue=(p.product_name_var.get() or "").strip() or "SP mới",
            parent=self.win,
        )
        if not name:
            return
        name = name.strip()
        from modules.pack_engine import create_profile, set_active_profile

        from_p = p._profile_from_ui()
        from_p["product_name"] = name
        ok, msg = create_profile(p.base_dir, name, from_profile=from_p)
        if not ok:
            # thử không copy nếu trùng? báo lỗi
            messagebox.showerror("Thêm mới", msg, parent=self.win)
            return
        p.profile_name = name
        _, _, prof = set_active_profile(p.base_dir, name)
        p.profile = prof
        p.product_name_var.set(name)
        p.ps_action_set_var.set(p.ps_action_set_var.get() or name)
        p.ps_action_name_var.set(p.ps_action_name_var.get() or name)
        p._refresh_profile_combo(name)
        p._load_profile_ui()
        try:
            p._settings_profile_combo["values"] = list_profiles(p.base_dir)
            p.profile_var.set(name)
        except Exception:
            pass
        self._refresh_preview()
        if hasattr(p.app, "log"):
            p.app.log(f"📦 {msg}", "success")

    def _delete(self) -> None:
        p = self.panel
        name = p.profile_name
        if not messagebox.askyesno(
            "Xóa cấu hình",
            f"Xóa cấu hình «{name}»?\n(Không xóa file ZIP đã tạo)",
            parent=self.win,
        ):
            return
        from modules.pack_engine import delete_profile, set_active_profile

        ok, msg = delete_profile(p.base_dir, name)
        if not ok:
            messagebox.showerror("Xóa", msg, parent=self.win)
            return
        names = list_profiles(p.base_dir)
        new = names[0] if names else "Mặc định"
        _, _, prof = set_active_profile(p.base_dir, new)
        p.profile_name = new
        p.profile = prof
        p._refresh_profile_combo(new)
        p._load_profile_ui()
        try:
            p._settings_profile_combo["values"] = names
            p.profile_var.set(new)
        except Exception:
            pass
        self._refresh_preview()
        messagebox.showinfo("Xóa", msg, parent=self.win)
