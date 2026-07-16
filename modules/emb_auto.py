"""
Auto workflow EMB — port logic gốc ChestEMB (không PySide6).
Thứ tự: screenshot → Save EMB → Export TBF/DST.
Sửa: timeout 60s (không 5s), chỉ abort Ctrl+Q (không phím Q đơn).
"""

from __future__ import annotations

import os
import time

import pyautogui
import keyboard

try:
    import win32gui
    import win32con
    HAS_WIN32 = True
except Exception:
    HAS_WIN32 = False


class AutoWorkflow:
    """Automated workflow for embroidery (Wilcom Ultimate Special Edition)."""

    def __init__(self, gui_ref, context: dict):
        self.gui = gui_ref
        self.context = context or {}
        self.start_time = time.time()
        self.embroidery_window_title = "Ultimate Special Edition"
        self.abort_flag = False
        self.embroidery_hwnd = None
        self.id_checkbox = ""
        self.folder_path = ""
        self.file_type = "TBF"
        self.max_seconds = 60.0

    def update_status(self, message, color="#00ff41"):
        try:
            self.gui.flash_status(message, color)
            if hasattr(self.gui, "status_signal"):
                self.gui.status_signal.emit(message, color)
        except Exception:
            print(f"[STATUS] {message}")

    def find_window_by_partial_title(self, partial_title):
        if not HAS_WIN32:
            return None

        def enum_handler(hwnd, results):
            if win32gui.IsWindowVisible(hwnd):
                window_text = win32gui.GetWindowText(hwnd)
                if partial_title.lower() in window_text.lower():
                    results.append((hwnd, window_text))

        results = []
        win32gui.EnumWindows(enum_handler, results)
        return results

    def activate_embroidery_window(self):
        self.update_status("Find Win...", "#ffff00")
        if not HAS_WIN32:
            time.sleep(0.2)
            return True

        possible_titles = [
            "Ultimate Special Edition",
            "[Ultimate Special Edition]",
            "Ultimate Special",
            "[Ultimate Special",
            "Embroider",
            "Embroidery",
            "Wilcom",
        ]
        for title in possible_titles:
            try:
                hwnd = win32gui.FindWindow(None, title)
                if hwnd:
                    if win32gui.IsIconic(hwnd):
                        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    win32gui.SetForegroundWindow(hwnd)
                    time.sleep(0.25)
                    self.embroidery_hwnd = hwnd
                    self.update_status("Win Ready", "#00ff41")
                    return True
            except Exception:
                continue

        for keyword in ("Ultimate", "Special", "Edition", "Embroid", "Wilcom"):
            results = self.find_window_by_partial_title(keyword)
            if not results:
                continue
            for hwnd, title in results:
                if "TX Embroider" in title or "ACC2019" in title:
                    continue
                try:
                    if win32gui.IsIconic(hwnd):
                        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    win32gui.SetForegroundWindow(hwnd)
                    time.sleep(0.25)
                    self.embroidery_hwnd = hwnd
                    self.update_status("Win Ready", "#00ff41")
                    return True
                except Exception:
                    continue

        self.update_status("NO WIN!", "#ff0000")
        self.embroidery_hwnd = None
        return False

    def capture_window_screenshot(self):
        if not HAS_WIN32 or not self.embroidery_hwnd:
            return pyautogui.screenshot()
        try:
            x, y, x2, y2 = win32gui.GetWindowRect(self.embroidery_hwnd)
            return pyautogui.screenshot(region=(x, y, x2 - x, y2 - y))
        except Exception:
            return pyautogui.screenshot()

    def check_abort(self):
        if time.time() - self.start_time > self.max_seconds:
            self.abort_flag = True
            self.update_status("TIMEOUT", "#ff3333")
            return True
        try:
            if keyboard.is_pressed("ctrl+q") or self.abort_flag:
                self.abort_flag = True
                self.update_status("CTRL+Q STOP", "#ff3333")
                return True
        except Exception:
            pass
        return False

    def process_dialog(self, keywords, filepath, timeout=5.0):
        if not HAS_WIN32:
            time.sleep(0.5)
            return True

        start_time = time.time()
        dialog_hwnd = None
        while time.time() - start_time < timeout:
            if self.check_abort():
                return False

            def enum_windows_callback(hwnd, results):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if any(kw.lower() in title.lower() for kw in keywords):
                        if "TX Embroider" not in title and "ACC2019" not in title:
                            results.append(hwnd)

            results = []
            win32gui.EnumWindows(enum_windows_callback, results)
            if results:
                dialog_hwnd = results[0]
                break
            time.sleep(0.02)

        if not dialog_hwnd:
            print(f"[AUTO] Dialog {keywords} not found")
            return False

        try:
            win32gui.ShowWindow(dialog_hwnd, win32con.SW_SHOW)
            win32gui.SetForegroundWindow(dialog_hwnd)
        except Exception as e:
            print(f"[AUTO] activate dialog: {e}")

        edit_hwnd = None

        def enum_child_callback(hwnd, results):
            if win32gui.GetClassName(hwnd) == "Edit":
                results.append(hwnd)

        child_edits = []
        win32gui.EnumChildWindows(dialog_hwnd, enum_child_callback, child_edits)
        if child_edits:
            edit_hwnd = child_edits[0]
        if not edit_hwnd:
            print("[AUTO] No Edit control in dialog")
            return False

        try:
            win32gui.ShowWindow(dialog_hwnd, win32con.SW_SHOW)
            win32gui.SetForegroundWindow(dialog_hwnd)
        except Exception:
            pass

        win32gui.SendMessage(edit_hwnd, win32con.WM_SETTEXT, 0, filepath)
        time.sleep(0.08)
        win32gui.PostMessage(dialog_hwnd, win32con.WM_COMMAND, 1, 0)  # IDOK
        time.sleep(0.15)
        self.check_and_confirm_overwrite()
        return True

    def check_and_confirm_overwrite(self, timeout=1.5):
        if not HAS_WIN32:
            return
        start = time.time()
        while time.time() - start < timeout:
            results = []

            def find_confirm(hwnd, acc):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    low = title.lower()
                    if any(k in low for k in ("confirm", "xác nhận", "already exists", "replace", "ghi đè")):
                        if "TX" not in title and "ACC2019" not in title:
                            acc.append(hwnd)

            win32gui.EnumWindows(find_confirm, results)
            if results:
                hwnd = results[0]
                try:
                    win32gui.SetForegroundWindow(hwnd)
                    win32gui.PostMessage(hwnd, win32con.WM_COMMAND, 6, 0)  # IDYES
                    win32gui.PostMessage(hwnd, win32con.WM_COMMAND, 1, 0)
                except Exception:
                    pass
                return
            time.sleep(0.05)

    def verify_file_saved(self, filepath, timeout=3.0):
        start = time.time()
        while time.time() - start < timeout:
            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                return True
            time.sleep(0.1)
        return False

    def step0_prepare_data(self):
        if self.check_abort():
            return False
        try:
            self.gui.progress_signal.emit(5)
        except Exception:
            pass
        self.id_checkbox = self.context.get("final_id", "Unknown")
        self.folder_path = self.context.get("folder_path")
        if not self.folder_path:
            self.update_status("NO FOLDER", "#ff0000")
            return False
        self.file_type = (self.context.get("file_type") or "TBF").upper()
        if self.file_type not in ("DST", "TBF"):
            self.file_type = "TBF"
        self.update_status("Data Ready", "#00ff41")
        return True

    def step3_screenshot(self):
        if self.check_abort():
            return False
        try:
            self.gui.progress_signal.emit(35)
        except Exception:
            pass
        if not self.activate_embroidery_window():
            self.update_status("NO WIN-3", "#ff0000")
            return False
        time.sleep(0.2)
        shot = self.capture_window_screenshot()
        filepath = os.path.join(self.folder_path, f"{self.id_checkbox}.png")
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except Exception:
                pass
        shot.save(filepath)
        self.update_status("Step 3 ✓", "#00ff41")
        return True

    def step1_save_as(self):
        if self.check_abort():
            return False
        try:
            self.gui.progress_signal.emit(45)
        except Exception:
            pass
        if not self.activate_embroidery_window():
            self.update_status("NO WIN-1", "#ff0000")
            return False
        keyboard.send("-")
        time.sleep(0.05)
        keyboard.send("-")
        time.sleep(0.1)
        keyboard.send("alt+f")
        time.sleep(0.18)
        keyboard.send("a")
        full_save_path = os.path.join(self.folder_path, f"{self.id_checkbox}.EMB")
        if os.path.exists(full_save_path):
            try:
                os.remove(full_save_path)
            except Exception:
                pass
        if not self.process_dialog(["Save As", "Lưu", "Save"], full_save_path, timeout=5.0):
            return False
        if self.verify_file_saved(full_save_path):
            self.update_status("Step 1 ✓", "#00ff41")
            return True
        self.update_status("EMB Save Fail", "#ff3333")
        return False

    def step2_export_machine(self):
        if self.check_abort():
            return False
        try:
            self.gui.progress_signal.emit(75)
        except Exception:
            pass
        if not self.activate_embroidery_window():
            self.update_status("NO WIN-2", "#ff0000")
            return False
        keyboard.send("shift+e")
        ext = f".{self.file_type}"
        full_export_path = os.path.join(self.folder_path, f"{self.id_checkbox}{ext}")
        if os.path.exists(full_export_path):
            try:
                os.remove(full_export_path)
            except Exception:
                pass
        if not self.process_dialog(["Export", "Machine", "Xuất"], full_export_path, timeout=5.0):
            return False
        if self.verify_file_saved(full_export_path):
            self.update_status("Step 2 ✓", "#00ff41")
            return True
        self.update_status("Export Fail", "#ff3333")
        return False

    def cleanup_on_error(self):
        try:
            self.gui.progress_signal.emit(0)
        except Exception:
            pass
        if not HAS_WIN32:
            try:
                keyboard.send("esc")
                keyboard.send("esc")
            except Exception:
                pass
            return
        keywords = ("save as", "lưu", "save", "export", "machine", "xuất", "confirm", "xác nhận", "replace")

        def enum_and_close(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if any(kw in title.lower() for kw in keywords):
                    if "TX Embroider" not in title and "ACC2019" not in title:
                        win32gui.PostMessage(hwnd, win32con.WM_COMMAND, 2, 0)
                        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)

        for _ in range(3):
            win32gui.EnumWindows(enum_and_close, None)
            time.sleep(0.12)

    def run(self):
        print("\n=== AUTO WORKFLOW (ACC emb_auto) Ctrl+Q abort ===")
        if not getattr(self.gui, "current_folder", None):
            self.update_status("Create Fldr", "#ffff00")
            try:
                self.gui.on_create_folder()
            except Exception:
                pass
            time.sleep(0.25)

        if not self.step0_prepare_data():
            self.cleanup_on_error()
            return False
        time.sleep(0.15)

        if not self.step3_screenshot():
            self.cleanup_on_error()
            return False
        time.sleep(0.15)

        if not self.step1_save_as():
            self.cleanup_on_error()
            return False
        time.sleep(0.15)

        if not self.step2_export_machine():
            self.cleanup_on_error()
            return False

        try:
            self.gui.progress_signal.emit(100)
        except Exception:
            pass
        self.update_status("ALL DONE! ✓", "#00ff41")
        try:
            self.gui.show_success_toast_signal.emit("Lưu Thành công")
        except Exception:
            pass
        self.update_status("AUTO OK", "#00ff41")
        return True
