"""Embed ChestEMB (Thêu) Qt panel inside a tkinter frame."""

import ctypes
import os
import sys
import threading


class TheuEmbedded:
    def __init__(self, tk_host, theu_path, log_fn=None):
        self.tk_host = tk_host
        self.theu_path = os.path.normpath(theu_path)
        self.log_fn = log_fn or (lambda msg: None)
        self.qt_app = None
        self.window = None
        self._started = False
        self._qt_timer_id = None
        self._root = tk_host.winfo_toplevel()

    def start(self):
        if self._started:
            return True
        if not os.path.isdir(self.theu_path):
            self.log_fn(f"Không tìm thấy Thêu tại: {self.theu_path}")
            return False

        try:
            self._boot_backend()
            self._embed_window()
            self._start_qt_pump()
            self._started = True
            self.log_fn("Đã tích hợp bảng Thêu.")
            return True
        except Exception as e:
            self.log_fn(f"Lỗi tích hợp Thêu: {e}")
            return False

    def _boot_backend(self):
        if self.theu_path not in sys.path:
            sys.path.insert(0, self.theu_path)

        os.chdir(self.theu_path)

        from PySide6.QtWidgets import QApplication

        self.qt_app = QApplication.instance()
        if self.qt_app is None:
            self.qt_app = QApplication(sys.argv)

        import security

        is_auth, msg, _expiry = security.check_license()
        if not is_auth:
            raise RuntimeError(msg or "ChestEMB chưa được kích hoạt license.")

        from tai_xiu_game import load_profile, save_profile, NameInputDialog

        profile = load_profile()
        if not profile.get("username"):
            from PySide6.QtWidgets import QDialog

            dialog = NameInputDialog()
            if dialog.exec() == QDialog.DialogCode.Accepted or dialog.username:
                profile["username"] = dialog.username
                save_profile(profile)
            else:
                raise RuntimeError("Cần nhập nickname để dùng bảng Thêu.")

        from gui import MiniApp
        from server import FlaskWorker
        from clipboard_bridge import ClipboardBridge
        from PySide6.QtCore import Qt

        self.window = MiniApp()
        self.window.flash_status("READY", "#00ff41")

        # Embedded mode: không nổi riêng, scale theo khung tk
        self.window.setWindowFlags(Qt.Widget)
        self.window.setAttribute(Qt.WA_TranslucentBackground, False)
        self.window.setMinimumSize(180, 200)
        self.window.setMaximumSize(16777215, 16777215)
        self.window.resize(max(self.tk_host.winfo_width(), 200), max(self.tk_host.winfo_height(), 220))

        flask_thread = FlaskWorker()
        flask_thread.data_received.connect(self.window.update_data)
        self.window.flask_thread = flask_thread
        flask_thread.start()

        clip_bridge = ClipboardBridge()
        clip_bridge.data_received.connect(self.window.update_data)
        clip_bridge.start()

        self.window.show()
        self.qt_app.processEvents()

    def _embed_window(self):
        self.tk_host.update_idletasks()
        hwnd_parent = self.tk_host.winfo_id()
        hwnd_child = int(self.window.winId())

        GWL_STYLE = -16
        WS_CHILD = 0x40000000
        WS_VISIBLE = 0x10000000

        user32 = ctypes.windll.user32
        style = user32.GetWindowLongW(hwnd_child, GWL_STYLE)
        user32.SetWindowLongW(hwnd_child, GWL_STYLE, style | WS_CHILD | WS_VISIBLE)
        user32.SetParent(hwnd_child, hwnd_parent)

        def _resize(event=None):
            w = max(self.tk_host.winfo_width(), 180)
            h = max(self.tk_host.winfo_height(), 200)
            user32.MoveWindow(hwnd_child, 0, 0, w, h, True)
            if self.qt_app:
                self.qt_app.processEvents()

        self.tk_host.bind("<Configure>", _resize, add="+")
        _resize()

    def _start_qt_pump(self):
        def _pump():
            if self.qt_app and self._started:
                self.qt_app.processEvents()
            self._qt_timer_id = self._root.after(30, _pump)

        _pump()

    def stop(self):
        self._started = False
        if self._qt_timer_id:
            try:
                self._root.after_cancel(self._qt_timer_id)
            except Exception:
                pass
            self._qt_timer_id = None
        if self.window:
            try:
                self.window.is_closing = True
                self.window.close()
            except Exception:
                pass
            self.window = None