"""CSV Loki panel — giao diện đồng bộ ACC2019."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)

from acc2019_core import (
    COLOR_ACCENT_PS,
    COLOR_BG,
    COLOR_CARD,
    COLOR_MUTED,
    COLOR_SUCCESS,
    COLOR_TEXT,
)
from csv_reader.config import CONFIG_PATH, load_config, save_config
from csv_reader.copy_engine import build_copy_payload
from csv_reader.detector import detect_product
from csv_reader.loki_mapper import map_data
from csv_reader.reader import CsvData, read_csv_file
from modules.csv_services import (
    add_recent_file,
    compare_csv_files,
    download_artworks,
    format_compare_report,
    get_recent_files,
    record_csv_processed,
)

COLOR_CSV = "#a78bfa"
CONSOLE_BG = "#07070a"
CONSOLE_FG = "#a9b7c6"


class CsvLokiPanel:
    def __init__(self, parent: tk.Misc, app) -> None:
        self.parent = parent
        self.app = app
        self.config = load_config()
        self.data: CsvData | None = None
        self.detection = None
        self._products: dict[str, object] = {}
        self.drop_zone: tk.Label | None = None
        self._build()

    def _build(self) -> None:
        pad = 4
        self.parent.columnconfigure(0, weight=1)
        self._json_visible = True

        # ── Header row ──
        hdr = tk.Frame(self.parent, bg=COLOR_BG)
        hdr.grid(row=0, column=0, sticky="ew", padx=pad, pady=(1, 0))
        hdr.columnconfigure(1, weight=1)

        tk.Label(hdr, text="Manual", font=("Segoe UI", 8, "bold"), fg=COLOR_CSV, bg=COLOR_BG).grid(
            row=0, column=0, sticky="w",
        )
        tk.Label(hdr, text="Product", font=("Segoe UI", 7), fg=COLOR_MUTED, bg=COLOR_BG).grid(
            row=1, column=0, columnspan=2, sticky="w",
        )

        self.product_var = tk.StringVar()
        self.product_combo = ttk.Combobox(
            hdr, textvariable=self.product_var, state="readonly", font=("Segoe UI", 8),
        )
        self.product_combo.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(1, 0))
        self.product_combo.bind("<<ComboboxSelected>>", lambda _: self._on_product_change())

        btn_grp = tk.Frame(hdr, bg=COLOR_BG)
        btn_grp.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(2, 0))

        for text, cmd, color in (
            ("Tải ảnh", self._download_artworks, "#f472b6"),
            ("So sánh", self._compare_csv, "#38bdf8"),
            ("Gần đây", self._open_recent_menu, "#fbbf24"),
            ("Copy", self._copy_all, COLOR_CSV),
            ("Mở CSV", self._open_file, COLOR_ACCENT_PS),
            ("Tải lại", self._reload_config, COLOR_SUCCESS),
            ("Sửa JSON", self._open_config_file, COLOR_MUTED),
        ):
            tk.Button(
                btn_grp, text=text, font=("Segoe UI", 7, "bold"),
                fg=COLOR_TEXT, bg=COLOR_CARD, activebackground=COLOR_CARD,
                highlightbackground=color, highlightthickness=1,
                bd=0, padx=4, pady=1, cursor="hand2", command=cmd,
            ).pack(side=tk.RIGHT, padx=(2, 0))

        # ── Info + drop ──
        mid = tk.Frame(self.parent, bg=COLOR_BG)
        mid.grid(row=1, column=0, sticky="ew", padx=pad, pady=(2, 0))

        self.note_var = tk.StringVar(value="Kéo thả CSV → tự nhận diện sản phẩm")
        tk.Label(
            mid, textvariable=self.note_var, font=("Segoe UI", 7),
            fg=COLOR_CSV, bg=COLOR_CARD, padx=4, pady=1, anchor="w",
        ).pack(fill=tk.X)

        self.drop_zone = tk.Label(
            mid,
            text="⬇  Kéo thả file .csv vào đây",
            font=("Segoe UI", 7, "bold"),
            fg=COLOR_CSV, bg=COLOR_BG,
            highlightbackground="#2a2540", highlightthickness=1,
            pady=4, cursor="hand2",
        )
        self.drop_zone.pack(fill=tk.X, pady=(2, 0))
        self.drop_zone.bind("<Button-1>", lambda _: self._open_file())

        self.detect_var = tk.StringVar(value="")
        tk.Label(mid, textvariable=self.detect_var, font=("Segoe UI", 7), fg=COLOR_MUTED, bg=COLOR_BG).pack(
            anchor="w",
        )

        # ── JSON preview (ô nhỏ đọc config sản phẩm) ──
        json_wrap = tk.Frame(self.parent, bg=COLOR_BG)
        json_wrap.grid(row=2, column=0, sticky="ew", padx=pad, pady=(2, 0))
        json_wrap.columnconfigure(0, weight=1)

        json_hdr = tk.Frame(json_wrap, bg=COLOR_CARD, highlightbackground="#252538", highlightthickness=1)
        json_hdr.grid(row=0, column=0, sticky="ew")
        json_hdr.columnconfigure(0, weight=1)

        self._json_toggle_lbl = tk.Label(
            json_hdr, text="▾ JSON sản phẩm", font=("Segoe UI", 7, "bold"),
            fg=COLOR_CSV, bg=COLOR_CARD, padx=6, pady=3, cursor="hand2",
        )
        self._json_toggle_lbl.grid(row=0, column=0, sticky="w")
        self._json_toggle_lbl.bind("<Button-1>", lambda _: self._toggle_json_box())

        tk.Button(
            json_hdr, text="Chọn file", font=("Segoe UI", 6),
            fg=COLOR_MUTED, bg=COLOR_CARD, activebackground=COLOR_CARD,
            bd=0, padx=4, cursor="hand2", command=self._pick_json_file,
        ).grid(row=0, column=1, padx=4)

        self._json_path_var = tk.StringVar(value=str(CONFIG_PATH))
        tk.Label(
            json_hdr, textvariable=self._json_path_var,
            font=("Consolas", 6), fg="#55556a", bg=COLOR_CARD,
        ).grid(row=0, column=2, sticky="e", padx=(0, 6))

        self._json_frame = tk.Frame(json_wrap, bg=COLOR_CARD, highlightbackground="#252538", highlightthickness=1)
        self._json_frame.grid(row=1, column=0, sticky="ew", pady=(0, 0))

        self._json_preview = scrolledtext.ScrolledText(
            self._json_frame,
            height=4,
            bg=CONSOLE_BG,
            fg=CONSOLE_FG,
            font=("Consolas", 7),
            bd=0,
            highlightthickness=0,
            wrap=tk.NONE,
            state=tk.DISABLED,
        )
        self._json_preview.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        # ── Table ──
        table_wrap = tk.Frame(self.parent, bg=COLOR_CARD, highlightbackground="#252538", highlightthickness=1)
        table_wrap.grid(row=3, column=0, sticky="nsew", padx=pad, pady=(6, 4))
        table_wrap.rowconfigure(0, weight=1)
        table_wrap.columnconfigure(0, weight=1)

        style = ttk.Style()
        style.configure(
            "Csv.Treeview", background=CONSOLE_BG, fieldbackground=CONSOLE_BG,
            foreground=CONSOLE_FG, rowheight=18, font=("Consolas", 8),
        )
        style.configure("Csv.Treeview.Heading", font=("Segoe UI", 7, "bold"), padding=2)

        self.tree = ttk.Treeview(table_wrap, show="headings", style="Csv.Treeview", height=6)
        vsb = ttk.Scrollbar(table_wrap, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        foot = tk.Frame(self.parent, bg=COLOR_BG)
        foot.grid(row=4, column=0, sticky="ew", padx=pad, pady=(0, 2))
        self.auto_var = tk.BooleanVar(value=self.config.auto_copy)
        tk.Checkbutton(
            foot, text="Tự động copy khi nhận diện", variable=self.auto_var,
            font=("Segoe UI", 7), fg=COLOR_MUTED, bg=COLOR_BG,
            selectcolor=COLOR_CARD, activebackground=COLOR_BG, command=self._save_prefs,
        ).pack(side=tk.LEFT)

        self._refresh_products()
        if self.config.products:
            self.product_var.set(self.config.products[0].name)
        self._update_json_preview()

    def _refresh_products(self) -> None:
        self._products = {p.name: p for p in self.config.products}
        self.product_combo["values"] = list(self._products.keys())

    def _toggle_json_box(self) -> None:
        self._json_visible = not self._json_visible
        if self._json_visible:
            self._json_frame.grid()
            self._json_toggle_lbl.configure(text="▾ JSON sản phẩm")
        else:
            self._json_frame.grid_remove()
            self._json_toggle_lbl.configure(text="▸ JSON sản phẩm")

    def _read_json_file_text(self, path: Path) -> str:
        if not path.is_file():
            return f"// Không tìm thấy file:\n// {path}"
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            return f"// Lỗi đọc file: {exc}"

    def _update_json_preview(self, *, full_file: bool = False) -> None:
        path = Path(self._json_path_var.get())
        text = ""

        if full_file or not self.product_var.get():
            raw = self._read_json_file_text(path)
            if len(raw) > 4000:
                text = raw[:4000] + "\n\n// ... (file dài, dùng 'Sửa JSON' để xem đủ)"
            else:
                text = raw
        else:
            product = self._selected()
            if product:
                text = json.dumps(product.to_dict(), ensure_ascii=False, indent=2)
            else:
                text = self._read_json_file_text(path)

        self._json_preview.configure(state=tk.NORMAL)
        self._json_preview.delete("1.0", tk.END)
        self._json_preview.insert("1.0", text)
        self._json_preview.configure(state=tk.DISABLED)

    def _pick_json_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Chọn file products JSON",
            initialdir=str(CONFIG_PATH.parent),
            filetypes=[("JSON", "*.json"), ("All", "*.*")],
        )
        if not path:
            return
        self._json_path_var.set(path)
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            from csv_reader.config import AppConfig

            self.config = AppConfig.from_dict(data)
            save_config(self.config)
            self._refresh_products()
            if self.config.products:
                self.product_var.set(self.config.products[0].name)
            self._update_json_preview(full_file=False)
            self._log(f"CSV: đã nạp {Path(path).name} · {len(self.config.products)} sản phẩm", "accent")
        except (OSError, json.JSONDecodeError, KeyError) as exc:
            self._update_json_preview(full_file=True)
            self._log(f"CSV: lỗi đọc JSON — {exc}", "danger")

    def _selected(self):
        return self._products.get(self.product_var.get())

    def _log(self, msg: str, tag: str = "normal") -> None:
        if hasattr(self.app, "log"):
            self.app.log(msg, tag)

    def _reload_config(self) -> None:
        self.config = load_config()
        self._json_path_var.set(str(CONFIG_PATH))
        self.auto_var.set(self.config.auto_copy)
        self._refresh_products()
        n = len(self.config.products)
        self._update_json_preview()
        self._log(f"CSV: đã tải lại config · {n} sản phẩm", "accent")
        if self.data and self.data.rows:
            self.detection = detect_product(self.data, self.config)
            if self.detection.product:
                self.product_var.set(self.detection.product.name)
                self._apply_mapping(self.detection.product)
                self._update_json_preview()

    def _open_config_file(self) -> None:
        path = str(CONFIG_PATH)
        if not CONFIG_PATH.is_file():
            messagebox.showinfo("Config", f"File chưa tồn tại:\n{path}")
            return
        try:
            os.startfile(path)  # noqa: S606 — Windows only
            self._log(f"CSV: mở {CONFIG_PATH.name}", "accent")
        except Exception:
            subprocess.Popen(["notepad.exe", path])

    def setup_drop(self) -> None:
        if not self.drop_zone:
            return
        try:
            import windnd

            def _on_drop(files):
                if not files:
                    return
                path = files[0]
                if isinstance(path, bytes):
                    path = path.decode("utf-8", errors="ignore")
                self.load_file(Path(path))

            windnd.hook_dropfiles(self.drop_zone, func=_on_drop)
            self._log("CSV Loki: kéo thả sẵn sàng", "accent")
        except ImportError:
            self._log("CSV: pip install windnd để kéo thả", "danger")

    def _open_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Chọn CSV",
            filetypes=[("CSV", "*.csv"), ("TSV", "*.tsv"), ("All", "*.*")],
        )
        if path:
            self.load_file(Path(path))

    def load_file(self, path: Path) -> None:
        if path.suffix.lower() not in (".csv", ".tsv", ".txt"):
            self._log("CSV: chỉ hỗ trợ .csv / .tsv", "danger")
            return
        try:
            self.data = read_csv_file(path)
        except (OSError, ValueError) as exc:
            self._log(f"CSV lỗi: {exc}", "danger")
            return

        if self.drop_zone:
            self.drop_zone.configure(text=f"✓ {path.name}", fg=COLOR_SUCCESS)

        self.detection = detect_product(self.data, self.config)
        if self.detection.product:
            self.product_var.set(self.detection.product.name)
            self.detect_var.set(f"→ {self.detection.product.name} ({self.detection.confidence})")
            self.note_var.set(" · ".join(self.detection.product.columns))
            self._apply_mapping(self.detection.product)
            self._update_json_preview()
            self._log(f"CSV → {self.detection.product.name} · {self.data.row_count} dòng", "success")
            if self.config.auto_copy and self.detection.is_confident:
                self._copy_all(silent=True)
        else:
            self.detect_var.set("Chưa nhận diện — chọn Product")
            if self.config.products:
                self.product_var.set(self.config.products[0].name)
                self._apply_mapping(self.config.products[0])
            self._log("CSV: không tự nhận diện", "danger")

        add_recent_file(path)
        if self.detection and self.detection.product:
            record_csv_processed(path, self.detection.product.name, self.data.row_count)
        if hasattr(self.app, "refresh_daily_stats"):
            self.app.refresh_daily_stats()

        if hasattr(self.app, "log_action"):
            self.app.log_action("CSV Loki", "ĐỌC FILE", path.name)

    def _open_recent_menu(self) -> None:
        recent = get_recent_files()
        if not recent:
            messagebox.showinfo("Gần đây", "Chưa có file CSV nào được mở.")
            return
        menu = tk.Menu(self.parent, tearoff=0)
        for p in recent:
            label = Path(p).name
            menu.add_command(label=label, command=lambda fp=p: self.load_file(Path(fp)))
        try:
            menu.tk_popup(self.parent.winfo_rootx() + 80, self.parent.winfo_rooty() + 60)
        finally:
            menu.grab_release()

    def _compare_csv(self) -> None:
        if not self.data:
            messagebox.showinfo("So sánh", "Mở file CSV A trước (file hiện tại).")
            return
        path_b = filedialog.askopenfilename(
            title="Chọn CSV B để so sánh",
            filetypes=[("CSV", "*.csv"), ("TSV", "*.tsv"), ("All", "*.*")],
        )
        if not path_b:
            return
        try:
            result = compare_csv_files(self.data.path, path_b, self.config)
            report = format_compare_report(result)
        except (OSError, ValueError) as exc:
            self._log(f"So sánh lỗi: {exc}", "danger")
            return

        win = tk.Toplevel(self.app.root)
        win.title("So sánh CSV")
        win.geometry("460x320")
        win.configure(bg=COLOR_BG)
        txt = scrolledtext.ScrolledText(
            win, bg=CONSOLE_BG, fg=CONSOLE_FG, font=("Consolas", 8), wrap=tk.WORD,
        )
        txt.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        txt.insert("1.0", report)
        txt.configure(state=tk.DISABLED)
        self._log("CSV: đã so sánh 2 file", "accent")

    def _selected_row_indices(self) -> list[int] | None:
        selected = self.tree.selection()
        if not selected:
            return None
        items = self.tree.get_children()
        return [items.index(s) for s in selected]

    def _download_artworks(self) -> None:
        if not self.data:
            self._log("CSV: mở file trước khi tải ảnh", "danger")
            return

        default_dir = Path.home() / "Desktop" / "ACC2019_Artwork"
        out = filedialog.askdirectory(
            title="Thư mục lưu ảnh (tên = Item ID)",
            initialdir=str(default_dir) if default_dir.parent.exists() else str(Path.home() / "Desktop"),
        )
        if not out:
            return

        indices = self._selected_row_indices()
        label = f"{len(indices)} dòng chọn" if indices else f"{self.data.row_count} dòng"
        self._log(f"CSV: đang tải ảnh · {label} → {out}", "accent")
        self.app.root.update()

        results = download_artworks(self.data, out, row_indices=indices)
        ok = sum(1 for r in results if r.get("ok"))
        fail = len(results) - ok
        self._log(f"CSV: tải xong {ok}/{len(results)} ảnh · {fail} lỗi", "success" if ok else "danger")
        for r in results:
            if r.get("ok"):
                self._log(f"  ✓ {r['item_id']} → {Path(r['path']).name}", "success")
            else:
                self._log(f"  ✗ {r.get('item_id', '?')}: {r.get('error')}", "danger")

        if ok and hasattr(self.app, "log_action"):
            self.app.log_action("CSV Loki", "TẢI ẢNH", f"{ok} file → {Path(out).name}")

        if ok:
            try:
                os.startfile(out)  # noqa: S606
            except Exception:
                pass

    def _on_product_change(self) -> None:
        product = self._selected()
        self._update_json_preview()
        if product and self.data:
            self.note_var.set(" · ".join(product.columns))
            self._apply_mapping(product)
        elif product:
            self.note_var.set(" · ".join(product.columns))

    def _apply_mapping(self, product) -> None:
        if not self.data:
            return
        cols, rows = map_data(self.data, product)
        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = cols
        for col in cols:
            self.tree.heading(col, text=col)
            w = 120 if "artwork" in col.lower() else 68
            self.tree.column(col, width=w, minwidth=36, stretch=True)
        for row in rows:
            padded = row + [""] * (len(cols) - len(row))
            self.tree.insert("", tk.END, values=padded[: len(cols)])

    def _save_prefs(self) -> None:
        self.config.auto_copy = self.auto_var.get()
        save_config(self.config)
        self._log("CSV: đã lưu tùy chọn auto copy", "accent")

    def _copy_all(self, silent: bool = False) -> None:
        product = self._selected()
        if not self.data or not product:
            if not silent:
                self._log("CSV: chưa có file / sản phẩm", "danger")
            return
        payload = build_copy_payload(self.data, product, self.config)
        self.app.root.clipboard_clear()
        self.app.root.clipboard_append(payload)
        self.app.root.update()
        msg = f"Copy {self.data.row_count} dòng · {product.name}"
        self._log(msg, "success")
        if not silent:
            messagebox.showinfo("Copy", msg)