#!/usr/bin/env python3
"""Loki-style CSV tool — drag & drop, auto-detect, column copy."""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from csv_reader.config import AppConfig, LokiProduct, load_config, save_config
from csv_reader.copy_engine import build_copy_payload
from csv_reader.detector import DetectionResult, detect_product
from csv_reader.loki_mapper import map_data
from csv_reader.reader import CsvData, read_csv_file

# ── Theme (Loki Manual — gọn, sáng) ───────────────────────────────────────
BG = "#f8f9fb"
CARD = "#ffffff"
BORDER = "#d8dee9"
TEXT = "#1e293b"
MUTED = "#64748b"
ACCENT = "#2563eb"
ACCENT_LIGHT = "#eff6ff"
SUCCESS = "#059669"
WARN = "#d97706"
FONT = ("Segoe UI", 9)
FONT_BOLD = ("Segoe UI", 9, "bold")
FONT_TITLE = ("Segoe UI", 10, "bold")


def _setup_style(root: tk.Tk) -> ttk.Style:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    root.configure(bg=BG)
    style.configure(".", background=BG, foreground=TEXT, font=FONT)
    style.configure("Card.TFrame", background=CARD)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Card.TLabel", background=CARD, foreground=TEXT)
    style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=(FONT[0], 8))
    style.configure("CardMuted.TLabel", background=CARD, foreground=MUTED, font=(FONT[0], 8))
    style.configure("Title.TLabel", background=CARD, font=FONT_TITLE)
    style.configure("TButton", padding=(8, 4))
    style.configure("Accent.TButton", padding=(10, 5), font=FONT_BOLD)
    style.configure("TCombobox", padding=4)
    style.configure("Treeview", rowheight=22, font=(FONT[0], 8))
    style.configure("Treeview.Heading", font=FONT_BOLD, padding=3)
    return style


def _enable_drag_drop(widget: tk.Misc, callback) -> None:
    if sys.platform == "win32":
        try:
            import windnd

            def _on_drop(files):
                if files:
                    path = files[0]
                    if isinstance(path, bytes):
                        path = path.decode("utf-8", errors="replace")
                    callback(Path(path))

            windnd.hook_dropfiles(widget, func=_on_drop)
            return
        except ImportError:
            pass
    # Linux / fallback: label only
    pass


class LokiCsvApp:
    def __init__(self, root: tk.Tk, initial_file: str | None = None) -> None:
        self.root = root
        self.root.title("Loki CSV")
        self.root.geometry("820x480")
        self.root.minsize(680, 400)

        _setup_style(root)
        self.config = load_config()
        self.data: CsvData | None = None
        self.detection: DetectionResult | None = None
        self.mapped_columns: list[str] = []
        self.mapped_rows: list[list[str]] = []

        self._build_ui()
        self._refresh_product_list()

        if initial_file:
            self._load_file(Path(initial_file))

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)
        main.columnconfigure(0, weight=0, minsize=250)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        # ── Left: Manual panel ──
        left = ttk.Frame(main, style="Card.TFrame", padding=12)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.columnconfigure(0, weight=1)

        ttk.Label(left, text="Manual", style="Title.TLabel").grid(row=0, column=0, sticky="w")

        ttk.Label(left, text="Product", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=(12, 4))
        self.product_var = tk.StringVar()
        self.product_combo = ttk.Combobox(
            left, textvariable=self.product_var, state="readonly", width=28,
        )
        self.product_combo.grid(row=2, column=0, sticky="ew")
        self.product_combo.bind("<<ComboboxSelected>>", lambda _: self._on_product_change())

        self.note_var = tk.StringVar(value="Kéo thả file CSV để bắt đầu")
        note = tk.Label(
            left, textvariable=self.note_var, bg=ACCENT_LIGHT, fg=ACCENT,
            font=(FONT[0], 8), padx=8, pady=6, anchor="w", justify=tk.LEFT, wraplength=220,
        )
        note.grid(row=3, column=0, sticky="ew", pady=(10, 0))

        # Drop zone
        self.drop_frame = tk.Frame(left, bg=CARD, highlightbackground=ACCENT,
                                   highlightthickness=2, highlightcolor=ACCENT)
        self.drop_frame.grid(row=4, column=0, sticky="ew", pady=(14, 0))
        self.drop_label = tk.Label(
            self.drop_frame, text="Kéo thả CSV\nhoặc click để chọn",
            bg=CARD, fg=MUTED, font=FONT, pady=28, cursor="hand2",
        )
        self.drop_label.pack(fill=tk.X)
        self.drop_label.bind("<Button-1>", lambda _: self._open_file())
        self.drop_frame.bind("<Button-1>", lambda _: self._open_file())
        _enable_drag_drop(self.drop_frame, self._load_file)
        _enable_drag_drop(self.drop_label, self._load_file)

        self.detect_var = tk.StringVar(value="")
        ttk.Label(left, textvariable=self.detect_var, style="CardMuted.TLabel").grid(
            row=5, column=0, sticky="w", pady=(8, 0),
        )

        self.auto_var = tk.BooleanVar(value=self.config.auto_copy)
        ttk.Checkbutton(
            left, text="Tự động copy khi nhận diện",
            variable=self.auto_var, command=self._save_prefs,
        ).grid(row=6, column=0, sticky="w", pady=(8, 0))

        btn_row = ttk.Frame(left, style="Card.TFrame")
        btn_row.grid(row=7, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(btn_row, text="Copy", style="Accent.TButton", command=self._copy_all).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="Mở file", command=self._open_file).pack(side=tk.LEFT, padx=(6, 0))

        # ── Right: Preview table ──
        right = ttk.Frame(main, style="Card.TFrame", padding=12)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        hdr = ttk.Frame(right, style="Card.TFrame")
        hdr.grid(row=0, column=0, sticky="ew")
        ttk.Label(hdr, text="Gợi ý cột copy", style="Title.TLabel").pack(side=tk.LEFT)
        self.file_var = tk.StringVar(value="")
        ttk.Label(hdr, textvariable=self.file_var, style="CardMuted.TLabel").pack(side=tk.RIGHT)

        table_wrap = ttk.Frame(right, style="Card.TFrame")
        table_wrap.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        table_wrap.rowconfigure(0, weight=1)
        table_wrap.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(table_wrap, show="headings", selectmode="extended")
        vsb = ttk.Scrollbar(table_wrap, orient=tk.VERTICAL, command=self.tree.yview)
        hsb = ttk.Scrollbar(table_wrap, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        self.tree.bind("<Double-1>", lambda _: self._copy_selected())

        self.status_var = tk.StringVar(value="Sẵn sàng — thả file CSV vào vùng bên trái")
        ttk.Label(right, textvariable=self.status_var, style="CardMuted.TLabel").grid(
            row=2, column=0, sticky="w", pady=(6, 0),
        )

        self._products_by_name: dict[str, LokiProduct] = {}

    def _refresh_product_list(self) -> None:
        names = [p.name for p in self.config.products]
        self._products_by_name = {p.name: p for p in self.config.products}
        self.product_combo["values"] = names

    def _selected_product(self) -> LokiProduct | None:
        name = self.product_var.get()
        return self._products_by_name.get(name)

    def _on_product_change(self) -> None:
        product = self._selected_product()
        if product:
            self.note_var.set("Cột copy:\n" + " · ".join(product.columns))
            if self.data:
                self._apply_mapping(product)

    def _open_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Chọn CSV",
            filetypes=[("CSV", "*.csv"), ("TSV", "*.tsv"), ("All", "*.*")],
        )
        if path:
            self._load_file(Path(path))

    def _load_file(self, path: Path) -> None:
        if not str(path).lower().endswith((".csv", ".tsv", ".txt")):
            messagebox.showwarning("File không hợp lệ", "Chỉ hỗ trợ file .csv / .tsv")
            return
        try:
            data = read_csv_file(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Lỗi đọc file", str(exc))
            return

        self.data = data
        self.file_var.set(f"{data.path.name}  ·  {data.row_count} dòng")
        self.drop_label.configure(text=data.path.name, fg=TEXT)
        self.status_var.set(f"Đã đọc {data.row_count} dòng · {data.encoding}")

        self.detection = detect_product(data, self.config)
        if self.detection.product:
            self.product_var.set(self.detection.product.name)
            self.detect_var.set(
                f"Nhận diện: {self.detection.product.name} ({self.detection.confidence}) — {self.detection.reason}"
            )
            self.note_var.set("Cột copy:\n" + " · ".join(self.detection.product.columns))
            self._apply_mapping(self.detection.product)
            if self.config.auto_copy and self.detection.is_confident:
                self._copy_all(silent=True)
        else:
            self.detect_var.set("Không tự nhận diện — chọn Product thủ công")
            if self.config.products:
                self.product_var.set(self.config.products[0].name)
                self._apply_mapping(self.config.products[0])

    def _apply_mapping(self, product: LokiProduct) -> None:
        if not self.data:
            return
        self.mapped_columns, self.mapped_rows = map_data(self.data, product)
        self._fill_table(self.mapped_columns, self.mapped_rows)

    def _fill_table(self, headers: list[str], rows: list[list[str]]) -> None:
        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = headers
        for col in headers:
            self.tree.heading(col, text=col)
            w = 160 if "artwork" in col.lower() or "http" in col.lower() else 90
            self.tree.column(col, width=w, minwidth=50, stretch=True)
        for i, row in enumerate(rows):
            padded = row + [""] * (len(headers) - len(row))
            tag = "even" if i % 2 == 0 else "odd"
            self.tree.insert("", tk.END, values=padded[: len(headers)], tags=(tag,))
        self.tree.tag_configure("even", background="#f8fafc")
        self.tree.tag_configure("odd", background=CARD)

    def _copy_to_clipboard(self, text: str, msg: str, *, silent: bool = False) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()
        if not silent:
            messagebox.showinfo("Đã copy", msg)
        else:
            self.status_var.set(msg)

    def _copy_all(self, silent: bool = False) -> None:
        product = self._selected_product()
        if not self.data or not product:
            if not silent:
                messagebox.showwarning("Chưa sẵn sàng", "Mở file CSV và chọn sản phẩm trước.")
            return
        payload = build_copy_payload(self.data, product, self.config)
        self._copy_to_clipboard(
            payload,
            f"Đã copy {self.data.row_count} dòng · {product.name}",
            silent=silent,
        )

    def _copy_selected(self) -> None:
        product = self._selected_product()
        if not self.data or not product:
            return
        selected = self.tree.selection()
        if not selected:
            return
        items = self.tree.get_children()
        indices = [items.index(s) for s in selected]
        payload = build_copy_payload(self.data, product, self.config, row_indices=indices)
        self._copy_to_clipboard(payload, f"Đã copy {len(indices)} dòng")

    def _save_prefs(self) -> None:
        self.config.auto_copy = self.auto_var.get()
        save_config(self.config)


def run_gui(initial_file: str | None = None) -> None:
    root = tk.Tk()
    LokiCsvApp(root, initial_file=initial_file)
    root.mainloop()


if __name__ == "__main__":
    run_gui()