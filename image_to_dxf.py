import os
import sys
import subprocess

try:
    import cv2
    import ezdxf
    from PIL import Image, ImageTk
except ImportError:
    print("[*] Installing required libraries (opencv-python, ezdxf, pillow)...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "opencv-python", "ezdxf", "pillow"])
    import cv2
    import ezdxf
    from PIL import Image, ImageTk

try:
    import windnd
    HAS_WINDND = True
except ImportError:
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "windnd"])
        import windnd
        HAS_WINDND = True
    except Exception:
        HAS_WINDND = False

import tkinter as tk
from tkinter import filedialog, messagebox

from dxf_convert import extract_smooth_polylines, physical_size_mm, read_image_rgba, resolve_dpi
from modules.dxf_preview import (
    confirm_dxf_preview,
    desktop_dxf_path,
    render_cut_preview,
    render_source_preview,
    save_polylines_dxf,
)

COLOR_BG = "#0c0c14"
COLOR_CARD = "#141424"
COLOR_TEXT = "#ffffff"
COLOR_MUTED = "#82829c"
COLOR_ACCENT = "#00d2ff"
COLOR_SUCCESS = "#00e676"
COLOR_DANGER = "#ff1744"


class ImageToDXFApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ACC2019 — DXF 1:1 + Review")
        self.root.geometry("560x520")
        self.root.configure(bg=COLOR_BG)
        self.root.minsize(520, 480)

        self.image_path = None
        self.dpi = (300, 300)
        self.width_px = 0
        self.height_px = 0
        self._img_bgra = None
        self._polylines = None
        self._photo_src = None
        self._photo_cut = None

        self.setup_ui()
        self.setup_drag_and_drop()

    def setup_ui(self):
        pad = 12

        tk.Label(
            self.root, text="Xuất DXF 1:1", font=("Segoe UI", 10, "bold"),
            fg=COLOR_ACCENT, bg=COLOR_BG,
        ).pack(anchor="w", padx=pad, pady=(10, 4))

        self.drop_box = tk.Label(
            self.root, text="Kéo thả ảnh silhouette\nhoặc nhấp chọn",
            font=("Segoe UI", 8, "bold"), fg=COLOR_ACCENT, bg=COLOR_CARD,
            bd=1, relief="solid", highlightbackground="#252538", highlightthickness=1,
            height=2, cursor="hand2",
        )
        self.drop_box.pack(fill=tk.X, padx=pad, pady=(0, 8))
        self.drop_box.bind("<Button-1>", self.select_image)

        info = tk.Frame(self.root, bg=COLOR_CARD, highlightbackground="#252538", highlightthickness=1)
        info.pack(fill=tk.X, padx=pad, pady=(0, 8))
        self.lbl_file_name = tk.Label(info, text="Chưa chọn ảnh", font=("Segoe UI", 8, "bold"),
                                      fg=COLOR_TEXT, bg=COLOR_CARD, anchor="w")
        self.lbl_file_name.pack(fill=tk.X, padx=10, pady=(6, 2))
        self.lbl_dimensions = tk.Label(info, text="0 × 0 px", font=("Segoe UI", 7),
                                       fg=COLOR_MUTED, bg=COLOR_CARD, anchor="w")
        self.lbl_dimensions.pack(fill=tk.X, padx=10)
        self.lbl_physical_size = tk.Label(info, text="-- mm", font=("Segoe UI", 8, "bold"),
                                          fg=COLOR_SUCCESS, bg=COLOR_CARD, anchor="w")
        self.lbl_physical_size.pack(fill=tk.X, padx=10, pady=(0, 6))

        prev = tk.Frame(self.root, bg=COLOR_BG)
        prev.pack(fill=tk.BOTH, expand=True, padx=pad)
        prev.columnconfigure(0, weight=1)
        prev.columnconfigure(1, weight=1)
        prev.rowconfigure(1, weight=1)

        tk.Label(prev, text="Ảnh gốc", font=("Segoe UI", 7, "bold"), fg=COLOR_MUTED, bg=COLOR_BG).grid(row=0, column=0)
        tk.Label(prev, text="Đường cắt", font=("Segoe UI", 7, "bold"), fg=COLOR_SUCCESS, bg=COLOR_BG).grid(row=0, column=1)

        self.lbl_src = tk.Label(prev, text="—", bg=COLOR_CARD, fg=COLOR_MUTED, width=28, height=12)
        self.lbl_src.grid(row=1, column=0, sticky="nsew", padx=(0, 4), pady=4)
        self.lbl_cut = tk.Label(prev, text="—", bg=COLOR_CARD, fg=COLOR_MUTED, width=28, height=12)
        self.lbl_cut.grid(row=1, column=1, sticky="nsew", padx=(4, 0), pady=4)

        btn_row = tk.Frame(self.root, bg=COLOR_BG)
        btn_row.pack(fill=tk.X, padx=pad, pady=(4, 0))
        self.btn_preview = tk.Button(
            btn_row, text="Phân tích & xem cắt", font=("Segoe UI", 8),
            bg=COLOR_CARD, fg=COLOR_ACCENT, bd=0, padx=10, pady=5,
            state=tk.DISABLED, command=self.analyze_preview,
        )
        self.btn_preview.pack(side=tk.LEFT)
        self.btn_convert = tk.Button(
            btn_row, text="Lưu DXF ra Desktop", font=("Segoe UI", 8, "bold"),
            bg=COLOR_ACCENT, fg="#000", bd=0, padx=10, pady=5,
            state=tk.DISABLED, command=self.convert_to_dxf,
        )
        self.btn_convert.pack(side=tk.RIGHT)

        self.console = tk.Label(self.root, text="Sẵn sàng.", font=("Consolas", 7),
                                fg=COLOR_MUTED, bg=COLOR_BG, anchor="w")
        self.console.pack(fill=tk.X, padx=pad, pady=(6, 8))

    def log(self, text, color=COLOR_MUTED):
        self.console.config(text=text, fg=color)

    def setup_drag_and_drop(self):
        if HAS_WINDND:
            def handle_drop(files):
                if files:
                    fp = files[0]
                    if isinstance(fp, bytes):
                        fp = fp.decode("utf-8", errors="ignore")
                    self.load_image_info(fp)
                    self.analyze_preview()
            windnd.hook_dropfiles(self.root, func=handle_drop)
            self.log("Kéo thả ảnh → tự phân tích & xem đường cắt.")
        else:
            self.log("Nhấp để chọn ảnh.")

    def select_image(self, event=None):
        fp = filedialog.askopenfilename(
            title="Chọn ảnh silhouette",
            filetypes=[("Image", "*.png;*.jpg;*.jpeg;*.bmp;*.tif;*.tiff")],
        )
        if fp:
            self.load_image_info(fp)

    def load_image_info(self, file_path):
        self.image_path = file_path
        self._polylines = None
        self.btn_convert.config(state=tk.DISABLED)
        try:
            self._img_bgra, w, h, dpi = read_image_rgba(file_path)
            self.width_px, self.height_px, self.dpi = w, h, dpi
            _, wmm, hmm = physical_size_mm(w, h, dpi)

            self.lbl_file_name.config(text=os.path.basename(file_path))
            self.lbl_dimensions.config(text=f"{w} × {h} px  ·  {int(dpi[0])} DPI")
            self.lbl_physical_size.config(text=f"{wmm:.1f} × {hmm:.1f} mm")

            src = render_source_preview(self._img_bgra)
            self._photo_src = ImageTk.PhotoImage(src)
            self.lbl_src.configure(image=self._photo_src, text="")
            self.lbl_cut.configure(image="", text="Chưa phân tích")

            self.drop_box.config(text=f"✓ {os.path.basename(file_path)}", fg=COLOR_TEXT)
            self.btn_preview.config(state=tk.NORMAL)
            self.log("Đã load ảnh. Bấm 'Phân tích' hoặc 'Lưu DXF'.", COLOR_SUCCESS)
        except Exception as e:
            messagebox.showerror("Lỗi", str(e))
            self.log(f"Lỗi: {e}", COLOR_DANGER)

    def analyze_preview(self):
        if not self._img_bgra:
            return
        self.log("Đang phân tích đường biên...", COLOR_ACCENT)
        self.root.update()
        try:
            polys = extract_smooth_polylines(
                self._img_bgra, self.width_px, self.height_px, self.dpi,
            )
            self._polylines = polys
            if not polys:
                self.log("Không thấy đường biên.", COLOR_DANGER)
                messagebox.showerror("Lỗi", "Không tìm thấy đường biên!")
                return

            mm_per_px, _, _ = physical_size_mm(self.width_px, self.height_px, self.dpi)
            cut, match_pct = render_cut_preview(
                self._img_bgra, polys, self.width_px, self.height_px, mm_per_px,
            )
            self._photo_cut = ImageTk.PhotoImage(cut)
            self.lbl_cut.configure(image=self._photo_cut, text="")
            self.btn_convert.config(state=tk.NORMAL)
            match_color = COLOR_SUCCESS if match_pct >= 98.0 else COLOR_DANGER
            self.log(
                f"Sẵn sàng: {len(polys)} contour · khớp {match_pct:.1f}% "
                f"(đỏ = lệch) — kiểm tra panel phải.",
                match_color,
            )
        except Exception as e:
            self.log(f"Lỗi: {e}", COLOR_DANGER)

    def convert_to_dxf(self):
        if not self.image_path or not self._img_bgra:
            return
        if not self._polylines:
            self.analyze_preview()
            if not self._polylines:
                return

        if not confirm_dxf_preview(
            self.root, self.image_path, self._img_bgra, self._polylines,
            self.width_px, self.height_px, self.dpi,
        ):
            self.log("Đã hủy — không lưu DXF.", COLOR_DANGER)
            return

        try:
            dxf_path = desktop_dxf_path(self.image_path)
            n = save_polylines_dxf(self._polylines, dxf_path)
            _, wmm, hmm = physical_size_mm(self.width_px, self.height_px, self.dpi)
            self.log(f"Đã lưu {os.path.basename(dxf_path)} · {n} contour", COLOR_SUCCESS)
            messagebox.showinfo(
                "Thành công",
                f"Đã lưu DXF ra Desktop!\n\n{os.path.basename(dxf_path)}\n"
                f"{wmm:.1f} × {hmm:.1f} mm  ·  {n} đường cắt",
            )
        except Exception as e:
            messagebox.showerror("Lỗi", str(e))
            self.log(f"Lỗi: {e}", COLOR_DANGER)


if __name__ == "__main__":
    initial_file = sys.argv[1] if len(sys.argv) > 1 else None
    root = tk.Tk()
    app = ImageToDXFApp(root)
    if initial_file and os.path.exists(initial_file):
        app.load_image_info(initial_file)
        app.analyze_preview()
    root.mainloop()