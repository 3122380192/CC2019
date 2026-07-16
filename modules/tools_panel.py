"""Tab Tiện ích — công cụ phụ trợ sản xuất (đổi tên, đếm file, sắp ảnh, đơn vị…)."""

from __future__ import annotations

import json
import os
import re
import shutil
import tkinter as tk
from collections import Counter
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

BG, CARD, TEXT, MUTED = "#0c0c14", "#141424", "#e8e8f0", "#82829c"
ACCENT, SUCCESS, GOLD, DANGER = "#00d2ff", "#00e676", "#fbbf24", "#ff6b8a"
TOOLS = "#f0abfc"

IMG_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".gif"}
JUNK_NAMES = {"thumbs.db", "desktop.ini", ".ds_store"}
JUNK_EXTS = {".tmp", ".temp", ".bak", ".crdownload", ".partial"}


def _desktop() -> str:
    for p in (
        os.path.join(os.path.expanduser("~"), "Desktop"),
        os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop"),
    ):
        if os.path.isdir(p):
            return p
    return os.path.expanduser("~")


def _safe_name(name: str) -> str:
    bad = '<>:"/\\|?*'
    for ch in bad:
        name = name.replace(ch, "_")
    return name.strip(" .") or "file"


class ToolsPanel:
    def __init__(self, parent: tk.Misc, app: Any) -> None:
        self.parent = parent
        self.app = app
        self.base_dir = getattr(app, "base_dir", ".")
        self.notes_path = os.path.join(self.base_dir, "tools_notes.json")

        self.folder_var = tk.StringVar()
        self.prefix_var = tk.StringVar()
        self.suffix_var = tk.StringVar()
        self.find_var = tk.StringVar()
        self.repl_var = tk.StringVar()
        self.seq_start_var = tk.IntVar(value=1)
        self.sort_n_var = tk.IntVar(value=6)
        self.unit_in_var = tk.StringVar(value="10")
        self.unit_from = tk.StringVar(value="cm")
        self.unit_to = tk.StringVar(value="in")
        self.unit_out_var = tk.StringVar(value="")
        self.pair_a_var = tk.StringVar(value="png")
        self.pair_b_var = tk.StringVar(value="dxf")
        self.status_var = tk.StringVar(value="Sẵn sàng")
        self.order_id_var = tk.StringVar()
        self.qr_extra_var = tk.StringVar()
        self.ocr_status_var = tk.StringVar(value="Chọn ảnh screenshot portal / dán text")
        self.checklist_vars: dict[str, tk.BooleanVar] = {
            "nhan_don": tk.BooleanVar(value=False),
            "tai_anh": tk.BooleanVar(value=False),
            "patch_dxf": tk.BooleanVar(value=False),
            "xu_ly_ps": tk.BooleanVar(value=False),
            "dong_goi": tk.BooleanVar(value=False),
            "gui_khach": tk.BooleanVar(value=False),
        }
        self._ocr_photo = None
        self._last_ocr_ids: list[str] = []

        self.frame = tk.Frame(parent, bg=BG)
        self.frame.pack(fill=tk.BOTH, expand=True)
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(1, weight=1)

        self._build()
        self._load_notes()

    # ── UI shell ──────────────────────────────────────────────
    def _build(self) -> None:
        top = tk.Frame(self.frame, bg=CARD)
        top.grid(row=0, column=0, sticky="ew")
        tk.Label(
            top, text="🛠 TIỆN ÍCH", font=("Segoe UI", 9, "bold"),
            fg=TOOLS, bg=CARD,
        ).pack(side=tk.LEFT, padx=8, pady=5)
        tk.Label(
            top, textvariable=self.status_var, font=("Segoe UI", 7),
            fg=MUTED, bg=CARD,
        ).pack(side=tk.LEFT, padx=4)
        tk.Button(
            top, text="📂 Desktop", font=("Segoe UI", 7), bg=BG, fg=MUTED,
            bd=0, padx=6, command=lambda: self._open_path(_desktop()), cursor="hand2",
        ).pack(side=tk.RIGHT, padx=4, pady=3)
        tk.Button(
            top, text="📅 Hôm nay", font=("Segoe UI", 7), bg=BG, fg=ACCENT,
            bd=0, padx=6, command=self._open_today, cursor="hand2",
        ).pack(side=tk.RIGHT, padx=2, pady=3)

        # scroll body
        wrap = tk.Frame(self.frame, bg=BG)
        wrap.grid(row=1, column=0, sticky="nsew")
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(0, weight=1)
        canvas = tk.Canvas(wrap, bg=BG, highlightthickness=0, bd=0)
        sb = tk.Scrollbar(wrap, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        body = tk.Frame(canvas, bg=BG)
        cid = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(cid, width=e.width))

        def _wheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

        canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", _wheel))
        canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))

        # Hỗ trợ làm đơn (ưu tiên)
        self._section_order_id_qr(body)
        self._section_ocr(body)
        self._section_checklist(body)
        self._section_backup(body)
        # Công cụ folder / file
        self._section_folder(body)
        self._section_count(body)
        self._section_rename(body)
        self._section_sort(body)
        self._section_pairs(body)
        self._section_units(body)
        self._section_clean(body)
        self._section_notes(body)
        self._section_ideas(body)

    def _card(self, parent: tk.Misc, title: str) -> tk.Frame:
        outer = tk.Frame(parent, bg=BG)
        outer.pack(fill=tk.X, padx=6, pady=4)
        tk.Label(
            outer, text=title, font=("Segoe UI", 8, "bold"),
            fg=TOOLS, bg=BG, anchor="w",
        ).pack(fill=tk.X, padx=2, pady=(2, 1))
        box = tk.Frame(outer, bg=CARD, bd=0, highlightthickness=0)
        box.pack(fill=tk.X, padx=0, pady=1)
        return box

    def _btn(self, parent, text, cmd, fg=ACCENT, **pack) -> tk.Button:
        b = tk.Button(
            parent, text=text, font=("Segoe UI", 7, "bold"),
            bg=BG, fg=fg, bd=0, padx=8, pady=4, cursor="hand2", command=cmd,
        )
        b.pack(**({"side": tk.LEFT, "padx": 2, "pady": 3} | pack))
        return b

    def _log(self, msg: str, tag: str = "accent") -> None:
        self.status_var.set(msg)
        if hasattr(self.app, "log"):
            try:
                self.app.log(f"🛠 {msg}", tag)
            except Exception:
                pass

    # ── A. Order ID + QR ──────────────────────────────────────
    def _section_order_id_qr(self, parent) -> None:
        box = self._card(parent, "A · Mã đơn & QR (phiếu / dán nhãn)")
        row = tk.Frame(box, bg=CARD)
        row.pack(fill=tk.X, padx=6, pady=4)
        row.columnconfigure(1, weight=1)
        tk.Label(row, text="Order ID", font=("Segoe UI", 7), fg=MUTED, bg=CARD).grid(
            row=0, column=0, sticky="w",
        )
        tk.Entry(
            row, textvariable=self.order_id_var, font=("Consolas", 10),
            bg=BG, fg=GOLD, insertbackground=TEXT, bd=0,
        ).grid(row=0, column=1, sticky="ew", ipady=4, padx=4)
        tk.Button(
            row, text="Dán", font=("Segoe UI", 7, "bold"),
            bg=BG, fg=MUTED, bd=0, padx=8, pady=2, cursor="hand2",
            command=self._paste_order,
        ).grid(row=0, column=2)
        br = tk.Frame(box, bg=CARD)
        br.pack(fill=tk.X, padx=6, pady=2)
        self._btn(br, "📱 Tạo QR PNG", self._make_qr, SUCCESS)
        self._btn(br, "Copy mã", self._copy_order, ACCENT)
        self._btn(br, "Tạo folder đơn", self._make_order_folder, GOLD)
        self._btn(br, "Mở QR folder", self._open_qr_folder, MUTED)
        tk.Label(
            box, text="QR lưu: Desktop\\_ACC_QR\\  ·  Folder đơn: Desktop\\YYYY-MM-DD\\<order_id>\\",
            font=("Segoe UI", 6), fg=MUTED, bg=CARD,
        ).pack(anchor="w", padx=8, pady=(0, 2))
        # preview label
        self.qr_preview_var = tk.StringVar(value="")
        tk.Label(
            box, textvariable=self.qr_preview_var, font=("Consolas", 7),
            fg=SUCCESS, bg=CARD, anchor="w",
        ).pack(fill=tk.X, padx=8, pady=(0, 6))

    def _paste_order(self) -> None:
        try:
            text = self.frame.clipboard_get()
        except tk.TclError:
            return
        from modules.tools_order import extract_order_ids

        ids = extract_order_ids(text)
        self.order_id_var.set(ids[0] if ids else text.strip().split()[0] if text.strip() else "")
        self._log(f"Order: {self.order_id_var.get()}")

    def _copy_order(self) -> None:
        oid = self.order_id_var.get().strip()
        if not oid:
            return
        try:
            self.frame.clipboard_clear()
            self.frame.clipboard_append(oid)
            self._log(f"Đã copy {oid}", "success")
        except tk.TclError:
            pass

    def _qr_dir(self) -> str:
        d = os.path.join(_desktop(), "_ACC_QR")
        os.makedirs(d, exist_ok=True)
        return d

    def _make_qr(self) -> None:
        from modules.tools_order import generate_qr_png

        oid = self.order_id_var.get().strip()
        if not oid:
            messagebox.showwarning("QR", "Nhập order_id trước", parent=self.frame)
            return
        out = os.path.join(self._qr_dir(), f"{_safe_name(oid)}.png")
        try:
            path = generate_qr_png(oid, out)
            self.qr_preview_var.set(f"→ {path}")
            self._log(f"QR: {os.path.basename(path)}", "success")
            if messagebox.askyesno("QR", f"Đã tạo QR:\n{path}\n\nMở folder?", parent=self.frame):
                self._open_path(self._qr_dir())
        except Exception as e:
            messagebox.showerror(
                "QR",
                f"{e}\n\nCài QR chuẩn:\npip install \"qrcode[pil]\"",
                parent=self.frame,
            )

    def _open_qr_folder(self) -> None:
        self._open_path(self._qr_dir())

    def _make_order_folder(self) -> None:
        oid = self.order_id_var.get().strip()
        if not oid:
            messagebox.showwarning("Folder đơn", "Nhập order_id", parent=self.frame)
            return
        day = datetime.now().strftime("%Y-%m-%d")
        path = os.path.join(_desktop(), day, _safe_name(oid))
        os.makedirs(path, exist_ok=True)
        self.folder_var.set(path)
        self._log(f"Folder đơn: {path}", "success")
        self._open_path(path)

    # ── B. OCR ────────────────────────────────────────────────
    def _section_ocr(self, parent) -> None:
        box = self._card(parent, "B · OCR mã đơn từ screenshot portal")
        row = tk.Frame(box, bg=CARD)
        row.pack(fill=tk.X, padx=6, pady=4)
        self._btn(row, "🖼 Chọn ảnh…", self._ocr_pick, ACCENT)
        self._btn(row, "📋 OCR clipboard (ảnh)", self._ocr_clipboard, GOLD)
        self._btn(row, "Dán text → trích mã", self._ocr_from_paste, MUTED)
        tk.Label(
            box, textvariable=self.ocr_status_var, font=("Segoe UI", 7),
            fg=MUTED, bg=CARD, anchor="w", wraplength=440, justify="left",
        ).pack(fill=tk.X, padx=8, pady=2)
        self.ocr_ids_var = tk.StringVar(value="")
        tk.Label(
            box, textvariable=self.ocr_ids_var, font=("Consolas", 8, "bold"),
            fg=GOLD, bg=CARD, anchor="w", wraplength=440, justify="left",
        ).pack(fill=tk.X, padx=8, pady=2)
        row2 = tk.Frame(box, bg=CARD)
        row2.pack(fill=tk.X, padx=6, pady=(0, 6))
        self._btn(row2, "Dùng mã đầu → Order ID", self._ocr_use_first, SUCCESS)
        self._btn(row2, "Copy tất cả mã", self._ocr_copy_all, ACCENT)
        tk.Label(
            box, text="Gợi ý: cài Tesseract OCR để đọc chữ rõ hơn (eng). Không có vẫn đọc được filename + Windows OCR.",
            font=("Segoe UI", 6), fg=MUTED, bg=CARD,
        ).pack(anchor="w", padx=8, pady=(0, 4))

    def _apply_ocr_result(self, ids: list[str], text: str, engine: str, src: str) -> None:
        self._last_ocr_ids = ids
        if ids:
            self.ocr_ids_var.set("Mã: " + " · ".join(ids[:8]) + (f" +{len(ids)-8}" if len(ids) > 8 else ""))
            self.ocr_status_var.set(f"OK ({engine}) · {os.path.basename(src) if src else 'text'}")
            self._log(f"OCR {len(ids)} mã · {engine}", "success")
        else:
            preview = (text or "")[:120].replace("\n", " ")
            self.ocr_ids_var.set("(không thấy mã — thử dán text hoặc cài Tesseract)")
            self.ocr_status_var.set(f"engine={engine} · raw: {preview or '—'}")
            self._log("OCR không thấy order_id", "danger")

    def _ocr_pick(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Screenshot portal",
            filetypes=[("Ảnh", "*.png;*.jpg;*.jpeg;*.bmp;*.webp;*.tif"), ("All", "*.*")],
            parent=self.frame,
        )
        if not paths:
            return
        from modules.tools_order import ocr_extract_orders

        all_ids: list[str] = []
        last_text, last_eng, last_src = "", "none", ""
        for p in paths:
            ids, text, eng = ocr_extract_orders(p)
            all_ids.extend(ids)
            last_text, last_eng, last_src = text, eng, p
        # unique
        seen, uniq = set(), []
        for i in all_ids:
            k = i.upper()
            if k not in seen:
                seen.add(k)
                uniq.append(i)
        self._apply_ocr_result(uniq, last_text, last_eng, last_src)

    def _ocr_clipboard(self) -> None:
        """OCR ảnh đang copy trong clipboard (Win)."""
        try:
            from PIL import ImageGrab, Image
        except ImportError:
            messagebox.showerror("OCR", "Cần Pillow", parent=self.frame)
            return
        img = ImageGrab.grabclipboard()
        if img is None:
            messagebox.showinfo(
                "OCR clipboard",
                "Clipboard không có ảnh.\nWin+Shift+S chụp → Ctrl+C → bấm lại.",
                parent=self.frame,
            )
            return
        if not isinstance(img, Image.Image):
            # list of files
            if isinstance(img, list) and img:
                from modules.tools_order import ocr_extract_orders
                ids, text, eng = ocr_extract_orders(str(img[0]))
                self._apply_ocr_result(ids, text, eng, str(img[0]))
                return
            messagebox.showinfo("OCR", "Clipboard không phải ảnh", parent=self.frame)
            return
        tmp = os.path.join(self.base_dir, "_ocr_clipboard.png")
        try:
            img.convert("RGB").save(tmp)
            from modules.tools_order import ocr_extract_orders
            ids, text, eng = ocr_extract_orders(tmp)
            self._apply_ocr_result(ids, text, eng, tmp)
        except Exception as e:
            messagebox.showerror("OCR", str(e), parent=self.frame)

    def _ocr_from_paste(self) -> None:
        try:
            text = self.frame.clipboard_get()
        except tk.TclError:
            text = ""
        if not text.strip():
            messagebox.showinfo("OCR", "Clipboard trống — copy text từ portal trước", parent=self.frame)
            return
        from modules.tools_order import extract_order_ids

        ids = extract_order_ids(text)
        self._apply_ocr_result(ids, text, "clipboard-text", "")

    def _ocr_use_first(self) -> None:
        if not self._last_ocr_ids:
            messagebox.showinfo("OCR", "Chưa có mã", parent=self.frame)
            return
        self.order_id_var.set(self._last_ocr_ids[0])
        self._log(f"Dùng mã: {self._last_ocr_ids[0]}", "success")

    def _ocr_copy_all(self) -> None:
        if not self._last_ocr_ids:
            return
        try:
            self.frame.clipboard_clear()
            self.frame.clipboard_append("\n".join(self._last_ocr_ids))
            self._log(f"Copy {len(self._last_ocr_ids)} mã", "success")
        except tk.TclError:
            pass

    # ── C. Checklist làm đơn ──────────────────────────────────
    def _section_checklist(self, parent) -> None:
        box = self._card(parent, "C · Checklist làm đơn (theo dõi nhanh)")
        labels = (
            ("nhan_don", "1. Nhận đơn / gán SP"),
            ("tai_anh", "2. Tải ảnh gốc"),
            ("patch_dxf", "3. Patch / DXF / Spot"),
            ("xu_ly_ps", "4. Xử lý Photoshop"),
            ("dong_goi", "5. Đóng gói ZIP"),
            ("gui_khach", "6. Gửi / đánh dấu xong"),
        )
        gr = tk.Frame(box, bg=CARD)
        gr.pack(fill=tk.X, padx=6, pady=4)
        for key, lab in labels:
            tk.Checkbutton(
                gr, text=lab, variable=self.checklist_vars[key],
                font=("Segoe UI", 8), fg=TEXT, bg=CARD, selectcolor=BG,
                activebackground=CARD, anchor="w",
            ).pack(fill=tk.X, padx=4, pady=0)
        row = tk.Frame(box, bg=CARD)
        row.pack(fill=tk.X, padx=6, pady=(0, 6))
        self._btn(row, "Reset checklist", self._reset_checklist, MUTED)
        self._btn(row, "Lưu theo order_id", self._save_checklist, SUCCESS)

    def _reset_checklist(self) -> None:
        for v in self.checklist_vars.values():
            v.set(False)

    def _save_checklist(self) -> None:
        oid = self.order_id_var.get().strip() or "no_order"
        path = os.path.join(self.base_dir, "tools_order_checklists.json")
        data = {}
        if os.path.isfile(path):
            try:
                data = json.loads(Path(path).read_text(encoding="utf-8"))
            except Exception:
                data = {}
        data[oid] = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "checks": {k: bool(v.get()) for k, v in self.checklist_vars.items()},
        }
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self._log(f"Checklist lưu: {oid}", "success")

    # ── D. Backup ─────────────────────────────────────────────
    def _section_backup(self, parent) -> None:
        box = self._card(parent, "D · Auto backup + thống kê mã đơn (folder ngày)")
        tk.Label(
            box,
            text="Backup gói: Desktop\\_ACC_Backup\\…\n"
                 "Lịch sử đơn: Desktop\\YYYY-MM-DD\\ma_don.txt + lich_su_don.txt\n"
                 "(tự ghi khi nhận/làm đơn trên tab Sản xuất)",
            font=("Segoe UI", 7), fg=TEXT, bg=CARD, justify="left", anchor="w",
        ).pack(fill=tk.X, padx=8, pady=4)
        row = tk.Frame(box, bg=CARD)
        row.pack(fill=tk.X, padx=6, pady=(0, 2))
        self._btn(row, "📂 Mở _ACC_Backup", self._open_backup_root, GOLD)
        self._btn(row, "Backup folder đang chọn", self._backup_current_folder, SUCCESS)
        self._btn(row, "Sang tab Đóng gói", lambda: self._goto_tab("pack"), ACCENT)
        row2 = tk.Frame(box, bg=CARD)
        row2.pack(fill=tk.X, padx=6, pady=(0, 6))
        self._btn(row2, "📊 Folder ngày + thống kê", self._open_day_stats, TOOLS)
        self._btn(row2, "📝 Mở ma_don.txt", self._open_ids_file, SUCCESS)
        self._btn(row2, "Copy hết mã hôm nay", self._copy_day_ids, ACCENT)

    def _open_backup_root(self) -> None:
        from modules.tools_order import default_backup_root

        root = default_backup_root()
        os.makedirs(root, exist_ok=True)
        self._open_path(root)

    def _backup_current_folder(self) -> None:
        folder = self._folder()
        if not folder:
            return
        from modules.tools_order import backup_folder_tree

        dest = backup_folder_tree(folder, label=os.path.basename(folder), log=lambda m: self._log(m, "success"))
        if dest:
            messagebox.showinfo("Backup", f"Đã backup:\n{dest}", parent=self.frame)
        else:
            messagebox.showwarning("Backup", "Không backup được", parent=self.frame)

    def _goto_tab(self, tid: str) -> None:
        if hasattr(self.app, "show_tab"):
            try:
                self.app.show_tab(tid)
            except Exception:
                pass

    def _open_day_stats(self) -> None:
        from modules.emb_stats import get_emb_today_stats, open_today_stats_folder

        st = get_emb_today_stats()
        folder = open_today_stats_folder()
        n = st.get("ids_in_text") or st.get("orders") or 0
        self._log(f"Thống kê: {n} mã · {folder}", "success")
        messagebox.showinfo(
            "Thống kê đơn",
            f"Hôm nay: {n} đơn tool (không trùng)\n"
            f"Folder Desktop\\ngày: {st.get('folder_count', 0)}\n"
            f"App: {st.get('orders', 0)} · Patch/DXF {st.get('patch_dxf', 0)}\n"
            f"Telegram: gửi khi nhận đơn mới (trùng = bỏ)\n\n"
            f"{folder}\n\n"
            f"ma_don.txt · lich_su_don.txt · thong_ke_don.txt",
            parent=self.frame,
        )

    def _open_ids_file(self) -> None:
        from modules.emb_stats import open_today_ids_file

        path = open_today_ids_file()
        self._log(f"Mở {os.path.basename(path)}", "accent")

    def _copy_day_ids(self) -> None:
        from modules.emb_stats import copy_today_ids_text

        text = copy_today_ids_text()
        if not text:
            messagebox.showinfo("Mã đơn", "Chưa có mã hôm nay", parent=self.frame)
            return
        try:
            self.frame.clipboard_clear()
            self.frame.clipboard_append(text)
            n = len([x for x in text.splitlines() if x.strip()])
            self._log(f"Copy {n} mã hôm nay", "success")
        except tk.TclError:
            pass

    # ── 1. Folder ─────────────────────────────────────────────
    def _section_folder(self, parent) -> None:
        box = self._card(parent, "1 · Thư mục làm việc")
        row = tk.Frame(box, bg=CARD)
        row.pack(fill=tk.X, padx=6, pady=4)
        tk.Entry(
            row, textvariable=self.folder_var, font=("Segoe UI", 8),
            bg=BG, fg=TEXT, insertbackground=TEXT, bd=0,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4, padx=(0, 4))
        self._btn(row, "…", self._browse_folder)
        self._btn(row, "Mở", lambda: self._open_path(self.folder_var.get()), SUCCESS)
        self._btn(row, "Copy path", self._copy_path, GOLD)
        tk.Label(
            box, text="Kéo thả folder vào đây (nếu app hỗ trợ drop) · hoặc bấm …",
            font=("Segoe UI", 6), fg=MUTED, bg=CARD,
        ).pack(anchor="w", padx=8, pady=(0, 4))

    def _browse_folder(self) -> None:
        d = filedialog.askdirectory(title="Chọn thư mục", parent=self.frame)
        if d:
            self.folder_var.set(d)
            self._log(f"Folder: {d}")

    def _open_path(self, path: str) -> None:
        path = (path or "").strip()
        if not path or not os.path.exists(path):
            messagebox.showwarning("Mở", "Đường dẫn không hợp lệ", parent=self.frame)
            return
        try:
            os.startfile(path)
        except OSError as e:
            messagebox.showerror("Mở", str(e), parent=self.frame)

    def _copy_path(self) -> None:
        path = self.folder_var.get().strip()
        if not path:
            return
        try:
            self.frame.clipboard_clear()
            self.frame.clipboard_append(path)
            self._log("Đã copy path", "success")
        except tk.TclError:
            pass

    def _open_today(self) -> None:
        day = datetime.now().strftime("%Y-%m-%d")
        p = os.path.join(_desktop(), day)
        if not os.path.isdir(p):
            os.makedirs(p, exist_ok=True)
        self.folder_var.set(p)
        self._open_path(p)

    def _folder(self) -> str | None:
        f = self.folder_var.get().strip()
        if not f or not os.path.isdir(f):
            messagebox.showwarning("Folder", "Chọn thư mục hợp lệ trước", parent=self.frame)
            return None
        return f

    # ── 2. Count ──────────────────────────────────────────────
    def _section_count(self, parent) -> None:
        box = self._card(parent, "2 · Đếm file theo đuôi")
        row = tk.Frame(box, bg=CARD)
        row.pack(fill=tk.X, padx=6, pady=4)
        self._btn(row, "📊 Đếm ngay", self._count_files, SUCCESS)
        self.count_var = tk.StringVar(value="—")
        tk.Label(
            box, textvariable=self.count_var, font=("Consolas", 7),
            fg=TEXT, bg=CARD, anchor="w", justify="left", wraplength=440,
        ).pack(fill=tk.X, padx=8, pady=(0, 6))

    def _count_files(self) -> None:
        folder = self._folder()
        if not folder:
            return
        ctr: Counter[str] = Counter()
        total = 0
        try:
            for name in os.listdir(folder):
                path = os.path.join(folder, name)
                if not os.path.isfile(path):
                    continue
                ext = os.path.splitext(name)[1].lower() or "(no ext)"
                ctr[ext] += 1
                total += 1
        except OSError as e:
            messagebox.showerror("Đếm", str(e), parent=self.frame)
            return
        if not total:
            self.count_var.set("Folder trống")
            return
        parts = [f"{ext} × {n}" for ext, n in sorted(ctr.items(), key=lambda x: (-x[1], x[0]))]
        self.count_var.set(f"Tổng {total} file · " + " · ".join(parts[:12]))
        self._log(f"Đếm {total} file trong {os.path.basename(folder)}", "success")

    # ── 3. Rename ─────────────────────────────────────────────
    def _section_rename(self, parent) -> None:
        box = self._card(parent, "3 · Đổi tên hàng loạt")
        g = tk.Frame(box, bg=CARD)
        g.pack(fill=tk.X, padx=6, pady=4)
        for i, (lab, var) in enumerate((
            ("Tiền tố", self.prefix_var),
            ("Hậu tố", self.suffix_var),
            ("Tìm", self.find_var),
            ("Thay", self.repl_var),
        )):
            tk.Label(g, text=lab, font=("Segoe UI", 7), fg=MUTED, bg=CARD).grid(row=0, column=i * 2, sticky="w")
            tk.Entry(
                g, textvariable=var, font=("Segoe UI", 8), width=10,
                bg=BG, fg=TEXT, insertbackground=TEXT, bd=0,
            ).grid(row=0, column=i * 2 + 1, padx=2, ipady=2)
        row = tk.Frame(box, bg=CARD)
        row.pack(fill=tk.X, padx=6, pady=2)
        tk.Label(row, text="Bắt đầu #", font=("Segoe UI", 7), fg=MUTED, bg=CARD).pack(side=tk.LEFT)
        tk.Spinbox(
            row, from_=0, to=9999, width=5, textvariable=self.seq_start_var,
            font=("Consolas", 8), bg=BG, fg=ACCENT, buttonbackground=CARD,
        ).pack(side=tk.LEFT, padx=4)
        self._btn(row, "Áp dụng (prefix/suffix/tìm-thay)", self._batch_rename, GOLD)
        self._btn(row, "Đánh số 001…", self._rename_sequence, ACCENT)
        tk.Label(
            box, text="Chỉ file trong folder (không đệ quy). Có hộp xác nhận trước khi đổi.",
            font=("Segoe UI", 6), fg=MUTED, bg=CARD,
        ).pack(anchor="w", padx=8, pady=(0, 4))

    def _list_files(self, folder: str) -> list[str]:
        try:
            names = sorted(os.listdir(folder), key=lambda s: s.lower())
        except OSError:
            return []
        return [n for n in names if os.path.isfile(os.path.join(folder, n))]

    def _batch_rename(self) -> None:
        folder = self._folder()
        if not folder:
            return
        pre = self.prefix_var.get()
        suf = self.suffix_var.get()
        find = self.find_var.get()
        repl = self.repl_var.get()
        if not pre and not suf and not find:
            messagebox.showinfo("Đổi tên", "Nhập tiền tố / hậu tố / tìm-thay", parent=self.frame)
            return
        files = self._list_files(folder)
        plan: list[tuple[str, str]] = []
        for name in files:
            stem, ext = os.path.splitext(name)
            new_stem = stem
            if find:
                new_stem = new_stem.replace(find, repl)
            new_stem = f"{pre}{new_stem}{suf}"
            new_name = _safe_name(new_stem) + ext
            if new_name != name:
                plan.append((name, new_name))
        self._apply_renames(folder, plan)

    def _rename_sequence(self) -> None:
        folder = self._folder()
        if not folder:
            return
        files = self._list_files(folder)
        start = int(self.seq_start_var.get() or 1)
        plan = []
        for i, name in enumerate(files):
            _stem, ext = os.path.splitext(name)
            new_name = f"{start + i:03d}{ext.lower()}"
            if new_name != name:
                plan.append((name, new_name))
        self._apply_renames(folder, plan)

    def _apply_renames(self, folder: str, plan: list[tuple[str, str]]) -> None:
        if not plan:
            messagebox.showinfo("Đổi tên", "Không có file nào cần đổi", parent=self.frame)
            return
        preview = "\n".join(f"{a}  →  {b}" for a, b in plan[:12])
        extra = f"\n… +{len(plan) - 12} file nữa" if len(plan) > 12 else ""
        if not messagebox.askyesno(
            "Xác nhận đổi tên",
            f"Đổi {len(plan)} file?\n\n{preview}{extra}",
            parent=self.frame,
        ):
            return
        # 2-pass tránh đụng tên
        tmp_map: list[tuple[str, str, str]] = []
        ok = 0
        try:
            for i, (old, new) in enumerate(plan):
                src = os.path.join(folder, old)
                tmp = os.path.join(folder, f".__tmp_rename_{i}__{new}")
                os.rename(src, tmp)
                tmp_map.append((tmp, os.path.join(folder, new), new))
            for tmp, final, _new in tmp_map:
                if os.path.exists(final):
                    base, ext = os.path.splitext(final)
                    k = 2
                    while os.path.exists(f"{base}_{k}{ext}"):
                        k += 1
                    final = f"{base}_{k}{ext}"
                os.rename(tmp, final)
                ok += 1
        except OSError as e:
            messagebox.showerror("Đổi tên", str(e), parent=self.frame)
            return
        self._log(f"Đã đổi tên {ok} file", "success")
        messagebox.showinfo("Đổi tên", f"Xong {ok} file", parent=self.frame)

    # ── 4. Sort images ────────────────────────────────────────
    def _section_sort(self, parent) -> None:
        box = self._card(parent, "4 · Sắp xếp ảnh")
        row = tk.Frame(box, bg=CARD)
        row.pack(fill=tk.X, padx=6, pady=4)
        tk.Label(row, text="N ký tự đầu → folder", font=("Segoe UI", 7), fg=MUTED, bg=CARD).pack(side=tk.LEFT)
        tk.Spinbox(
            row, from_=1, to=40, width=4, textvariable=self.sort_n_var,
            font=("Consolas", 8), bg=BG, fg=ACCENT, buttonbackground=CARD,
        ).pack(side=tk.LEFT, padx=4)
        self._btn(row, "Tách vào subfolder", self._sort_by_prefix, SUCCESS)
        self._btn(row, "Gom ảnh → _images", self._collect_images, GOLD)
        tk.Label(
            box, text="VD N=6: ABC123_x.png + ABC123_y.png → folder ABC123\\",
            font=("Segoe UI", 6), fg=MUTED, bg=CARD,
        ).pack(anchor="w", padx=8, pady=(0, 4))

    def _sort_by_prefix(self) -> None:
        folder = self._folder()
        if not folder:
            return
        n = max(1, int(self.sort_n_var.get() or 1))
        moved = 0
        try:
            for name in self._list_files(folder):
                ext = os.path.splitext(name)[1].lower()
                if ext not in IMG_EXTS:
                    continue
                stem = os.path.splitext(name)[0]
                key = _safe_name(stem[:n] if len(stem) >= n else stem)
                dest_dir = os.path.join(folder, key)
                os.makedirs(dest_dir, exist_ok=True)
                src = os.path.join(folder, name)
                dst = os.path.join(dest_dir, name)
                if os.path.abspath(src) == os.path.abspath(dst):
                    continue
                if os.path.exists(dst):
                    continue
                shutil.move(src, dst)
                moved += 1
        except OSError as e:
            messagebox.showerror("Sắp xếp", str(e), parent=self.frame)
            return
        self._log(f"Sắp xếp: chuyển {moved} ảnh vào subfolder (N={n})", "success")
        messagebox.showinfo("Sắp xếp ảnh", f"Đã chuyển {moved} ảnh", parent=self.frame)

    def _collect_images(self) -> None:
        folder = self._folder()
        if not folder:
            return
        dest = os.path.join(folder, "_images")
        os.makedirs(dest, exist_ok=True)
        moved = 0
        try:
            for name in self._list_files(folder):
                if os.path.splitext(name)[1].lower() not in IMG_EXTS:
                    continue
                src = os.path.join(folder, name)
                dst = os.path.join(dest, name)
                if os.path.exists(dst):
                    continue
                shutil.move(src, dst)
                moved += 1
        except OSError as e:
            messagebox.showerror("Gom ảnh", str(e), parent=self.frame)
            return
        self._log(f"Gom {moved} ảnh → _images", "success")
        messagebox.showinfo("Gom ảnh", f"Đã gom {moved} ảnh vào _images\\", parent=self.frame)

    # ── 5. Missing pairs ──────────────────────────────────────
    def _section_pairs(self, parent) -> None:
        box = self._card(parent, "5 · Thiếu cặp file (vd png ↔ dxf)")
        row = tk.Frame(box, bg=CARD)
        row.pack(fill=tk.X, padx=6, pady=4)
        tk.Label(row, text="A", font=("Segoe UI", 7), fg=MUTED, bg=CARD).pack(side=tk.LEFT)
        tk.Entry(row, textvariable=self.pair_a_var, width=6, font=("Consolas", 8), bg=BG, fg=TEXT, bd=0).pack(
            side=tk.LEFT, padx=2, ipady=2,
        )
        tk.Label(row, text="↔ B", font=("Segoe UI", 7), fg=MUTED, bg=CARD).pack(side=tk.LEFT)
        tk.Entry(row, textvariable=self.pair_b_var, width=6, font=("Consolas", 8), bg=BG, fg=TEXT, bd=0).pack(
            side=tk.LEFT, padx=2, ipady=2,
        )
        self._btn(row, "Quét thiếu cặp", self._scan_pairs, DANGER)
        self.pair_var = tk.StringVar(value="—")
        tk.Label(
            box, textvariable=self.pair_var, font=("Consolas", 7),
            fg=GOLD, bg=CARD, anchor="w", justify="left", wraplength=440,
        ).pack(fill=tk.X, padx=8, pady=(0, 6))

    def _scan_pairs(self) -> None:
        folder = self._folder()
        if not folder:
            return
        a = self.pair_a_var.get().strip().lower().lstrip(".")
        b = self.pair_b_var.get().strip().lower().lstrip(".")
        if not a or not b:
            return
        stems_a, stems_b = set(), set()
        for name in self._list_files(folder):
            stem, ext = os.path.splitext(name)
            ext = ext.lower().lstrip(".")
            if ext == a or (a == "jpg" and ext == "jpeg") or (a == "tif" and ext == "tiff"):
                stems_a.add(stem.lower())
            if ext == b or (b == "jpg" and ext == "jpeg") or (b == "tif" and ext == "tiff"):
                stems_b.add(stem.lower())
        miss_b = sorted(stems_a - stems_b)
        miss_a = sorted(stems_b - stems_a)
        lines = []
        if miss_b:
            lines.append(f"Có .{a} thiếu .{b}: {', '.join(miss_b[:8])}" + (f" +{len(miss_b)-8}" if len(miss_b) > 8 else ""))
        if miss_a:
            lines.append(f"Có .{b} thiếu .{a}: {', '.join(miss_a[:8])}" + (f" +{len(miss_a)-8}" if len(miss_a) > 8 else ""))
        if not lines:
            self.pair_var.set(f"Đủ cặp .{a} ↔ .{b} ({len(stems_a)} cặp)")
            self._log("Đủ cặp file", "success")
        else:
            self.pair_var.set(" · ".join(lines))
            self._log(f"Thiếu cặp: {len(miss_b)}+{len(miss_a)}", "danger")

    # ── 6. Units ──────────────────────────────────────────────
    def _section_units(self, parent) -> None:
        box = self._card(parent, "6 · Đổi đơn vị (thêu / in ấn)")
        row = tk.Frame(box, bg=CARD)
        row.pack(fill=tk.X, padx=6, pady=4)
        tk.Entry(
            row, textvariable=self.unit_in_var, width=10, font=("Consolas", 9),
            bg=BG, fg=TEXT, insertbackground=TEXT, bd=0,
        ).pack(side=tk.LEFT, ipady=3)
        units = ("mm", "cm", "in", "px@300dpi")
        ttk.Combobox(row, textvariable=self.unit_from, values=units, width=9, state="readonly").pack(
            side=tk.LEFT, padx=3,
        )
        tk.Label(row, text="→", fg=MUTED, bg=CARD).pack(side=tk.LEFT)
        ttk.Combobox(row, textvariable=self.unit_to, values=units, width=9, state="readonly").pack(
            side=tk.LEFT, padx=3,
        )
        self._btn(row, "Đổi", self._convert_units, ACCENT)
        tk.Label(
            box, textvariable=self.unit_out_var, font=("Consolas", 9, "bold"),
            fg=SUCCESS, bg=CARD, anchor="w",
        ).pack(fill=tk.X, padx=8, pady=(0, 6))

    def _to_mm(self, val: float, unit: str) -> float:
        u = unit.lower()
        if u == "mm":
            return val
        if u == "cm":
            return val * 10
        if u == "in":
            return val * 25.4
        if u.startswith("px"):
            return val / 300.0 * 25.4
        return val

    def _from_mm(self, mm: float, unit: str) -> float:
        u = unit.lower()
        if u == "mm":
            return mm
        if u == "cm":
            return mm / 10
        if u == "in":
            return mm / 25.4
        if u.startswith("px"):
            return mm / 25.4 * 300.0
        return mm

    def _convert_units(self) -> None:
        raw = self.unit_in_var.get().strip().replace(",", ".")
        try:
            val = float(raw)
        except ValueError:
            messagebox.showwarning("Đơn vị", "Nhập số hợp lệ", parent=self.frame)
            return
        mm = self._to_mm(val, self.unit_from.get())
        out = self._from_mm(mm, self.unit_to.get())
        self.unit_out_var.set(f"{val:g} {self.unit_from.get()}  =  {out:.4g} {self.unit_to.get()}")

    # ── 7. Clean junk ─────────────────────────────────────────
    def _section_clean(self, parent) -> None:
        box = self._card(parent, "7 · Dọn file rác")
        row = tk.Frame(box, bg=CARD)
        row.pack(fill=tk.X, padx=6, pady=4)
        self._btn(row, "🗑 Xóa .tmp / Thumbs.db…", self._clean_junk, DANGER)
        tk.Label(
            box, text="Chỉ trong folder đang chọn (không đệ quy)",
            font=("Segoe UI", 6), fg=MUTED, bg=CARD,
        ).pack(anchor="w", padx=8, pady=(0, 4))

    def _clean_junk(self) -> None:
        folder = self._folder()
        if not folder:
            return
        targets = []
        for name in self._list_files(folder):
            low = name.lower()
            ext = os.path.splitext(low)[1]
            if low in JUNK_NAMES or ext in JUNK_EXTS:
                targets.append(name)
        if not targets:
            messagebox.showinfo("Dọn rác", "Không thấy file rác", parent=self.frame)
            return
        if not messagebox.askyesno("Dọn rác", f"Xóa {len(targets)} file?\n" + "\n".join(targets[:10]), parent=self.frame):
            return
        n = 0
        for name in targets:
            try:
                os.remove(os.path.join(folder, name))
                n += 1
            except OSError:
                pass
        self._log(f"Đã xóa {n} file rác", "success")

    # ── 8. Notes ──────────────────────────────────────────────
    def _section_notes(self, parent) -> None:
        box = self._card(parent, "8 · Ghi chú nhanh (lưu local)")
        self.notes_txt = tk.Text(
            box, height=4, font=("Segoe UI", 8),
            bg=BG, fg=TEXT, insertbackground=TEXT, bd=0, wrap=tk.WORD,
        )
        self.notes_txt.pack(fill=tk.X, padx=6, pady=4)
        row = tk.Frame(box, bg=CARD)
        row.pack(fill=tk.X, padx=6, pady=(0, 6))
        self._btn(row, "💾 Lưu ghi chú", self._save_notes, SUCCESS)
        self._btn(row, "Xóa trắng", self._clear_notes, MUTED)

    def _load_notes(self) -> None:
        try:
            if os.path.isfile(self.notes_path):
                data = json.loads(Path(self.notes_path).read_text(encoding="utf-8"))
                text = data.get("text") or ""
                self.notes_txt.insert("1.0", text)
        except Exception:
            pass

    def _save_notes(self) -> None:
        text = self.notes_txt.get("1.0", tk.END).rstrip()
        try:
            Path(self.notes_path).write_text(
                json.dumps({"text": text, "updated": datetime.now().isoformat()}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._log("Đã lưu ghi chú", "success")
        except OSError as e:
            messagebox.showerror("Ghi chú", str(e), parent=self.frame)

    def _clear_notes(self) -> None:
        self.notes_txt.delete("1.0", tk.END)

    # ── 9. Ideas roadmap ──────────────────────────────────────
    def _section_ideas(self, parent) -> None:
        box = self._card(parent, "9 · Gợi ý thêm (hỗ trợ làm đơn)")
        ideas = (
            "✓ Đã có: QR order_id · OCR screenshot · backup trước xóa · checklist\n"
            "• Timer theo đơn (bắt đầu → xong, thống kê ca)\n"
            "• So sánh 2 folder (thiếu file khi gửi khách)\n"
            "• Resize / nén ảnh hàng loạt trước pack\n"
            "• In phiếu QR + order_id (PDF 1 trang)\n"
            "• Gắn order_id vào tên file hàng loạt (prefix mã)\n"
            "• Hotkey: OCR clipboard · tạo QR · nhảy tab Sản xuất\n"
            "• Đồng bộ checklist với tab Sản xuất / EMB history"
        )
        tk.Label(
            box, text=ideas, font=("Segoe UI", 7), fg=MUTED, bg=CARD,
            anchor="w", justify="left",
        ).pack(fill=tk.X, padx=8, pady=6)

    def destroy(self) -> None:
        try:
            self.frame.destroy()
        except tk.TclError:
            pass
