"""ACC2019 core — Adobe CC 2019 manager business logic."""

import ctypes
import os
import shutil
import subprocess
import sys
import threading
import time
import winreg

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

VERSION = "1.1.0"
AUTHOR = "Antigravity Pair"

COLOR_BG = "#0c0c14"
COLOR_CARD = "#141424"
COLOR_TEXT = "#ffffff"
COLOR_MUTED = "#82829c"
COLOR_ACCENT_PS = "#00d2ff"
COLOR_ACCENT_AI = "#ff9d00"
COLOR_SUCCESS = "#00e676"
COLOR_DANGER = "#ff1744"
COLOR_BUTTON_HOVER = "#23233c"

PS_EXE_PATH = r"C:\Program Files\Adobe\Adobe Photoshop CC 2019\Photoshop.exe"
AI_EXE_PATH = (
    r"C:\Program Files\Adobe\Adobe Illustrator CC 2019"
    r"\Support Files\Contents\Windows\Illustrator.exe"
)
PS_INSTALL_DIR = r"C:\Program Files\Adobe\Adobe Photoshop CC 2019"
AI_INSTALL_DIR = r"C:\Program Files\Adobe\Adobe Illustrator CC 2019"
ADOBE_COMMON_SETUP = (
    r"C:\Program Files (x86)\Common Files\Adobe\Adobe Desktop Common\HDBox\Setup.exe"
)
ADOBE_COMMON_UNINSTALLER = (
    r"C:\Program Files (x86)\Common Files\Adobe"
    r"\Adobe Desktop Common\HDBox\Uninstaller.exe"
)
# Metadata gỡ cài HDBox (CC 2019 pre-activated)
_ADOBE_PRODUCT_META = {
    "PHSP": {
        "exe": PS_EXE_PATH,
        "install_dir": PS_INSTALL_DIR,
        "product_version": "20.0.9",
        "product_adobe_code": "{PHSP-20.0.9-64-ADBEADBEADBEADBEADBEA}",
        "product_name": "Photoshop CC",
        "shortcuts": (
            r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Adobe Photoshop CC 2019.lnk",
            r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Adobe Photoshop 2019.lnk",
        ),
        "user_data": (
            r"%APPDATA%\Adobe\Adobe Photoshop CC 2019",
            r"%APPDATA%\Adobe\Photoshop\20.0",
            r"%LOCALAPPDATA%\Adobe\Photoshop",
        ),
    },
    "ILST": {
        "exe": AI_EXE_PATH,
        "install_dir": AI_INSTALL_DIR,
        "product_version": "23.1",
        "product_adobe_code": "{ILST-23.1-64-ADBEADBEADBEADBEADBEADB}",
        "product_name": "Illustrator CC",
        "shortcuts": (
            r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Adobe Illustrator 2019.lnk",
            r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Adobe Illustrator CC 2019.lnk",
        ),
        "user_data": (
            r"%APPDATA%\Adobe\Adobe Illustrator 23 Settings",
            r"%APPDATA%\Adobe\Adobe Illustrator CC 2019",
            r"%LOCALAPPDATA%\Adobe\Adobe Illustrator 23 Settings",
        ),
    },
}

_README_TEXT = (
    "=== HƯỚNG DẪN NHẬP ACTIONS & SCRIPTS TỰ ĐỘNG ===\n\n"
    "1. Hãy copy các file Actions (.atn) của bạn vào thư mục 'Actions'.\n"
    "2. Hãy copy các file Scripts (.jsx hoặc .js) của bạn vào thư mục 'Scripts'.\n"
    "3. Nhấn nút 'Nhập Actions/Scripts ⚡' trên giao diện phần mềm.\n\n"
    "Phần mềm sẽ tự động copy toàn bộ vào thư mục cài đặt của Photoshop "
    "và tự động mở Photoshop để nạp (load) các Actions này vào bảng điều khiển Actions của bạn.\n"
)


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


class AdobeManagerApp:
    """Core Adobe CC 2019 manager — UI shell; acc2019.ACC2019App overrides setup_ui."""

    def __init__(self, root):
        self.root = root
        self.root.title("Adobe CC 2019 Quick Manager")
        self.root.geometry("480x600")
        self.root.minsize(460, 560)
        self.root.configure(bg=COLOR_BG)
        self.root.resizable(True, True)

        if getattr(sys, "frozen", False):
            self.base_dir = os.path.dirname(sys.executable)
        else:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.history_path = os.path.join(self.base_dir, "adobe_history.txt")

        self.ps_installer = os.path.join(
            self.base_dir,
            "Adobe Photoshop CC 2019 v20.0.9.28674 (x64) Multilingual Pre-Activated [FileCR]",
            "Adobe Photoshop CC 2019 v20.0.9.28674 (x64) Multilingual Pre-Activated [FileCR]",
            "Set-up.exe",
        )
        self.ai_installer = os.path.join(
            self.base_dir,
            "Adobe Illustrator CC 2019 v23.1.0.670 Pre-Activated [FileCR]",
            "Adobe Illustrator CC 2019 v23.1.0.670 Pre-Activated [FileCR]",
            "Setup (Pre-activated)",
            "Set-up.exe",
        )

        self.is_ps_installed = os.path.exists(PS_EXE_PATH)
        self.is_ai_installed = os.path.exists(AI_EXE_PATH)
        self.is_ps_running = False
        self.is_ai_running = False
        self.installing_ps = False
        self.installing_ai = False
        self.ps_action_type = None
        self.ai_action_type = None

        imports_dir = os.path.join(self.base_dir, "Photoshop_Imports")
        actions_dir = os.path.join(imports_dir, "Actions")
        scripts_dir = os.path.join(imports_dir, "Scripts")
        os.makedirs(actions_dir, exist_ok=True)
        os.makedirs(scripts_dir, exist_ok=True)

        readme_path = os.path.join(imports_dir, "HuongDan.txt")
        if not os.path.exists(readme_path):
            try:
                with open(readme_path, "w", encoding="utf-8") as f:
                    f.write(_README_TEXT)
            except Exception:
                pass

        self.setup_ui()
        from modules.produce_queue import ProduceQueue

        self.produce_queue = ProduceQueue(self)
        self.update_ps_ui()
        self.update_ai_ui()
        if not getattr(self, "_defer_drag_drop", False):
            self.root.after(0, self.setup_drag_and_drop)
        self.log("Khởi động hệ thống quản lý...")
        self._preload_patch_template()
        self.check_installer_files()

        self.stop_monitoring = False
        self.monitor_thread = threading.Thread(target=self.status_monitor_loop, daemon=True)
        self.monitor_thread.start()

    # ------------------------------------------------------------------ logging
    def log(self, message, tag="normal"):
        """Show message on terminal console."""
        if not hasattr(self, "console") or self.console is None:
            print(f"[log] {message}")
            return
        timestamp = time.strftime("[%H:%M:%S]")
        self.console.config(state=tk.NORMAL)
        self.console.insert(tk.END, f"{timestamp} {message}\n", tag)
        self.console.see(tk.END)
        self.console.config(state=tk.DISABLED)

    def log_action(self, app_name, action, detail=""):
        """Log actions both to console and write to persistent history file."""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"{app_name} | {action}"
        if detail:
            log_msg += f" ({detail})"

        tag = "normal"
        if "THÀNH CÔNG" in action or "thành công" in action:
            tag = "success"
        elif (
            "THẤT BẠI" in action
            or "LỖI" in action
            or "lỗi" in action
            or "không" in action
        ):
            tag = "danger"

        self.log(log_msg, tag)

        try:
            if not os.path.exists(self.history_path):
                with open(self.history_path, "w", encoding="utf-8") as f:
                    f.write("=== LỊCH SỬ HOẠT ĐỘNG ADOBE QUICK MANAGER ===\n\n")
            with open(self.history_path, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {log_msg}\n")
        except Exception as e:
            self.log(f"Lỗi ghi lịch sử: {e}")

    def open_history_file(self):
        """Open the history text file in Notepad."""
        try:
            if not os.path.exists(self.history_path):
                with open(self.history_path, "w", encoding="utf-8") as f:
                    f.write("=== LỊCH SỬ HOẠT ĐỘNG ADOBE QUICK MANAGER ===\n\n")
            os.startfile(self.history_path)
            self.log("Đã mở file lịch sử hoạt động.")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể mở file lịch sử: {e}")

    # ------------------------------------------------------------------ process control
    # Main app only — dùng khi bật/tắt nhanh (không đụng shared Adobe)
    _PS_MAIN = ("Photoshop.exe",)
    _AI_MAIN = ("Illustrator.exe",)
    # Helper riêng app — kill khi gỡ cài / đóng triệt để
    _PS_HELPERS = (
        "Photoshop.exe",
        "Adobe Desktop Service.exe",
        "AdobeNotificationClient.exe",
    )
    _AI_HELPERS = (
        "Illustrator.exe",
        "AISniffer.exe",
        "AIGPUSniffer.exe",
        "AISafeModeLauncher.exe",
        "CRWindowsClientService.exe",
        "CRLogTransport.exe",
        "LogTransport2.exe",
        "Adobe Desktop Service.exe",
        "AdobeNotificationClient.exe",
    )
    # Shared — chỉ kill khi gỡ cài hoặc "Đóng PS+AI" (tránh làm sập app kia)
    _ADOBE_SHARED = (
        "AdobeIPCBroker.exe",
        "CEPHtmlEngine.exe",
        "CCXProcess.exe",
        "CCLibrary.exe",
        "CoreSync.exe",
        "Adobe Crash Processor.exe",
        "AdobeCEFHelper.exe",
        "AdobeUpdateService.exe",
        "armsvc.exe",
        "AGSService.exe",
        "AdobeGCClient.exe",
        "Set-up.exe",
        "Setup.exe",
        "Uninstaller.exe",
        "Adobe Installer.exe",
    )

    def force_close_all_processes(self, *, notify: bool = True, background: bool = True):
        """Force close both Photoshop and Illustrator. UI không bị đơ."""
        if background:
            if getattr(self, "_closing_all", False):
                return
            self._closing_all = True
            kill_btn_text = None
            if hasattr(self, "btn_kill_all"):
                try:
                    kill_btn_text = self.btn_kill_all.cget("text")
                    self.btn_kill_all.config(state=tk.DISABLED, text="Đang đóng…")
                except tk.TclError:
                    pass

            def _worker():
                try:
                    self.force_close_app_processes("PHSP", deep=True, log=True)
                    self.force_close_app_processes("ILST", deep=True, log=False)
                    self.is_ps_running = False
                    self.is_ai_running = False
                    self.root.after(0, self.update_ps_ui)
                    self.root.after(0, self.update_ai_ui)
                    self.log_action(
                        "Hệ thống",
                        "Đã đóng tất cả các tiến trình Photoshop & Illustrator đang chạy.",
                    )
                    if notify:
                        self.root.after(
                            0,
                            lambda: messagebox.showinfo(
                                "Thông báo",
                                "Đã đóng toàn bộ tiến trình liên quan đến Photoshop & Illustrator!",
                            ),
                        )
                finally:
                    self._closing_all = False
                    def _restore():
                        if hasattr(self, "btn_kill_all"):
                            try:
                                kw = {"state": tk.NORMAL}
                                if kill_btn_text:
                                    kw["text"] = kill_btn_text
                                self.btn_kill_all.config(**kw)
                            except tk.TclError:
                                pass
                    self.root.after(0, _restore)

            threading.Thread(target=_worker, daemon=True).start()
            return

        self.force_close_app_processes("PHSP", deep=True, log=True)
        self.force_close_app_processes("ILST", deep=True, log=False)
        self.is_ps_running = False
        self.is_ai_running = False
        self.update_ps_ui()
        self.update_ai_ui()
        self.log_action(
            "Hệ thống", "Đã đóng tất cả các tiến trình Photoshop & Illustrator đang chạy."
        )
        if notify:
            messagebox.showinfo(
                "Thông báo",
                "Đã đóng toàn bộ tiến trình liên quan đến Photoshop & Illustrator!",
            )

    def _process_names_for(self, sap_code: str, *, deep: bool = False) -> list[str]:
        if sap_code == "PHSP":
            names = list(self._PS_HELPERS if deep else self._PS_MAIN)
        elif sap_code == "ILST":
            names = list(self._AI_HELPERS if deep else self._AI_MAIN)
        else:
            return []
        if deep:
            names.extend(self._ADOBE_SHARED)
        # unique, giữ thứ tự
        seen = set()
        out = []
        for n in names:
            k = n.lower()
            if k not in seen:
                seen.add(k)
                out.append(n)
        return out

    def _app_label(self, sap_code: str) -> str:
        if sap_code == "PHSP":
            return "Photoshop CC 2019"
        if sap_code == "ILST":
            return "Illustrator CC 2019"
        return sap_code

    def _kill_by_name(self, process_names: list[str], *, tree: bool = True) -> None:
        """taskkill + TerminateProcess Win32. Không sleep — caller tự wait."""
        if not process_names:
            return
        for proc in process_names:
            try:
                cmd = ["taskkill", "/F", "/IM", proc]
                if tree:
                    cmd.insert(2, "/T")
                subprocess.run(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except Exception:
                pass
        self._win32_terminate(process_names)

    def _win32_terminate(self, process_names: list[str]) -> None:
        try:
            import ctypes.wintypes

            class PROCESSENTRY32(ctypes.Structure):
                _fields_ = [
                    ("dwSize", ctypes.wintypes.DWORD),
                    ("cntUsage", ctypes.wintypes.DWORD),
                    ("th32ProcessID", ctypes.wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_void_p),
                    ("th32ModuleID", ctypes.wintypes.DWORD),
                    ("cntThreads", ctypes.wintypes.DWORD),
                    ("th32ParentProcessID", ctypes.wintypes.DWORD),
                    ("pcPriClassBase", ctypes.wintypes.LONG),
                    ("dwFlags", ctypes.wintypes.DWORD),
                    ("szExeFile", ctypes.c_char * 260),
                ]

            TH32CS_SNAPPROCESS = 2
            PROCESS_TERMINATE = 1
            kernel32 = ctypes.windll.kernel32
            h_process_snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
            if h_process_snap == -1:
                return

            pe32 = PROCESSENTRY32()
            pe32.dwSize = ctypes.sizeof(PROCESSENTRY32)
            kill_names = {p.lower() for p in process_names}

            if kernel32.Process32First(h_process_snap, ctypes.byref(pe32)):
                while True:
                    exe_name = pe32.szExeFile.decode("mbcs", errors="ignore").lower()
                    if exe_name in kill_names:
                        pid = pe32.th32ProcessID
                        h_proc = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
                        if h_proc:
                            kernel32.TerminateProcess(h_proc, 99)
                            kernel32.CloseHandle(h_proc)
                    if not kernel32.Process32Next(h_process_snap, ctypes.byref(pe32)):
                        break
            kernel32.CloseHandle(h_process_snap)
        except Exception as e:
            self.log(f"Lỗi khi force-kill Win32: {e}")

    def _any_running(self, process_names: list[str] | tuple[str, ...]) -> bool:
        if not process_names:
            return False
        running = self._list_running_names()
        return any(n.lower() in running for n in process_names)

    def _list_running_names(self) -> set[str]:
        """Snapshot tên process đang chạy (lowercase) — nhanh hơn tasklist."""
        names: set[str] = set()
        try:
            import ctypes.wintypes

            class PROCESSENTRY32(ctypes.Structure):
                _fields_ = [
                    ("dwSize", ctypes.wintypes.DWORD),
                    ("cntUsage", ctypes.wintypes.DWORD),
                    ("th32ProcessID", ctypes.wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_void_p),
                    ("th32ModuleID", ctypes.wintypes.DWORD),
                    ("cntThreads", ctypes.wintypes.DWORD),
                    ("th32ParentProcessID", ctypes.wintypes.DWORD),
                    ("pcPriClassBase", ctypes.wintypes.LONG),
                    ("dwFlags", ctypes.wintypes.DWORD),
                    ("szExeFile", ctypes.c_char * 260),
                ]

            TH32CS_SNAPPROCESS = 2
            kernel32 = ctypes.windll.kernel32
            h = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
            if h == -1:
                return names
            pe32 = PROCESSENTRY32()
            pe32.dwSize = ctypes.sizeof(PROCESSENTRY32)
            if kernel32.Process32First(h, ctypes.byref(pe32)):
                while True:
                    exe = pe32.szExeFile.decode("mbcs", errors="ignore").lower()
                    if exe:
                        names.add(exe)
                    if not kernel32.Process32Next(h, ctypes.byref(pe32)):
                        break
            kernel32.CloseHandle(h)
        except Exception:
            pass
        return names

    def wait_processes_gone(
        self,
        process_names: list[str] | tuple[str, ...],
        timeout: float = 8.0,
        poll: float = 0.2,
    ) -> bool:
        """Đợi process tắt hết. True nếu sạch trong timeout."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self._any_running(process_names):
                return True
            time.sleep(poll)
        return not self._any_running(process_names)

    def force_close_app_processes(
        self,
        sap_code: str,
        *,
        deep: bool = False,
        log: bool = True,
        wait_timeout: float = 4.0,
        rounds: int = 3,
    ) -> bool:
        """
        Đóng PS hoặc AI.
        deep=False: chỉ app chính (toggle Mở/Đóng mượt, không đụng app kia).
        deep=True: helpers + shared Adobe (dùng khi gỡ cài / Đóng PS+AI).
        Trả về True nếu process chính đã tắt.
        """
        main = list(self._PS_MAIN if sap_code == "PHSP" else self._AI_MAIN)
        targets = self._process_names_for(sap_code, deep=deep)
        if not targets:
            return True

        app_name = self._app_label(sap_code)
        if log:
            mode = "triệt để" if deep else "nhanh"
            self.log_action(app_name, f"Đang đóng tiến trình ({mode})...")

        for attempt in range(max(1, rounds)):
            if not self._any_running(targets if deep else main):
                break
            self._kill_by_name(targets, tree=True)
            if self.wait_processes_gone(main, timeout=wait_timeout / rounds):
                break
            # round sau: luôn deep-ish để gỡ file lock
            if attempt + 1 < rounds:
                extra = list(targets)
                if deep:
                    extra.extend(self._ADOBE_SHARED)
                self._kill_by_name(extra, tree=True)

        gone = not self._any_running(main)
        if sap_code == "PHSP":
            self.is_ps_running = not gone
        elif sap_code == "ILST":
            self.is_ai_running = not gone
        return gone

    def is_process_running(self, process_name: str) -> bool:
        """Kiểm tra process nhanh qua Toolhelp (không spawn tasklist)."""
        if not process_name:
            return False
        return process_name.lower() in self._list_running_names()

    def refresh_data(self):
        """Force rescan installer files and registry status."""
        self.log("Đang quét lại tệp cài đặt và trạng thái...")
        self.check_installer_files()
        self.is_ps_installed = os.path.exists(PS_EXE_PATH)
        self.is_ai_installed = os.path.exists(AI_EXE_PATH)
        self.update_ps_ui()
        self.update_ai_ui()
        self.log("Đã làm mới dữ liệu và trạng thái ứng dụng.")

    def _preload_patch_template(self):
        try:
            from patch_crop import load_crop_config

            cfg = load_crop_config(base_dir=self.base_dir)
            self.log(
                f"Template patch: {cfg['layer_name']} | vùng cắt "
                f"{cfg['abs_crop'][2] - cfg['abs_crop'][0]}x"
                f"{cfg['abs_crop'][3] - cfg['abs_crop'][1]}px",
                "accent",
            )
        except Exception as e:
            self.log(f"Lưu ý: chưa load được template patch - {e}", "danger")

    # ------------------------------------------------------------------ UI helpers
    def create_tab_button(self, parent, tab_id, text, accent=COLOR_ACCENT_PS):
        btn = tk.Button(
            parent,
            text=text,
            font=("Segoe UI", 8, "bold"),
            bg=COLOR_CARD,
            fg=COLOR_MUTED,
            activebackground=COLOR_CARD,
            activeforeground=accent,
            bd=0,
            padx=8,
            pady=4,
            cursor="hand2",
            command=lambda: self.show_tab(tab_id),
        )
        self.tab_buttons[tab_id] = {"btn": btn, "accent": accent}
        return btn

    def show_tab(self, tab_id):
        for tid, frame in self.tab_frames.items():
            if tid == tab_id:
                frame.pack(fill=tk.BOTH, expand=True)
            else:
                frame.pack_forget()

        for tid, meta in self.tab_buttons.items():
            accent = meta["accent"]
            if tid == tab_id:
                meta["btn"].config(fg=accent, highlightbackground=accent, highlightthickness=1)
            else:
                meta["btn"].config(fg=COLOR_MUTED, highlightthickness=0)

        self.active_tab = tab_id

    def create_drop_zone(self, parent, text, fg, border_color, command, wraplength=170, height=2):
        zone = tk.Label(
            parent,
            text=text,
            font=("Segoe UI", 7, "bold"),
            fg=fg,
            bg=COLOR_BG,
            bd=1,
            relief="solid",
            highlightbackground=border_color,
            highlightthickness=1,
            height=height,
            cursor="hand2",
            wraplength=wraplength,
            justify="center",
        )
        zone.bind("<Button-1>", command)
        return zone

    def create_app_card(self, parent, app_name, accent):
        card = tk.Frame(parent, bg=COLOR_CARD, highlightbackground="#252538", highlightthickness=1)
        card.pack(fill=tk.X, pady=(0, 6))

        header = tk.Frame(card, bg=COLOR_CARD)
        header.pack(fill=tk.X, padx=8, pady=(6, 2))

        tk.Label(
            header,
            text=app_name,
            font=("Segoe UI", 8, "bold"),
            fg=accent,
            bg=COLOR_CARD,
        ).pack(side=tk.LEFT)

        status = tk.Label(
            header,
            text="Đang kiểm tra...",
            font=("Segoe UI", 7, "bold"),
            fg=COLOR_MUTED,
            bg=COLOR_CARD,
        )
        status.pack(side=tk.RIGHT)

        actions = tk.Frame(card, bg=COLOR_CARD)
        actions.pack(fill=tk.X, padx=8, pady=(0, 4))

        btn_install = self.create_flat_button(actions, text="Cài", bg=accent, padx=8, pady=3)
        btn_install.pack(side=tk.LEFT, padx=(0, 4))

        btn_uninstall = self.create_flat_button(actions, text="Gỡ", bg=COLOR_DANGER, padx=8, pady=3)
        btn_uninstall.pack(side=tk.LEFT, padx=(0, 4))

        btn_open = self.create_flat_button(
            actions,
            text="Mở",
            bg=COLOR_CARD,
            fg=COLOR_TEXT,
            border_color="#444",
            padx=8,
            pady=3,
        )
        btn_open.pack(side=tk.RIGHT)

        progress_canvas = tk.Canvas(card, height=4, bg="#0d0d16", bd=0, highlightthickness=0)
        progress_canvas.pack(fill=tk.X, padx=8, pady=(0, 6))
        progress_rect = progress_canvas.create_rectangle(0, 0, 0, 4, fill=accent, width=0)

        return {
            "card": card,
            "status": status,
            "btn_install": btn_install,
            "btn_uninstall": btn_uninstall,
            "btn_open": btn_open,
            "progress_canvas": progress_canvas,
            "progress_rect": progress_rect,
        }

    def create_flat_button(
        self,
        parent,
        text,
        bg,
        fg="#ffffff",
        border_color=None,
        padx=8,
        pady=3,
        command=None,
    ):
        hover_bg = COLOR_BUTTON_HOVER if bg == COLOR_CARD else self.lighten_color(bg)
        btn = tk.Button(
            parent,
            text=text,
            font=("Segoe UI", 8, "bold"),
            bg=bg,
            fg=fg,
            activebackground=hover_bg,
            activeforeground=fg,
            bd=0,
            padx=padx,
            pady=pady,
            cursor="hand2",
            command=command,
        )

        def on_enter(_event=None):
            if btn["state"] != tk.DISABLED:
                btn.config(bg=hover_bg)

        def on_leave(_event=None):
            if btn["state"] != tk.DISABLED:
                btn.config(bg=bg)

        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)
        if border_color:
            btn.config(highlightbackground=border_color, highlightthickness=1)
        return btn

    def lighten_color(self, hex_color):
        try:
            hex_color = hex_color.lstrip("#")
            rgb = tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
            new_rgb = tuple(min(255, int(c * 1.2)) for c in rgb)
            return "#{:02x}{:02x}{:02x}".format(*new_rgb)
        except Exception:
            return hex_color

    def setup_ui(self):
        """Default compact tab UI (produce / adobe / system) — overridden by ACC2019App."""
        pad = 12

        header_frame = tk.Frame(self.root, bg=COLOR_BG)
        header_frame.pack(fill=tk.X, padx=pad, pady=(8, 4))

        tk.Label(
            header_frame,
            text="Adobe CC 2019 Manager",
            font=("Segoe UI", 10, "bold"),
            fg=COLOR_TEXT,
            bg=COLOR_BG,
        ).pack(side=tk.LEFT)

        self.btn_history = self.create_flat_button(
            header_frame,
            text="Lịch sử",
            bg=COLOR_CARD,
            fg=COLOR_ACCENT_PS,
            border_color="#333",
            padx=8,
            pady=2,
            command=self.open_history_file,
        )
        self.btn_history.pack(side=tk.RIGHT)

        tab_bar = tk.Frame(self.root, bg=COLOR_BG)
        tab_bar.pack(fill=tk.X, padx=pad, pady=(0, 4))

        self.tab_buttons = {}
        self.tab_frames = {}
        self.active_tab = "produce"

        self.create_tab_button(tab_bar, "produce", "Sản xuất", COLOR_SUCCESS).pack(
            side=tk.LEFT, padx=(0, 4)
        )
        self.create_tab_button(tab_bar, "adobe", "Adobe CC", COLOR_ACCENT_PS).pack(
            side=tk.LEFT, padx=(0, 4)
        )
        self.create_tab_button(tab_bar, "system", "Hệ thống", COLOR_MUTED).pack(side=tk.LEFT)

        content = tk.Frame(self.root, bg=COLOR_BG)
        content.pack(fill=tk.BOTH, expand=True, padx=pad, pady=0)

        # Tab Sản xuất
        produce_frame = tk.Frame(content, bg=COLOR_BG)
        self.tab_frames["produce"] = produce_frame

        drop_row = tk.Frame(produce_frame, bg=COLOR_BG)
        drop_row.pack(fill=tk.X)
        for col in range(3):
            drop_row.columnconfigure(col, weight=1)

        patch_col = tk.Frame(
            drop_row, bg=COLOR_CARD, highlightbackground="#1a3a2a", highlightthickness=1
        )
        patch_col.grid(row=0, column=0, sticky="nsew", padx=(0, 3))
        tk.Label(
            patch_col,
            text="Cắt Patch GG",
            font=("Segoe UI", 8, "bold"),
            fg=COLOR_SUCCESS,
            bg=COLOR_CARD,
        ).pack(anchor="w", padx=8, pady=(6, 2))
        self.patch_drop_zone = self.create_drop_zone(
            patch_col,
            "Kéo thả\n4200×4800",
            COLOR_SUCCESS,
            "#1a3a2a",
            self.select_patch_image,
            wraplength=130,
        )
        self.patch_drop_zone.pack(fill=tk.X, padx=8, pady=(0, 8))

        dxf_col = tk.Frame(
            drop_row, bg=COLOR_CARD, highlightbackground="#252538", highlightthickness=1
        )
        dxf_col.grid(row=0, column=1, sticky="nsew", padx=3)
        tk.Label(
            dxf_col,
            text="Xuất DXF 1:1",
            font=("Segoe UI", 8, "bold"),
            fg=COLOR_ACCENT_PS,
            bg=COLOR_CARD,
        ).pack(anchor="w", padx=8, pady=(6, 2))
        self.dxf_drop_zone = self.create_drop_zone(
            dxf_col,
            "Kéo thả\nsilhouette",
            COLOR_ACCENT_PS,
            "#252538",
            self.select_dxf_image,
            wraplength=130,
        )
        self.dxf_drop_zone.pack(fill=tk.X, padx=8, pady=(0, 8))

        spot_col = tk.Frame(
            drop_row, bg=COLOR_CARD, highlightbackground="#3a1a1a", highlightthickness=1
        )
        spot_col.grid(row=0, column=2, sticky="nsew", padx=(3, 0))
        tk.Label(
            spot_col,
            text="Đổ màu W1",
            font=("Segoe UI", 8, "bold"),
            fg=COLOR_DANGER,
            bg=COLOR_CARD,
        ).pack(anchor="w", padx=8, pady=(6, 2))
        self.spot_drop_zone = self.create_drop_zone(
            spot_col,
            "Kéo thả ảnh\n→ .tif W1 đỏ",
            COLOR_DANGER,
            "#3a1a1a",
            self.select_spot_color_image,
            wraplength=130,
        )
        self.spot_drop_zone.pack(fill=tk.X, padx=8, pady=(0, 8))

        tk.Label(
            produce_frame,
            text="Spot W1: chỉ phủ vật thể, nền trong suốt, giữ nguyên kích thước → .tif",
            font=("Segoe UI", 7),
            fg=COLOR_MUTED,
            bg=COLOR_BG,
            anchor="w",
        ).pack(fill=tk.X, pady=(4, 0))

        # Tab Adobe CC
        adobe_frame = tk.Frame(content, bg=COLOR_BG)
        self.tab_frames["adobe"] = adobe_frame

        adobe_toolbar = tk.Frame(adobe_frame, bg=COLOR_BG)
        adobe_toolbar.pack(fill=tk.X, pady=(0, 6))

        self.btn_refresh = self.create_flat_button(
            adobe_toolbar,
            text="Làm mới",
            bg=COLOR_CARD,
            fg=COLOR_SUCCESS,
            border_color="#1a3a2a",
            padx=8,
            pady=3,
            command=self.refresh_data,
        )
        self.btn_refresh.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_kill_all = self.create_flat_button(
            adobe_toolbar,
            text="Đóng PS + AI",
            bg=COLOR_CARD,
            fg=COLOR_DANGER,
            border_color="#441111",
            padx=8,
            pady=3,
            command=self.force_close_all_processes,
        )
        self.btn_kill_all.pack(side=tk.LEFT)

        ps = self.create_app_card(adobe_frame, "Photoshop CC 2019", COLOR_ACCENT_PS)
        self.ps_card = ps["card"]
        self.ps_status_label = ps["status"]
        self.btn_install_ps = ps["btn_install"]
        self.btn_uninstall_ps = ps["btn_uninstall"]
        self.btn_open_ps = ps["btn_open"]
        self.ps_progress_canvas = ps["progress_canvas"]
        self.ps_progress_rect = ps["progress_rect"]
        self.btn_install_ps.config(command=self.start_install_ps)
        self.btn_uninstall_ps.config(command=self.start_uninstall_ps)
        self.btn_open_ps.config(command=self.toggle_photoshop)

        self.btn_import_ps = self.create_flat_button(
            ps["card"],
            text="Nhập Actions/Scripts",
            bg=COLOR_CARD,
            fg=COLOR_ACCENT_PS,
            border_color="#00d2ff",
            padx=8,
            pady=3,
            command=self.import_ps_presets,
        )
        self.btn_import_ps.pack(fill=tk.X, padx=8, pady=(0, 6))

        ai = self.create_app_card(adobe_frame, "Illustrator CC 2019", COLOR_ACCENT_AI)
        self.ai_card = ai["card"]
        self.ai_status_label = ai["status"]
        self.btn_install_ai = ai["btn_install"]
        self.btn_uninstall_ai = ai["btn_uninstall"]
        self.btn_open_ai = ai["btn_open"]
        self.ai_progress_canvas = ai["progress_canvas"]
        self.ai_progress_rect = ai["progress_rect"]
        self.btn_install_ai.config(command=self.start_install_ai)
        self.btn_uninstall_ai.config(command=self.start_uninstall_ai)
        self.btn_open_ai.config(command=self.toggle_illustrator)

        # Tab Hệ thống
        system_frame = tk.Frame(content, bg=COLOR_BG)
        self.tab_frames["system"] = system_frame

        sys_grid = tk.Frame(system_frame, bg=COLOR_BG)
        sys_grid.pack(fill=tk.X)
        sys_grid.columnconfigure(0, weight=1)
        sys_grid.columnconfigure(1, weight=1)

        self.btn_clean = self.create_flat_button(
            sys_grid,
            text="Dọn tàn dư Adobe",
            bg=COLOR_CARD,
            fg=COLOR_ACCENT_PS,
            border_color="#252538",
            padx=8,
            pady=6,
            command=self.clean_adobe_remnants,
        )
        self.btn_clean.grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=(0, 4))

        self.btn_disable_services = self.create_flat_button(
            sys_grid,
            text="Tắt dịch vụ ngầm",
            bg=COLOR_CARD,
            fg=COLOR_ACCENT_AI,
            border_color="#252538",
            padx=8,
            pady=6,
            command=self.disable_adobe_services,
        )
        self.btn_disable_services.grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=(0, 4))

        self.btn_dxf_converter = self.create_flat_button(
            system_frame,
            text="Mở tool DXF riêng",
            bg=COLOR_CARD,
            fg=COLOR_TEXT,
            border_color="#252538",
            padx=8,
            pady=6,
            command=self.open_dxf_converter,
        )
        self.btn_dxf_converter.pack(fill=tk.X, pady=(0, 4))

        tk.Label(
            system_frame,
            text="Dọn dẹp chỉ nên chạy khi đã gỡ Adobe.\nTắt dịch vụ giúp giảm tải CPU/RAM.",
            font=("Segoe UI", 7),
            fg=COLOR_MUTED,
            bg=COLOR_BG,
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

        self.show_tab("produce")

        log_header = tk.Frame(self.root, bg=COLOR_BG)
        log_header.pack(fill=tk.X, padx=pad, pady=(4, 0))
        tk.Label(
            log_header,
            text="Nhật ký / Thông báo",
            font=("Segoe UI", 8, "bold"),
            fg=COLOR_MUTED,
            bg=COLOR_BG,
        ).pack(side=tk.LEFT)

        self.console = scrolledtext.ScrolledText(
            self.root,
            height=8,
            bg="#07070a",
            fg="#a9b7c6",
            insertbackground="white",
            font=("Consolas", 9),
            bd=0,
            highlightbackground="#222",
            highlightthickness=1,
        )
        self.console.pack(fill=tk.BOTH, padx=pad, pady=(2, 8), expand=True)
        self.console.tag_config("normal", foreground="#a9b7c6")
        self.console.tag_config("success", foreground=COLOR_SUCCESS)
        self.console.tag_config("danger", foreground=COLOR_DANGER)
        self.console.tag_config("accent", foreground=COLOR_ACCENT_PS)

    def check_installer_files(self):
        btn_ps = getattr(self, "btn_install_ps", None)
        btn_ai = getattr(self, "btn_install_ai", None)

        if os.path.exists(self.ps_installer):
            self.log("Tìm thấy bộ cài Photoshop.")
            if btn_ps and not self.is_ps_installed and not self.installing_ps:
                btn_ps.config(state=tk.NORMAL)
        else:
            self.log(f"LƯU Ý: Thiếu bộ cài Photoshop. (Đang tìm: {self.ps_installer})")
            if btn_ps:
                btn_ps.config(state=tk.DISABLED)

        if os.path.exists(self.ai_installer):
            self.log("Tìm thấy bộ cài Illustrator.")
            if btn_ai and not self.is_ai_installed and not self.installing_ai:
                btn_ai.config(state=tk.NORMAL)
        else:
            self.log(f"LƯU Ý: Thiếu bộ cài Illustrator. (Đang tìm: {self.ai_installer})")
            if btn_ai:
                btn_ai.config(state=tk.DISABLED)

    def status_monitor_loop(self):
        """Monitors install status on disk and process state in the background."""
        while not self.stop_monitoring:
            try:
                # Một snapshot cho cả PS + AI — rẻ hơn tasklist
                running = self._list_running_names()
                ps_running = "photoshop.exe" in running
                ai_running = "illustrator.exe" in running

                ps_exists = os.path.exists(PS_EXE_PATH)
                if ps_exists != self.is_ps_installed:
                    self.is_ps_installed = ps_exists
                    self.root.after(0, self.update_ps_ui)

                # Không ghi đè khi đang đóng/mở tay (tránh nhấp nháy nút)
                if not getattr(self, "_toggling_ps", False):
                    if ps_running != self.is_ps_running:
                        self.is_ps_running = ps_running
                        self.root.after(0, self.update_ps_ui)

                ai_exists = os.path.exists(AI_EXE_PATH)
                if ai_exists != self.is_ai_installed:
                    self.is_ai_installed = ai_exists
                    self.root.after(0, self.update_ai_ui)

                if not getattr(self, "_toggling_ai", False):
                    if ai_running != self.is_ai_running:
                        self.is_ai_running = ai_running
                        self.root.after(0, self.update_ai_ui)
            except Exception:
                pass

            time.sleep(1.0)

    def update_ps_ui(self):
        # Tab Adobe lazy-load — widget chưa tạo thì bỏ qua (build tab sẽ gọi lại)
        if not getattr(self, "ps_status_label", None):
            return
        if self.ps_action_type is not None:
            return

        if self.is_ps_installed:
            self.ps_status_label.config(text="ĐÃ CÀI ĐẶT", fg=COLOR_SUCCESS)
            if not self.installing_ps:
                self.btn_install_ps.config(state=tk.DISABLED)
                self.btn_uninstall_ps.config(state=tk.NORMAL)
                if getattr(self, "btn_import_ps", None):
                    self.btn_import_ps.config(state=tk.NORMAL)
                if self.is_ps_running:
                    self.btn_open_ps.config(text="Đóng", fg=COLOR_DANGER)
                else:
                    self.btn_open_ps.config(text="Mở", fg=COLOR_TEXT)
                self.btn_open_ps.config(state=tk.NORMAL)
        else:
            self.ps_status_label.config(text="CHƯA CÀI ĐẶT", fg=COLOR_DANGER)
            if not self.installing_ps:
                if os.path.exists(self.ps_installer):
                    self.btn_install_ps.config(state=tk.NORMAL)
                self.btn_uninstall_ps.config(state=tk.DISABLED)
                self.btn_open_ps.config(text="Mở", fg=COLOR_TEXT)
                self.btn_open_ps.config(state=tk.DISABLED)
                if getattr(self, "btn_import_ps", None):
                    self.btn_import_ps.config(state=tk.DISABLED)

    def update_ai_ui(self):
        if not getattr(self, "ai_status_label", None):
            return
        if self.ai_action_type is not None:
            return

        if self.is_ai_installed:
            self.ai_status_label.config(text="ĐÃ CÀI ĐẶT", fg=COLOR_SUCCESS)
            if not self.installing_ai:
                self.btn_install_ai.config(state=tk.DISABLED)
                self.btn_uninstall_ai.config(state=tk.NORMAL)
                if self.is_ai_running:
                    self.btn_open_ai.config(text="Đóng", fg=COLOR_DANGER)
                else:
                    self.btn_open_ai.config(text="Mở", fg=COLOR_TEXT)
                self.btn_open_ai.config(state=tk.NORMAL)
        else:
            self.ai_status_label.config(text="CHƯA CÀI ĐẶT", fg=COLOR_DANGER)
            if not self.installing_ai:
                if os.path.exists(self.ai_installer):
                    self.btn_install_ai.config(state=tk.NORMAL)
                self.btn_uninstall_ai.config(state=tk.DISABLED)
                self.btn_open_ai.config(text="Mở", fg=COLOR_TEXT)
                self.btn_open_ai.config(state=tk.DISABLED)

    def set_ps_progress(self, percent):
        if not getattr(self, "ps_progress_canvas", None):
            return
        width = self.ps_progress_canvas.winfo_width()
        if width <= 1:
            width = 380
        x1 = int(width * (percent / 100))
        self.ps_progress_canvas.coords(self.ps_progress_rect, 0, 0, x1, 4)
        if self.ps_action_type == "INSTALL":
            self.ps_status_label.config(text=f"ĐANG CÀI ĐẶT... {percent}%", fg=COLOR_ACCENT_PS)
        elif self.ps_action_type == "UNINSTALL":
            self.ps_status_label.config(text=f"ĐANG GỠ BỎ... {percent}%", fg=COLOR_DANGER)

    def set_ai_progress(self, percent):
        if not getattr(self, "ai_progress_canvas", None):
            return
        width = self.ai_progress_canvas.winfo_width()
        if width <= 1:
            width = 380
        x1 = int(width * (percent / 100))
        self.ai_progress_canvas.coords(self.ai_progress_rect, 0, 0, x1, 4)
        if self.ai_action_type == "INSTALL":
            self.ai_status_label.config(text=f"ĐANG CÀI ĐẶT... {percent}%", fg=COLOR_ACCENT_AI)
        elif self.ai_action_type == "UNINSTALL":
            self.ai_status_label.config(text=f"ĐANG GỠ BỎ... {percent}%", fg=COLOR_DANGER)

    def run_simulated_progress(self, app, duration=60):
        """Simulate progress from 0% to 95% over duration seconds."""
        steps = 100
        interval = duration / steps
        percent = 0.0

        while True:
            if app == "PS":
                is_active = self.ps_action_type is not None
            elif app == "AI":
                is_active = self.ai_action_type is not None
            else:
                is_active = False

            if not is_active:
                return

            if percent < 95:
                if percent < 50:
                    percent += 1
                elif percent < 80:
                    percent += 0.5
                else:
                    percent += 0.2

                p_display = int(percent)
                if app == "PS":
                    self.root.after(0, lambda p=p_display: self.set_ps_progress(p))
                elif app == "AI":
                    self.root.after(0, lambda p=p_display: self.set_ai_progress(p))

            time.sleep(interval)

    # ------------------------------------------------------------------ PS install/uninstall
    def start_install_ps(self):
        if self.installing_ps:
            return
        if not os.path.exists(self.ps_installer):
            messagebox.showerror("Lỗi", "Không tìm thấy file Set-up.exe của Photoshop!")
            return

        self.installing_ps = True
        self.btn_install_ps.config(state=tk.DISABLED)
        self.btn_uninstall_ps.config(state=tk.DISABLED)
        self.ps_status_label.config(text="ĐANG CÀI ĐẶT...", fg=COLOR_ACCENT_PS)
        self.log_action("Photoshop CC 2019", "Bắt đầu cài đặt ngầm")
        threading.Thread(target=self.install_ps_worker, daemon=True).start()

    def install_ps_worker(self):
        try:
            try:
                self.ps_action_type = "INSTALL"
                self.root.after(0, lambda: self.set_ps_progress(0))
                threading.Thread(target=self.run_simulated_progress, args=("PS", 90), daemon=True).start()

                ok = self._run_install_flow("PHSP", self.ps_installer)
                if ok:
                    self.root.after(0, lambda: self.set_ps_progress(100))
                    time.sleep(0.3)
                    self.is_ps_installed = True
                    self.log_action("Photoshop CC 2019", "Cài đặt THÀNH CÔNG")
                    self.root.after(
                        0,
                        lambda: messagebox.showinfo(
                            "Thông báo", "Photoshop CC 2019 đã được cài đặt thành công!"
                        ),
                    )
                else:
                    self.root.after(0, lambda: self.set_ps_progress(0))
                    self.log_action(
                        "Photoshop CC 2019", "Cài đặt THẤT BẠI", "Không tìm thấy file chạy"
                    )
                    self.root.after(
                        0,
                        lambda: messagebox.showerror("Lỗi", "Cài đặt Photoshop CC 2019 thất bại!"),
                    )
            except Exception as e:
                self.root.after(0, lambda: self.set_ps_progress(0))
                self.log_action("Photoshop CC 2019", "Cài đặt LỖI", str(e))
                self.root.after(
                    0,
                    lambda err=e: messagebox.showerror(
                        "Lỗi", f"Có lỗi xảy ra trong quá trình cài đặt: {err}"
                    ),
                )
        finally:
            self.installing_ps = False
            self.ps_action_type = None
            self.is_ps_installed = os.path.exists(PS_EXE_PATH)
            self.root.after(0, self.update_ps_ui)

    def start_uninstall_ps(self):
        if not messagebox.askyesno("Xác nhận", "Bạn có chắc muốn gỡ cài đặt nhanh Photoshop CC 2019?"):
            return

        self.installing_ps = True
        self.btn_install_ps.config(state=tk.DISABLED)
        self.btn_uninstall_ps.config(state=tk.DISABLED)
        self.ps_status_label.config(text="ĐANG GỠ BỎ...", fg=COLOR_DANGER)
        self.log_action("Photoshop CC 2019", "Bắt đầu gỡ cài đặt ngầm")
        threading.Thread(target=self.uninstall_ps_worker, daemon=True).start()

    def uninstall_ps_worker(self):
        try:
            try:
                self.ps_action_type = "UNINSTALL"
                self.root.after(0, lambda: self.set_ps_progress(0))
                threading.Thread(target=self.run_simulated_progress, args=("PS", 30), daemon=True).start()

                ok = self._run_uninstall_flow("PHSP")
                if ok:
                    self.root.after(0, lambda: self.set_ps_progress(100))
                    time.sleep(0.3)
                    self.log_action("Photoshop CC 2019", "Gỡ cài đặt THÀNH CÔNG")
                    self.root.after(
                        0,
                        lambda: messagebox.showinfo(
                            "Thông báo", "Photoshop CC 2019 đã được gỡ cài đặt thành công!"
                        ),
                    )
                else:
                    self.root.after(0, lambda: self.set_ps_progress(0))
                    self.log_action(
                        "Photoshop CC 2019", "Gỡ cài đặt THẤT BẠI", "Vẫn tồn tại file chạy"
                    )
                    self.root.after(
                        0,
                        lambda: messagebox.showerror(
                            "Lỗi",
                            "Gỡ cài đặt Photoshop CC 2019 thất bại!\n"
                            "Thử: Đóng PS+AI → Tắt dịch vụ → Gỡ lại.\n"
                            "(Cần chạy app với quyền Administrator nếu file bị khóa.)",
                        ),
                    )
            except Exception as e:
                self.root.after(0, lambda: self.set_ps_progress(0))
                self.log_action("Photoshop CC 2019", "Gỡ cài đặt LỖI", str(e))
                self.root.after(
                    0,
                    lambda err=e: messagebox.showerror(
                        "Lỗi", f"Có lỗi xảy ra trong quá trình gỡ cài đặt: {err}"
                    ),
                )
        finally:
            self.installing_ps = False
            self.ps_action_type = None
            self.is_ps_installed = os.path.exists(PS_EXE_PATH)
            self.is_ps_running = self.is_process_running("Photoshop.exe")
            self.root.after(0, self.update_ps_ui)

    def _build_official_uninstall_cmd(self, sap_code: str) -> str:
        """Lệnh Uninstaller.exe HDBox đầy đủ (kèm productAdobeCode)."""
        meta = _ADOBE_PRODUCT_META.get(sap_code)
        if not meta:
            return ""
        tool = ADOBE_COMMON_UNINSTALLER
        if not os.path.exists(tool):
            tool = ADOBE_COMMON_SETUP
        if not os.path.exists(tool):
            return ""
        return (
            f'"{tool}" --uninstall=1 --sapCode={sap_code} '
            f'--productVersion={meta["product_version"]} '
            f"--productPlatform=win64 "
            f'--productAdobeCode={meta["product_adobe_code"]} '
            f'--productName="{meta["product_name"]}" --mode=silent'
        )

    def _kill_adobe_installer_dialogs(self) -> None:
        """Tắt hộp thoại Adobe Installer còn treo (vd. product not installed)."""
        names = (
            "Set-up.exe",
            "Setup.exe",
            "Uninstaller.exe",
            "Adobe Installer.exe",
            "HDHelper.exe",
        )
        self._kill_by_name(list(names), tree=True)

    def _rmtree_force(self, path: str) -> bool:
        """Xóa thư mục cứng đầu (file lock / permission)."""
        if not path or not os.path.exists(path):
            return True

        def _on_error(func, p, _exc):
            try:
                os.chmod(p, 0o777)
                func(p)
            except Exception:
                pass

        try:
            shutil.rmtree(path, onerror=_on_error)
        except Exception:
            pass
        if not os.path.exists(path):
            return True

        # robocopy mirror empty — xóa cây còn sót
        try:
            empty = os.path.join(
                os.environ.get("TEMP", r"C:\Windows\Temp"),
                f"_acc_empty_{os.getpid()}_{int(time.time())}",
            )
            os.makedirs(empty, exist_ok=True)
            subprocess.run(
                ["robocopy", empty, path, "/MIR", "/R:1", "/W:1", "/NFL", "/NDL", "/NJH", "/NJS"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            try:
                os.rmdir(path)
            except Exception:
                shutil.rmtree(path, ignore_errors=True)
            try:
                os.rmdir(empty)
            except Exception:
                pass
        except Exception:
            pass
        return not os.path.exists(path)

    def _force_remove_app_files(self, sap_code: str) -> bool:
        """
        Gỡ thủ công khi uninstaller Adobe fail / product không đăng ký registry.
        Xóa thư mục cài + shortcut + prefs user + key Uninstall.
        """
        meta = _ADOBE_PRODUCT_META.get(sap_code)
        if not meta:
            return False
        app_name = self._app_label(sap_code)
        exe_path = meta["exe"]
        install_dir = meta["install_dir"]

        self.log(f"{app_name}: gỡ thủ công (xóa file + shortcut)…")
        self.force_close_app_processes(
            sap_code, deep=True, log=False, wait_timeout=5.0, rounds=3
        )
        self._kill_adobe_installer_dialogs()
        time.sleep(0.8)

        if os.path.isdir(install_dir):
            ok = self._rmtree_force(install_dir)
            if ok:
                self.log(f"{app_name}: đã xóa {install_dir}")
            else:
                self.log(f"{app_name}: chưa xóa hết {install_dir}", "danger")

        for sc in meta.get("shortcuts", ()):
            sc_exp = os.path.expandvars(sc)
            if os.path.exists(sc_exp):
                try:
                    os.remove(sc_exp)
                    self.log(f"{app_name}: đã xóa shortcut {sc_exp}")
                except Exception as e:
                    self.log(f"{app_name}: không xóa được shortcut: {e}", "danger")

        for ud in meta.get("user_data", ()):
            ud_exp = os.path.expandvars(ud)
            if os.path.isdir(ud_exp):
                self._rmtree_force(ud_exp)

        # Desktop shortcuts (user + public)
        for desk in (
            os.path.join(os.environ.get("PUBLIC", r"C:\Users\Public"), "Desktop"),
            os.path.join(os.environ.get("USERPROFILE", ""), "Desktop"),
        ):
            if not desk or not os.path.isdir(desk):
                continue
            for name in os.listdir(desk):
                low = name.lower()
                if sap_code == "PHSP" and "photoshop" in low and name.lower().endswith(".lnk"):
                    try:
                        os.remove(os.path.join(desk, name))
                    except Exception:
                        pass
                if sap_code == "ILST" and "illustrator" in low and name.lower().endswith(".lnk"):
                    try:
                        os.remove(os.path.join(desk, name))
                    except Exception:
                        pass

        self._delete_uninstall_registry_keys(sap_code)
        return not os.path.exists(exe_path)

    def _delete_uninstall_registry_keys(self, sap_code: str) -> None:
        """Xóa key Uninstall chứa registry có chứa sapCode (PHSP/ILST)."""
        roots = (
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
            ),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        )
        needle = sap_code.lower()
        for hkey, sub in roots:
            try:
                with winreg.OpenKey(hkey, sub, 0, winreg.KEY_ALL_ACCESS) as key:
                    to_del = []
                    for i in range(winreg.QueryInfoKey(key)[0]):
                        try:
                            name = winreg.EnumKey(key, i)
                            if needle in name.lower():
                                to_del.append(name)
                        except OSError:
                            break
                    for name in to_del:
                        try:
                            winreg.DeleteKey(key, name)
                            self.log(f"Đã xóa registry Uninstall\\{name}")
                        except OSError:
                            pass
            except OSError:
                continue

    def _run_uninstall_flow(self, sap_code: str) -> bool:
        """
        Gỡ cài: kill → uninstaller Adobe (registry / HDBox) → fallback xóa thủ công.
        Trả về True nếu exe đã biến mất.
        """
        meta = _ADOBE_PRODUCT_META.get(sap_code)
        if not meta:
            return False
        exe_path = meta["exe"]
        app_name = self._app_label(sap_code)

        for attempt in range(1, 3):
            self.log(
                f"{app_name}: chuẩn bị gỡ (lần {attempt}/2) — đóng process + unlock file…"
            )
            self.force_close_app_processes(
                sap_code, deep=True, log=(attempt == 1), wait_timeout=6.0, rounds=3
            )
            time.sleep(1.2 if attempt == 1 else 2.0)

            if not os.path.exists(exe_path):
                self._kill_adobe_installer_dialogs()
                return True

            uninstall_cmd = (
                self.get_uninstall_command(sap_code)
                or self._build_official_uninstall_cmd(sap_code)
            )
            if uninstall_cmd:
                self.log(f"{app_name}: chạy uninstaller Adobe…")
                try:
                    process = subprocess.Popen(
                        uninstall_cmd,
                        shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    process.communicate(timeout=180)
                except subprocess.TimeoutExpired:
                    try:
                        process.kill()
                    except Exception:
                        pass
                    self.log(
                        f"{app_name}: uninstaller quá lâu — abort lần {attempt}", "danger"
                    )
                except Exception as e:
                    self.log(f"{app_name}: lỗi uninstaller: {e}", "danger")
                finally:
                    # Đóng hộp thoại "product is not installed" nếu có
                    self._kill_adobe_installer_dialogs()

                for _ in range(16):
                    if not os.path.exists(exe_path):
                        return True
                    time.sleep(0.4)
            else:
                self.log(f"{app_name}: không có uninstaller Adobe — chuyển gỡ thủ công.")

            self.force_close_app_processes(
                sap_code, deep=True, log=False, wait_timeout=4.0, rounds=2
            )

        # Adobe uninstaller thường fail với bản pre-activated / mất registry
        if os.path.exists(exe_path):
            self.log(
                f"{app_name}: uninstaller không xóa file — chuyển sang gỡ thủ công."
            )
            if self._force_remove_app_files(sap_code):
                return True
            # thử thêm 1 lần sau khi kill lại
            self.force_close_app_processes(
                sap_code, deep=True, log=False, wait_timeout=5.0, rounds=3
            )
            time.sleep(1.0)
            return self._force_remove_app_files(sap_code)

        return not os.path.exists(exe_path)

    def toggle_photoshop(self):
        """Mở/Đóng PS mượt — không block UI, feedback nút ngay."""
        if getattr(self, "_toggling_ps", False) or self.installing_ps:
            return
        if self.is_ps_running or self.is_process_running("Photoshop.exe"):
            self._toggling_ps = True
            try:
                self.btn_open_ps.config(state=tk.DISABLED, text="Đang đóng…", fg=COLOR_DANGER)
            except tk.TclError:
                pass

            def _close():
                try:
                    ok = self.force_close_app_processes(
                        "PHSP", deep=False, log=True, wait_timeout=3.0, rounds=2
                    )
                    if not ok:
                        # App chính bám — deep kill một nhịp
                        ok = self.force_close_app_processes(
                            "PHSP", deep=True, log=False, wait_timeout=4.0, rounds=2
                        )
                    self.is_ps_running = not ok
                    if ok:
                        self.log_action("Photoshop CC 2019", "Đã đóng ứng dụng")
                    else:
                        self.log_action(
                            "Photoshop CC 2019", "Đóng chưa sạch", "process vẫn chạy"
                        )
                finally:
                    self._toggling_ps = False
                    self.root.after(0, self.update_ps_ui)

            threading.Thread(target=_close, daemon=True).start()
            return

        if os.path.exists(PS_EXE_PATH):
            self._toggling_ps = True
            try:
                self.btn_open_ps.config(state=tk.DISABLED, text="Đang mở…", fg=COLOR_SUCCESS)
            except tk.TclError:
                pass
            try:
                self.log_action("Photoshop CC 2019", "Khởi chạy ứng dụng")
                os.startfile(PS_EXE_PATH)
                self.is_ps_running = True
            except Exception as e:
                self.log_action("Photoshop CC 2019", "Mở LỖI", str(e))
                messagebox.showerror("Lỗi", f"Không mở được Photoshop:\n{e}")
            finally:
                # Cho monitor cập nhật sau khi process lên
                def _done():
                    self._toggling_ps = False
                    self.update_ps_ui()
                self.root.after(800, _done)
        else:
            messagebox.showerror("Lỗi", "Không tìm thấy file thực thi của Photoshop.")

    def import_ps_presets(self):
        """Import actions and scripts into Photoshop."""
        if not self.is_ps_installed:
            messagebox.showerror("Lỗi", "Photoshop CC 2019 chưa được cài đặt!")
            return

        imports_dir = os.path.join(self.base_dir, "Photoshop_Imports")
        actions_src = os.path.join(imports_dir, "Actions")
        scripts_src = os.path.join(imports_dir, "Scripts")
        os.makedirs(actions_src, exist_ok=True)
        os.makedirs(scripts_src, exist_ok=True)

        ps_actions_dst = r"C:\Program Files\Adobe\Adobe Photoshop CC 2019\Presets\Actions"
        ps_scripts_dst = r"C:\Program Files\Adobe\Adobe Photoshop CC 2019\Presets\Scripts"

        if not os.path.exists(ps_actions_dst) or not os.path.exists(ps_scripts_dst):
            messagebox.showerror("Lỗi", "Không tìm thấy thư mục Presets của Photoshop!")
            return

        imported_actions = []
        imported_scripts = []

        try:
            for item in os.listdir(scripts_src):
                if item.lower().endswith((".jsx", ".js")):
                    src_file = os.path.join(scripts_src, item)
                    dst_file = os.path.join(ps_scripts_dst, item)
                    shutil.copy2(src_file, dst_file)
                    imported_scripts.append(item)
        except Exception as e:
            self.log(f"Lỗi khi copy Scripts: {e}")

        try:
            for item in os.listdir(actions_src):
                if item.lower().endswith(".atn"):
                    src_file = os.path.join(actions_src, item)
                    dst_file = os.path.join(ps_actions_dst, item)
                    shutil.copy2(src_file, dst_file)
                    imported_actions.append(item)
        except Exception as e:
            self.log(f"Lỗi khi copy Actions: {e}")

        if not imported_actions and not imported_scripts:
            self.log("Thư mục nhập trống. Đang mở thư mục Photoshop_Imports để bạn thêm file...")
            os.startfile(imports_dir)
            messagebox.showinfo(
                "Thông báo",
                "Thư mục Photoshop_Imports hiện đang trống!\n\n"
                "Tôi đã mở thư mục này ra. Hãy copy các file .atn vào thư mục 'Actions' "
                "và các file .jsx vào thư mục 'Scripts', sau đó bấm lại nút này.",
            )
            return

        if imported_actions:
            self.log(f"Đang tự động nạp {len(imported_actions)} Actions vào Photoshop...")
            jsx_content = []
            for action_name in imported_actions:
                action_path = os.path.join(ps_actions_dst, action_name).replace("\\", "/")
                jsx_content.append(f'try {{ app.load(new File("{action_path}")); }} catch(e) {{}}')

            temp_jsx = os.path.join(imports_dir, "temp_load_actions.jsx")
            try:
                with open(temp_jsx, "w", encoding="utf-8") as f:
                    f.write("\n".join(jsx_content))

                cmd = f'"{PS_EXE_PATH}" "{temp_jsx}"'
                subprocess.Popen(cmd, shell=True)
                self.log_action("Photoshop CC 2019", "Đã nạp thành công Actions và Scripts vào Photoshop.")
                messagebox.showinfo(
                    "Thành công",
                    f"Đã sao chép:\n- {len(imported_scripts)} Scripts\n- {len(imported_actions)} Actions\n\n"
                    "Photoshop đang khởi động để tự động nạp các Actions này!",
                )
            except Exception as e:
                self.log(f"Lỗi nạp Actions tự động: {e}")
                messagebox.showinfo(
                    "Thành công",
                    f"Đã sao chép {len(imported_scripts)} Scripts và {len(imported_actions)} "
                    "Actions vào thư mục Presets của Photoshop!",
                )
        else:
            self.log_action(
                "Photoshop CC 2019",
                f"Đã sao chép thành công {len(imported_scripts)} Scripts vào Photoshop.",
            )
            messagebox.showinfo(
                "Thành công",
                f"Đã sao chép thành công {len(imported_scripts)} Scripts vào thư mục Presets của Photoshop!",
            )

    # ------------------------------------------------------------------ AI install/uninstall
    def start_install_ai(self):
        if self.installing_ai:
            return
        if not os.path.exists(self.ai_installer):
            messagebox.showerror("Lỗi", "Không tìm thấy file Set-up.exe của Illustrator!")
            return

        self.installing_ai = True
        self.btn_install_ai.config(state=tk.DISABLED)
        self.btn_uninstall_ai.config(state=tk.DISABLED)
        self.ai_status_label.config(text="ĐANG CÀI ĐẶT...", fg=COLOR_ACCENT_AI)
        self.log_action("Illustrator CC 2019", "Bắt đầu cài đặt ngầm")
        threading.Thread(target=self.install_ai_worker, daemon=True).start()

    def install_ai_worker(self):
        try:
            try:
                self.ai_action_type = "INSTALL"
                self.root.after(0, lambda: self.set_ai_progress(0))
                threading.Thread(target=self.run_simulated_progress, args=("AI", 90), daemon=True).start()

                ok = self._run_install_flow("ILST", self.ai_installer)
                if ok:
                    self.root.after(0, lambda: self.set_ai_progress(100))
                    time.sleep(0.3)
                    self.is_ai_installed = True
                    self.log_action("Illustrator CC 2019", "Cài đặt THÀNH CÔNG")
                    self.root.after(
                        0,
                        lambda: messagebox.showinfo(
                            "Thông báo", "Illustrator CC 2019 đã được cài đặt thành công!"
                        ),
                    )
                else:
                    self.root.after(0, lambda: self.set_ai_progress(0))
                    self.log_action(
                        "Illustrator CC 2019", "Cài đặt THẤT BẠI", "Không tìm thấy file chạy"
                    )
                    self.root.after(
                        0,
                        lambda: messagebox.showerror("Lỗi", "Cài đặt Illustrator CC 2019 thất bại!"),
                    )
            except Exception as e:
                self.root.after(0, lambda: self.set_ai_progress(0))
                self.log_action("Illustrator CC 2019", "Cài đặt LỖI", str(e))
                self.root.after(
                    0,
                    lambda err=e: messagebox.showerror(
                        "Lỗi", f"Có lỗi xảy ra trong quá trình cài đặt: {err}"
                    ),
                )
        finally:
            self.installing_ai = False
            self.ai_action_type = None
            self.is_ai_installed = os.path.exists(AI_EXE_PATH)
            self.root.after(0, self.update_ai_ui)

    def _run_install_flow(self, sap_code: str, installer_path: str) -> bool:
        """
        Cài silent HD installer:
        kill process cũ → chạy Set-up.exe silent → đợi exe (tối đa ~3 phút).
        """
        meta = _ADOBE_PRODUCT_META.get(sap_code)
        if not meta:
            return False
        exe_path = meta["exe"]
        app_name = self._app_label(sap_code)

        if not installer_path or not os.path.exists(installer_path):
            self.log(f"{app_name}: không tìm thấy Set-up.exe", "danger")
            return False

        # Dọn process cũ + installer treo — tránh file lock
        self.force_close_app_processes(
            sap_code, deep=True, log=True, wait_timeout=4.0, rounds=2
        )
        self._kill_adobe_installer_dialogs()
        time.sleep(0.8)

        # Nếu còn mảnh cài dở (exe mất nhưng folder rác) — dọn install dir trống/hỏng
        if not os.path.exists(exe_path) and os.path.isdir(meta["install_dir"]):
            # chỉ dọn nếu thiếu exe (cài dở) — tránh xóa bản đang dùng
            self.log(f"{app_name}: phát hiện thư mục cài dở — dọn trước khi cài lại…")
            self._rmtree_force(meta["install_dir"])

        installer_dir = os.path.dirname(installer_path)
        # Pre-activated HD package: silent flags chuẩn
        cmd = (
            f'"{installer_path}" --silent=1 --ADOBE_SETUP_IN_PROCESS=1 --install=1'
        )
        self.log(f"{app_name}: chạy installer silent…")
        try:
            process = subprocess.Popen(
                cmd,
                cwd=installer_dir,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            try:
                process.communicate(timeout=600)
            except subprocess.TimeoutExpired:
                self.log(f"{app_name}: installer quá lâu (>10 phút) — vẫn kiểm tra file…", "danger")
                try:
                    process.kill()
                except Exception:
                    pass
        except Exception as e:
            self.log(f"{app_name}: lỗi chạy installer: {e}", "danger")
            self._kill_adobe_installer_dialogs()
            return os.path.exists(exe_path)

        # Đợi exe xuất hiện (cài silent đôi khi ghi file chậm)
        deadline = time.time() + 120
        while time.time() < deadline:
            if os.path.exists(exe_path):
                break
            time.sleep(1.0)

        self._kill_adobe_installer_dialogs()
        ok = os.path.exists(exe_path)
        if ok:
            self.log(f"{app_name}: đã thấy file chạy tại {exe_path}")
        else:
            self.log(f"{app_name}: hết thời gian chờ — chưa thấy {exe_path}", "danger")
        return ok

    def start_uninstall_ai(self):
        if not messagebox.askyesno(
            "Xác nhận", "Bạn có chắc muốn gỡ cài đặt nhanh Illustrator CC 2019?"
        ):
            return

        self.installing_ai = True
        self.btn_install_ai.config(state=tk.DISABLED)
        self.btn_uninstall_ai.config(state=tk.DISABLED)
        self.ai_status_label.config(text="ĐANG GỠ BỎ...", fg=COLOR_DANGER)
        self.log_action("Illustrator CC 2019", "Bắt đầu gỡ cài đặt ngầm")
        threading.Thread(target=self.uninstall_ai_worker, daemon=True).start()

    def uninstall_ai_worker(self):
        try:
            try:
                self.ai_action_type = "UNINSTALL"
                self.root.after(0, lambda: self.set_ai_progress(0))
                threading.Thread(target=self.run_simulated_progress, args=("AI", 30), daemon=True).start()

                ok = self._run_uninstall_flow("ILST")
                if ok:
                    self.root.after(0, lambda: self.set_ai_progress(100))
                    time.sleep(0.3)
                    self.log_action("Illustrator CC 2019", "Gỡ cài đặt THÀNH CÔNG")
                    self.root.after(
                        0,
                        lambda: messagebox.showinfo(
                            "Thông báo", "Illustrator CC 2019 đã được gỡ cài đặt thành công!"
                        ),
                    )
                else:
                    self.root.after(0, lambda: self.set_ai_progress(0))
                    self.log_action(
                        "Illustrator CC 2019", "Gỡ cài đặt THẤT BẠI", "Vẫn tồn tại file chạy"
                    )
                    self.root.after(
                        0,
                        lambda: messagebox.showerror(
                            "Lỗi",
                            "Gỡ cài đặt Illustrator CC 2019 thất bại!\n"
                            "Thử: Đóng PS+AI → Tắt dịch vụ → Gỡ lại.\n"
                            "(Cần chạy app với quyền Administrator nếu file bị khóa.)",
                        ),
                    )
            except Exception as e:
                self.root.after(0, lambda: self.set_ai_progress(0))
                self.log_action("Illustrator CC 2019", "Gỡ cài đặt LỖI", str(e))
                self.root.after(
                    0,
                    lambda err=e: messagebox.showerror(
                        "Lỗi", f"Có lỗi xảy ra trong quá trình gỡ cài đặt: {err}"
                    ),
                )
        finally:
            self.installing_ai = False
            self.ai_action_type = None
            self.is_ai_installed = os.path.exists(AI_EXE_PATH)
            self.is_ai_running = self.is_process_running("Illustrator.exe")
            self.root.after(0, self.update_ai_ui)

    def toggle_illustrator(self):
        """Mở/Đóng AI mượt — không block UI, feedback nút ngay."""
        if getattr(self, "_toggling_ai", False) or self.installing_ai:
            return
        if self.is_ai_running or self.is_process_running("Illustrator.exe"):
            self._toggling_ai = True
            try:
                self.btn_open_ai.config(state=tk.DISABLED, text="Đang đóng…", fg=COLOR_DANGER)
            except tk.TclError:
                pass

            def _close():
                try:
                    ok = self.force_close_app_processes(
                        "ILST", deep=False, log=True, wait_timeout=3.0, rounds=2
                    )
                    if not ok:
                        ok = self.force_close_app_processes(
                            "ILST", deep=True, log=False, wait_timeout=4.0, rounds=2
                        )
                    self.is_ai_running = not ok
                    if ok:
                        self.log_action("Illustrator CC 2019", "Đã đóng ứng dụng")
                    else:
                        self.log_action(
                            "Illustrator CC 2019", "Đóng chưa sạch", "process vẫn chạy"
                        )
                finally:
                    self._toggling_ai = False
                    self.root.after(0, self.update_ai_ui)

            threading.Thread(target=_close, daemon=True).start()
            return

        if os.path.exists(AI_EXE_PATH):
            self._toggling_ai = True
            try:
                self.btn_open_ai.config(state=tk.DISABLED, text="Đang mở…", fg=COLOR_SUCCESS)
            except tk.TclError:
                pass
            try:
                self.log_action("Illustrator CC 2019", "Khởi chạy ứng dụng")
                os.startfile(AI_EXE_PATH)
                self.is_ai_running = True
            except Exception as e:
                self.log_action("Illustrator CC 2019", "Mở LỖI", str(e))
                messagebox.showerror("Lỗi", f"Không mở được Illustrator:\n{e}")
            finally:
                def _done():
                    self._toggling_ai = False
                    self.update_ai_ui()
                self.root.after(800, _done)
        else:
            messagebox.showerror("Lỗi", "Không tìm thấy file thực thi của Illustrator.")

    # ------------------------------------------------------------------ system tools
    def clean_adobe_remnants(self):
        """Clean leftover files, cache, and registry entries of uninstalled Adobe apps."""
        if self.is_ps_installed or self.is_ai_installed:
            if not messagebox.askyesno(
                "Xác nhận",
                "Cảnh báo: Phát hiện Photoshop hoặc Illustrator vẫn đang được cài đặt.\n"
                "Việc dọn dẹp có thể làm mất dữ liệu cấu hình hoặc ảnh hưởng đến ứng dụng đang chạy.\n"
                "Bạn có chắc chắn muốn tiếp tục dọn dẹp tàn dư không?",
            ):
                return
        elif not messagebox.askyesno(
            "Xác nhận",
            "Bạn có chắc muốn dọn dẹp toàn bộ tàn dư, file tạm và Registry cũ của Adobe?",
        ):
            return

        self.log_action("Hệ thống", "Bắt đầu dọn dẹp tàn dư Adobe...")
        paths_to_clean = []

        def expand_path(p):
            return os.path.expandvars(p)

        if not self.is_ps_installed:
            paths_to_clean.extend(
                [
                    r"C:\Program Files\Adobe\Adobe Photoshop CC 2019",
                    r"%appdata%\Adobe\Photoshop",
                    r"%localappdata%\Adobe\Photoshop",
                    r"%appdata%\Adobe\Workflow",
                ]
            )

        if not self.is_ai_installed:
            paths_to_clean.extend(
                [
                    r"C:\Program Files\Adobe\Adobe Illustrator CC 2019",
                    r"%appdata%\Adobe\Adobe Illustrator",
                    r"%appdata%\Adobe\Adobe Illustrator 23 Settings",
                    r"%appdata%\Adobe\Adobe Illustrator CC 2019",
                    r"%localappdata%\Adobe\Adobe Illustrator",
                    r"%localappdata%\Adobe\Adobe Illustrator 23 Settings",
                ]
            )

        paths_to_clean.extend(
            [
                r"%localappdata%\Temp\Adobe",
                r"%localappdata%\Adobe\OOBE",
                r"%localappdata%\Adobe\AAMUpdater",
                r"C:\Program Files (x86)\Common Files\Adobe\Installers",
                r"C:\ProgramData\Adobe\Setup",
            ]
        )

        cleaned_dirs_count = 0
        cleaned_files_count = 0
        failed_paths = []

        for path_template in paths_to_clean:
            real_path = expand_path(path_template)
            if not os.path.exists(real_path):
                continue

            try:
                if os.path.isdir(real_path):
                    shutil.rmtree(real_path, ignore_errors=True)
                    if os.path.exists(real_path):
                        for root_dir, dirs, files in os.walk(real_path, topdown=False):
                            for name in files:
                                try:
                                    os.remove(os.path.join(root_dir, name))
                                    cleaned_files_count += 1
                                except Exception:
                                    pass
                            for name in dirs:
                                try:
                                    os.rmdir(os.path.join(root_dir, name))
                                except Exception:
                                    pass
                        try:
                            os.rmdir(real_path)
                        except Exception:
                            pass
                    cleaned_dirs_count += 1
                else:
                    os.remove(real_path)
                    cleaned_files_count += 1

                self.log(f"Đã xóa: {real_path}")
            except Exception:
                failed_paths.append(real_path)

        reg_keys_to_clean = []
        if not self.is_ps_installed:
            reg_keys_to_clean.extend(
                [
                    (winreg.HKEY_CURRENT_USER, r"Software\Adobe\Photoshop"),
                    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Adobe\Photoshop"),
                ]
            )
        if not self.is_ai_installed:
            reg_keys_to_clean.extend(
                [
                    (winreg.HKEY_CURRENT_USER, r"Software\Adobe\Adobe Illustrator"),
                    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Adobe\Adobe Illustrator"),
                ]
            )

        def delete_reg_key_recursive(hkey, subkey):
            try:
                with winreg.OpenKey(hkey, subkey, 0, winreg.KEY_ALL_ACCESS) as key:
                    info = winreg.QueryInfoKey(key)
                    for i in range(info[0] - 1, -1, -1):
                        child = winreg.EnumKey(key, i)
                        delete_reg_key_recursive(hkey, f"{subkey}\\{child}")
                winreg.DeleteKey(hkey, subkey)
                self.log(f"Đã xóa Registry Key: {subkey}")
            except Exception:
                pass

        for hkey, subkey in reg_keys_to_clean:
            delete_reg_key_recursive(hkey, subkey)

        self.log_action(
            "Hệ thống", f"Đã dọn dẹp xong. Xóa {cleaned_dirs_count} thư mục tàn dư."
        )
        messagebox.showinfo(
            "Thông báo",
            f"Đã hoàn tất dọn dẹp tàn dư Adobe!\nXóa thành công {cleaned_dirs_count} thư mục tàn dư.",
        )

    def disable_adobe_services(self):
        """Disable Adobe background services — chạy nền, UI không đơ."""
        if getattr(self, "_disabling_services", False):
            return
        if not messagebox.askyesno(
            "Xác nhận",
            "Bạn có chắc muốn vô hiệu hóa tất cả các dịch vụ chạy ngầm và kiểm tra bản quyền "
            "của Adobe để tăng tốc máy?",
        ):
            return

        self._disabling_services = True
        svc_btn_text = None
        if hasattr(self, "btn_disable_services"):
            try:
                svc_btn_text = self.btn_disable_services.cget("text")
                self.btn_disable_services.config(state=tk.DISABLED, text="Đang tắt…")
            except tk.TclError:
                pass

        self.log_action("Hệ thống", "Bắt đầu vô hiệu hóa các dịch vụ chạy ngầm Adobe...")

        def _worker():
            ps_cmd = (
                "Get-Service | Where-Object { $_.Name -like '*Adobe*' -or $_.DisplayName -like '*Adobe*' "
                "-or $_.Name -eq 'AGSService' -or $_.Name -eq 'AdobeUpdateService' } | ForEach-Object { "
                "  $name = $_.Name; "
                "  Set-Service -Name $name -StartupType Disabled -ErrorAction SilentlyContinue; "
                "  Stop-Service -Name $name -Force -ErrorAction SilentlyContinue; "
                "  Write-Output $name }"
            )
            try:
                process = subprocess.Popen(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                stdout, _stderr = process.communicate(timeout=60)
                disabled_list = [line.strip() for line in stdout.splitlines() if line.strip()]

                def _done_ok():
                    if disabled_list:
                        for svc in disabled_list:
                            self.log(f"Đã tắt & vô hiệu hóa dịch vụ: {svc}")
                        self.log_action(
                            "Hệ thống",
                            f"Đã vô hiệu hóa thành công {len(disabled_list)} dịch vụ nền.",
                        )
                        messagebox.showinfo(
                            "Thông báo",
                            f"Đã tắt và vô hiệu hóa thành công {len(disabled_list)} dịch vụ Adobe chạy ngầm!",
                        )
                    else:
                        self.log("Không tìm thấy dịch vụ chạy ngầm nào của Adobe đang hoạt động.")
                        messagebox.showinfo(
                            "Thông báo",
                            "Không tìm thấy dịch vụ chạy ngầm nào của Adobe cần xử lý.",
                        )

                self.root.after(0, _done_ok)
            except Exception as e:
                self.root.after(
                    0,
                    lambda err=e: (
                        self.log(f"Lỗi khi tắt dịch vụ: {err}"),
                        messagebox.showerror("Lỗi", f"Có lỗi xảy ra khi tắt dịch vụ: {err}"),
                    ),
                )
            finally:
                self._disabling_services = False

                def _restore():
                    if hasattr(self, "btn_disable_services"):
                        try:
                            kw = {"state": tk.NORMAL}
                            if svc_btn_text:
                                kw["text"] = svc_btn_text
                            self.btn_disable_services.config(**kw)
                        except tk.TclError:
                            pass

                self.root.after(0, _restore)

        threading.Thread(target=_worker, daemon=True).start()

    def open_dxf_converter(self):
        """Launch the Image to DXF Converter tool."""
        try:
            script_path = os.path.join(self.base_dir, "image_to_dxf.py")
            subprocess.Popen([sys.executable, script_path])
            self.log("Đã khởi chạy công cụ Chuyển ảnh sang DXF (1:1).")
        except Exception as e:
            self.log(f"Lỗi khởi chạy công cụ DXF: {e}")
            messagebox.showerror("Lỗi", f"Không thể mở công cụ DXF: {e}")

    # ------------------------------------------------------------------ drag & drop
    def _normalize_dropped_path(self, raw) -> str:
        if isinstance(raw, bytes):
            for enc in ("utf-8", "mbcs", "gbk"):
                try:
                    return raw.decode(enc).strip()
                except Exception:
                    continue
            return raw.decode("utf-8", errors="ignore").strip()
        return str(raw).strip().strip("{}")

    def _drop_target(self, zone_attr: str, col_attr: str | None = None):
        for attr in (col_attr, zone_attr):
            if not attr:
                continue
            widget = getattr(self, attr, None)
            if widget is not None:
                try:
                    if widget.winfo_exists():
                        return widget
                except tk.TclError:
                    pass
        return getattr(self, zone_attr, None)

    def setup_drag_and_drop(self):
        """Setup windnd drag and drop for each tool zone."""
        if getattr(self, "_drag_drop_hooked", False):
            return
        try:
            import windnd

            def _collect_images(files, extra_ext=()):
                paths = []
                ok_ext = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".psd") + extra_ext
                for f in files:
                    p = self._normalize_dropped_path(f)
                    if not p or not os.path.isfile(p):
                        continue
                    ext = os.path.splitext(p)[1].lower()
                    if ext in ok_ext:
                        paths.append(os.path.abspath(p))
                return paths

            def _schedule(tool: str, paths: list[str]) -> None:
                if len(paths) == 1:
                    path = paths[0]
                    if tool == "patch":
                        self.root.after(0, lambda p=path: self.process_patch_crop(p))
                    elif tool == "dxf":
                        self.root.after(0, lambda p=path: self.process_image_to_dxf(p))
                    else:
                        self.root.after(0, lambda p=path: self.process_spot_color_tif(p))
                else:
                    batch = list(paths)
                    self.root.after(0, lambda ps=batch, t=tool: self.produce_queue.enqueue_many(t, ps))

            def handle_patch_drop(files):
                if not files:
                    return
                paths = _collect_images(files)
                if not paths:
                    self.log("Patch crop: chỉ hỗ trợ file ảnh.", "danger")
                    return
                _schedule("patch", paths)

            def handle_dxf_drop(files):
                if not files:
                    return
                paths = [p for p in _collect_images(files) if os.path.splitext(p)[1].lower() in (
                    ".png", ".jpg", ".jpeg", ".bmp",
                )]
                if not paths:
                    self.log("DXF: chỉ hỗ trợ .png / .jpg / .bmp.", "danger")
                    return
                _schedule("dxf", paths)

            def handle_spot_drop(files):
                if not files:
                    return
                paths = _collect_images(files)
                if not paths:
                    self.log("Spot W1: chỉ hỗ trợ file ảnh.", "danger")
                    return
                _schedule("spot", paths)

            targets = (
                ("patch_drop_zone", "patch_drop_col", handle_patch_drop),
                ("dxf_drop_zone", "dxf_drop_col", handle_dxf_drop),
                ("spot_drop_zone", "spot_drop_col", handle_spot_drop),
            )
            hooked = 0
            for zone_attr, col_attr, handler in targets:
                widget = self._drop_target(zone_attr, col_attr)
                if widget is None:
                    continue
                windnd.hook_dropfiles(widget, func=handler)
                hooked += 1

            if hooked:
                self._drag_drop_hooked = True
                self.log("Kéo thả sẵn sàng: Patch crop + Xuất DXF + Spot W1.")
            else:
                self.log("Kéo thả: chưa tìm thấy vùng drop.", "danger")
        except ImportError:
            threading.Thread(target=self.install_windnd_silently, daemon=True).start()
        except Exception as exc:
            self.log(f"Kéo thả lỗi: {exc}", "danger")

    def install_windnd_silently(self):
        if getattr(sys, "frozen", False):
            self.log("Thiếu windnd trong bản exe — rebuild kèm windnd.", "danger")
            return
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "windnd"])
            self.root.after(1000, self.setup_drag_and_drop)
        except Exception:
            pass

    def select_patch_image(self, event=None):
        file_path = filedialog.askopenfilename(
            title="Chọn ảnh thiết kế Patch để cắt theo template GG",
            filetypes=[("Image Files", "*.png;*.jpg;*.jpeg;*.bmp;*.tif;*.tiff")],
        )
        if file_path:
            self.process_patch_crop(file_path)

    def _auto_dxf_after_patch(self) -> bool:
        var = getattr(self, "auto_dxf_var", None)
        return var is not None and bool(var.get())

    def _dxf_min_match_pct(self) -> float:
        skip_var = getattr(self, "dxf_skip_low_var", None)
        if skip_var is not None and skip_var.get():
            return float(getattr(self, "DXF_MIN_MATCH", 95.0))
        return 0.0

    def process_patch_crop(self, file_path, silent=False):
        self.log(f"Đang cắt patch: {os.path.basename(file_path)}...")
        self.root.update()

        try:
            from patch_crop import process_patch_image
        except ImportError as e:
            self.log(f"Lỗi import patch_crop: {e}", "danger")
            if not silent:
                messagebox.showerror("Lỗi", f"Không thể tải module patch_crop: {e}")
            return {"ok": False, "error": str(e)}

        try:
            order_stem = None
            position = None
            emb = getattr(self, "emb_panel", None)
            if emb:
                order_stem = emb.get_order_id_for_patch()
                position = emb.get_selected_position()

            # 2 ảnh patch luôn ra Desktop (không vào folder đơn), kể cả khi bật Patch→DXF
            result = process_patch_image(
                file_path,
                base_dir=self.base_dir,
                order_stem=order_stem,
                position=position,
                output_dir=None,
            )
            if order_stem and emb:
                try:
                    from modules.emb_stats import record_emb_action
                    record_emb_action(order_stem, "patch")
                except Exception:
                    pass
                if hasattr(self, "refresh_daily_stats"):
                    self.root.after(0, self.refresh_daily_stats)
            w1, h1 = result["size_1"]
            dpi_x, dpi_y = result.get("dpi", (300, 300))
            mm_w, mm_h = result.get("size_mm", (0, 0))

            self.log_action(
                "Patch Crop",
                "Cắt THÀNH CÔNG",
                f"{os.path.basename(result['output_1'])} + {os.path.basename(result['output_2'])} "
                f"({w1}x{h1}px @ {dpi_x:.0f}dpi)",
            )

            out = {
                "ok": True,
                "message": f"{os.path.basename(result['output_1'])} + {os.path.basename(result['output_2'])}",
                "output_1": result["output_1"],
                "output_2": result["output_2"],
            }

            if self._auto_dxf_after_patch():
                self.log(
                    f"Patch → DXF: {os.path.basename(result['output_2'])}…",
                    "accent",
                )
                dxf_result = self.process_image_to_dxf(result["output_2"], silent=silent)
                out["dxf"] = dxf_result
                if dxf_result and dxf_result.get("ok"):
                    mp = dxf_result.get("match_pct")
                    if mp is not None:
                        out["match_pct"] = mp
                        out["message"] += f" · DXF {mp:.1f}% khớp"

            if not silent:
                extra = ""
                dxf = out.get("dxf")
                if dxf and dxf.get("ok") and dxf.get("dxf_path"):
                    extra = (
                        f"\n\nDXF (từ ảnh cắt đen):\n"
                        f"  → {os.path.basename(dxf['dxf_path'])}\n"
                        f"  → Khớp {dxf.get('match_pct', 0):.1f}%"
                    )
                elif dxf and dxf.get("skipped"):
                    extra = f"\n\nDXF: bỏ qua — {dxf.get('message', '')}"
                messagebox.showinfo(
                    "Thành công",
                    f"Đã cắt patch và xuất ra Desktop!\n\n"
                    f"Ảnh thiết kế: {os.path.basename(result['output_1'])}\n"
                    f"  → {w1} x {h1} px @ {dpi_x:.0f} DPI\n"
                    f"  → {mm_w:.1f} x {mm_h:.1f} mm (giữ nguyên chất lượng, không resize)\n\n"
                    f"Ảnh cắt đen: {os.path.basename(result['output_2'])}\n"
                    f"  → {w1} x {h1} px @ {dpi_x:.0f} DPI (bôi đen để tạo file cắt)\n\n"
                    f"Vùng cắt: {result['layer_name']}{extra}",
                )
            return out
        except Exception as e:
            self.log(f"Lỗi cắt patch: {e}", "danger")
            if not silent:
                messagebox.showerror("Lỗi", f"Có lỗi khi cắt patch:\n{e}")
            return {"ok": False, "error": str(e)}

    def select_dxf_image(self, event=None):
        file_path = filedialog.askopenfilename(
            title="Chọn ảnh phủ đen Silhouette để xuất DXF",
            filetypes=[("Image Files", "*.png;*.jpg;*.jpeg;*.bmp")],
        )
        if file_path:
            self.process_image_to_dxf(file_path)

    def select_spot_color_image(self, event=None):
        file_path = filedialog.askopenfilename(
            title="Chọn ảnh để đổ spot channel W1 và lưu .TIF",
            filetypes=[("Image Files", "*.png;*.jpg;*.jpeg;*.bmp;*.tif;*.tiff;*.psd")],
        )
        if file_path:
            self.process_spot_color_tif(file_path)

    def _ensure_spot_color_deps(self) -> bool:
        """Install Spot W1 dependencies if missing."""
        missing = []
        for package, module in (
            ("numpy", "numpy"),
            ("pillow", "PIL"),
            ("tifffile", "tifffile"),
            ("psdtags", "psdtags"),
        ):
            try:
                __import__(module)
            except ImportError:
                missing.append(package)

        if not missing:
            return True

        self.log(f"Thiếu thư viện Spot W1: {', '.join(missing)}. Đang cài đặt...")
        self.root.update()
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", *missing],
            )
            self.log("Đã cài đặt xong thư viện Spot W1.", "success")
            return True
        except Exception as e:
            self.log(f"Không thể cài thư viện Spot W1: {e}", "danger")
            messagebox.showerror(
                "Lỗi",
                f"Thiếu thư viện: {', '.join(missing)}\n\n"
                f"Không tự cài được. Chạy thủ công:\n"
                f'pip install {" ".join(missing)}',
            )
            return False

    def process_spot_color_tif(self, file_path, silent=False):
        self.log(f"Đang đổ spot W1: {os.path.basename(file_path)}...")
        self.root.update()

        if not self._ensure_spot_color_deps():
            return {"ok": False, "error": "Thiếu thư viện Spot W1"}

        try:
            from spot_color_tif import apply_spot_color_w1
        except ImportError as e:
            self.log(f"Lỗi import spot_color_tif: {e}", "danger")
            if not silent:
                messagebox.showerror("Lỗi", f"Không thể tải module spot_color_tif: {e}")
            return {"ok": False, "error": str(e)}

        try:
            result = apply_spot_color_w1(file_path, base_dir=self.base_dir)
            c, m, y, k = result["cmyk"]
            w, h = result.get("size", (0, 0))
            dpi_x, dpi_y = result.get("dpi", (0, 0))
            self.log_action(
                "Spot W1",
                "Đổ màu THÀNH CÔNG",
                f"{os.path.basename(result['output'])} ({w}x{h}px, {result['solidity']}%)",
            )
            coverage = result.get("object_coverage_pct", 0)
            transparent = result.get("transparent_background_pct", 0)
            w1_spot = result.get("w1_spot_pct", 0)
            if not silent:
                messagebox.showinfo(
                    "Thành công",
                    f"Đã xuất .TIF spot W1 (giống Photoshop) ra Desktop!\n\n"
                    f"File: {result['output']}\n"
                    f"Kích thước: {w} x {h} px @ {dpi_x:.0f} DPI (giữ nguyên)\n"
                    f"Ảnh RGB + Alpha: giữ nguyên 100%\n"
                    f"Kênh W1: C:{c} M:{m} Y:{y} K:{k} (#ff0000), {w1_spot}%\n"
                    f"Nền trong suốt: {transparent}%\n"
                    f"Solidity: {result['solidity']}%\n"
                    f"Nén: None (lossless)\n"
                    f"Thời gian: {result['elapsed_sec']}s",
                )
            return {
                "ok": True,
                "message": os.path.basename(result["output"]),
                "output": result["output"],
            }
        except Exception as e:
            self.log(f"Lỗi đổ spot W1: {e}", "danger")
            if not silent:
                messagebox.showerror("Lỗi", f"Có lỗi khi đổ spot channel W1:\n{e}")
            return {"ok": False, "error": str(e)}

    def process_image_to_dxf(self, file_path, silent=False):
        self.log(f"Đang xử lý ảnh: {os.path.basename(file_path)}...")
        self.root.update()

        try:
            from dxf_convert import (
                compute_dxf_match_pct,
                extract_smooth_polylines,
                physical_size_mm,
                read_image_rgba,
            )
        except ImportError:
            self.log("Thiếu thư viện xử lý ảnh. Đang tự động cài đặt...")
            self.root.update()
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", "opencv-python", "ezdxf", "pillow"]
                )
                from dxf_convert import (
                    compute_dxf_match_pct,
                    extract_smooth_polylines,
                    physical_size_mm,
                    read_image_rgba,
                )

                self.log("Đã cài đặt xong thư viện!")
            except Exception as e:
                self.log(f"Không thể cài đặt thư viện: {e}", "danger")
                if not silent:
                    messagebox.showerror(
                        "Lỗi", f"Không thể tự động cài đặt các thư viện cần thiết: {e}"
                    )
                return {"ok": False, "error": str(e)}

        try:
            img_bgra, width_px, height_px, dpi = read_image_rgba(file_path)
            _, width_mm, height_mm = physical_size_mm(width_px, height_px, dpi)

            polylines = extract_smooth_polylines(img_bgra, width_px, height_px, dpi)

            if not polylines:
                self.log("Lỗi: Không tìm thấy đường biên nào!", "danger")
                if not silent:
                    messagebox.showerror("Lỗi", "Không tìm thấy đường biên nào trong ảnh!")
                return {"ok": False, "error": "Không tìm thấy đường biên"}

            match_pct = compute_dxf_match_pct(img_bgra, polylines, width_px, height_px, dpi)
            min_match = self._dxf_min_match_pct() if silent else 0.0
            if silent and min_match > 0 and match_pct < min_match:
                msg = f"Khớp {match_pct:.1f}% < {min_match:.0f}% — bỏ qua lưu"
                self.log(f"DXF: {os.path.basename(file_path)} · {msg}", "danger")
                return {
                    "ok": False,
                    "skipped": True,
                    "match_pct": match_pct,
                    "message": msg,
                }

            from modules.dxf_preview import confirm_dxf_preview, resolve_dxf_path, save_polylines_dxf

            if not silent:
                if not confirm_dxf_preview(
                    self.root, file_path, img_bgra, polylines,
                    width_px, height_px, dpi,
                ):
                    self.log("DXF: đã hủy — không lưu file (xem lại preview).", "danger")
                    return {"ok": False, "cancelled": True, "match_pct": match_pct}

            output_dir = None
            emb = getattr(self, "emb_panel", None)
            if emb:
                output_dir = emb.get_patch_output_dir()
            dxf_path = resolve_dxf_path(file_path, output_dir)
            save_polylines_dxf(polylines, dxf_path)
            dxf_name = os.path.basename(dxf_path)
            dest_label = os.path.basename(os.path.dirname(dxf_path)) if output_dir else "Desktop"
            if emb and emb.get_order_id_for_patch():
                try:
                    from modules.emb_stats import record_emb_action
                    record_emb_action(emb.get_order_id_for_patch(), "dxf")
                except Exception:
                    pass
                if hasattr(self, "refresh_daily_stats"):
                    self.root.after(0, self.refresh_daily_stats)

            width_cm = width_mm / 10.0
            height_cm = height_mm / 10.0
            dpi_u = max(float(dpi[0]), float(dpi[1]), 1.0)
            width_in = width_px / dpi_u
            height_in = height_px / dpi_u

            match_tag = "success" if match_pct >= 98.0 else ("danger" if match_pct < 90.0 else "accent")
            self.log(
                f"DXF: {dxf_name} · khớp {match_pct:.1f}% · "
                f"{width_cm:.1f}×{height_cm:.1f} cm → {dest_label}",
                match_tag,
            )
            if not silent:
                messagebox.showinfo(
                    "Thành công",
                    f"Đã xuất file cắt DXF (tỉ lệ 1:1)!\n\n"
                    f"File: {dxf_name}\n"
                    f"Thư mục: {os.path.dirname(dxf_path)}\n"
                    f"Khớp silhouette: {match_pct:.1f}%\n"
                    f"Kích thước:\n"
                    f"- {width_cm:.2f} cm x {height_cm:.2f} cm\n"
                    f"- {width_in:.2f} in x {height_in:.2f} in\n"
                    f"- {width_mm:.1f} mm x {height_mm:.1f} mm",
                )
            return {
                "ok": True,
                "match_pct": match_pct,
                "dxf_path": dxf_path,
                "message": f"{dxf_name} · {match_pct:.1f}% khớp",
            }
        except Exception as e:
            self.log(f"Lỗi chuyển đổi DXF: {e}", "danger")
            if not silent:
                messagebox.showerror("Lỗi", f"Có lỗi xảy ra: {e}")
            return {"ok": False, "error": str(e)}

    # ------------------------------------------------------------------ registry
    def get_uninstall_command(self, sap_code):
        registry_paths = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
            ),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        ]

        for hkey, subkey_path in registry_paths:
            try:
                with winreg.OpenKey(hkey, subkey_path) as key:
                    num_subkeys = winreg.QueryInfoKey(key)[0]
                    for i in range(num_subkeys):
                        try:
                            subkey_name = winreg.EnumKey(key, i)
                            if sap_code.lower() not in subkey_name.lower():
                                continue

                            with winreg.OpenKey(key, subkey_name) as subkey_obj:
                                uninstall_string = winreg.QueryValueEx(subkey_obj, "UninstallString")[0]

                            if not uninstall_string:
                                continue

                            # Registry đôi khi có xuống dòng / khoảng trắng thừa
                            uninstall_string = " ".join(
                                str(uninstall_string).replace("\r", " ").replace("\n", " ").split()
                            )

                            if (
                                "Setup.exe" in uninstall_string
                                or "Uninstaller.exe" in uninstall_string
                                or "Set-up.exe" in uninstall_string
                            ):
                                # mode=1 = GUI; silent để không bật hộp thoại
                                if "--mode=1" in uninstall_string:
                                    uninstall_string = uninstall_string.replace(
                                        "--mode=1", "--mode=silent"
                                    )
                                elif "--mode=silent" not in uninstall_string:
                                    uninstall_string = uninstall_string.strip() + " --mode=silent"
                                return uninstall_string
                        except Exception:
                            continue
            except Exception:
                continue

        return None
