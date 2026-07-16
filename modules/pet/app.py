import os
import json
import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
import datetime
import shutil
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import zipfile
import psutil
try:
    import pythoncom
except ImportError:
    pythoncom = None
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


# Try importing win32com for Photoshop interaction
try:
    import win32com.client
    PHOTOSHOP_AVAILABLE = True
except ImportError:
    PHOTOSHOP_AVAILABLE = False

# Compute BASE_DIR for robust executable path resolution
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Configuration file path
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

# Set appearance and theme
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Force utf-8 encoding for standard output
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

# --- Global Windows Hotkey Thread using Win32 API ---
if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes
    
    # VK Codes
    VK_PRIOR = 0x21  # Page Up
    VK_NEXT = 0x22   # Page Down
    VK_X = 0x58      # X key
    
    # Modifiers
    MOD_ALT = 0x0001
    MOD_CONTROL = 0x0002
    
    user32 = ctypes.windll.user32
    
    class HotkeyThread(threading.Thread):
        def __init__(self, app):
            super().__init__(daemon=True)
            self.app = app
            
        def run(self):
            # Unregister first to clear any stale registration from previous runs
            user32.UnregisterHotKey(None, 101)
            user32.UnregisterHotKey(None, 102)
            user32.UnregisterHotKey(None, 103)
            
            # Page Up key: ID 101, Modifier 0
            user32.RegisterHotKey(None, 101, 0, VK_PRIOR)
            # Page Down key: ID 102, Modifier 0
            user32.RegisterHotKey(None, 102, 0, VK_NEXT)
            # Ctrl + Alt + X: ID 103, Modifier Control + Alt
            user32.RegisterHotKey(None, 103, MOD_CONTROL | MOD_ALT, VK_X)
            
            try:
                msg = wintypes.MSG()
                while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                    if msg.message == 0x0312: # WM_HOTKEY
                        id = msg.wParam
                        if id == 101:
                            self.app.after(0, self.app.hide_gui_to_icon)
                        elif id == 102:
                            self.app.after(0, self.app.show_gui_from_icon)
                        elif id == 103:
                            self.app.after(0, self.app.quit_app)
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
            finally:
                user32.UnregisterHotKey(None, 101)
                user32.UnregisterHotKey(None, 102)
                user32.UnregisterHotKey(None, 103)


# --- Local HTTP Server with PNA & CORS bypass ---
class POHTTPRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress logging in console to keep terminal clean
        pass
        
    def send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Access-Control-Allow-Private-Network')
        self.send_header('Access-Control-Allow-Private-Network', 'true') # PNA bypass!

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self):
        # 1. Connection Heartbeat Ping
        if self.path.startswith("/ping"):
            self.server.app.on_ping_received()
            self.send_response(200)
            self.send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "pong"}).encode())
            
        # 2. Receive Product/PO Name
        elif self.path.startswith("/send_po"):
            parsed_url = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed_url.query)
            po_name = params.get("po", [""])[0]
            
            if po_name:
                self.server.app.on_po_received_thread_safe(po_name)
                
            self.send_response(200)
            self.send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "success", "po": po_name}).encode())
            
        # 3. Receive Success Notification from loki.c8p.dev
        elif self.path.startswith("/notify_success"):
            self.server.app.trigger_success_flash_thread_safe()
            self.send_response(200)
            self.send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "success"}).encode())
        else:
            self.send_response(404)
            self.end_headers()

class POHTTPServer(HTTPServer):
    def __init__(self, server_address, RequestHandlerClass, app_instance):
        super().__init__(server_address, RequestHandlerClass)
        self.app = app_instance


# --- Background System Stats Collector Thread ---
class StatsCollector(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.cpu = 0
        self.ram = 0
        self.gpu = 0
        self.running = True
        self._wmi = None

    def run(self):
        # Initialize COM for this thread
        if pythoncom:
            pythoncom.CoInitialize()
        try:
            import win32com.client
            self._wmi = win32com.client.GetObject('winmgmts:')
        except Exception as e:
            print(f"[StatsCollector] WMI Init Error: {e}")
            self._wmi = None

        # Warm up CPU call
        try:
            psutil.cpu_percent()
        except Exception:
            pass

        while self.running:
            try:
                self.cpu = int(psutil.cpu_percent())
                self.ram = int(psutil.virtual_memory().percent)
            except Exception as e:
                print(f"[StatsCollector] Stats error: {e}")

            gpu_val = 0
            if self._wmi:
                try:
                    engines = self._wmi.InstancesOf('Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine')
                    utils = {}
                    for x in engines:
                        try:
                            name = x.Name
                            parts = name.split('_')
                            eng_type = "3D"
                            for i, p in enumerate(parts):
                                if p == "engtype" and i + 1 < len(parts):
                                    eng_type = parts[i+1]
                                    break
                            val = int(x.UtilizationPercentage)
                            utils[eng_type] = utils.get(eng_type, 0) + val
                        except Exception:
                            continue
                    if utils:
                        gpu_val = min(max(utils.values()), 100)
                except Exception as e:
                    # Re-initialize WMI in case of COM disconnection
                    try:
                        import win32com.client
                        self._wmi = win32com.client.GetObject('winmgmts:')
                    except Exception:
                        pass
            self.gpu = gpu_val
            time.sleep(1.0)


# --- Transparent System Stats Overlay Window ---
class SystemOverlay(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-transparentcolor", "black")
        self.configure(bg="black")
        
        # Dragging variables
        self._drag_x = 0
        self._drag_y = 0
        
        # Load position from config or center-top default
        screen_width = self.winfo_screenwidth()
        default_x = (screen_width - 220) // 2
        default_y = 5
        x = self.app.config.get("overlay_x", default_x)
        y = self.app.config.get("overlay_y", default_y)
        self.geometry(f"+{x}+{y}")
        
        # Semi-transparent drop shadow label (black)
        self.lbl_shadow = tk.Label(
            self,
            text="CPU: 0%  RAM: 0%  GPU: 0%",
            font=("Consolas", 10, "bold"),
            fg="#111111",
            bg="black",
            padx=0,
            pady=0
        )
        self.lbl_shadow.place(x=1, y=1)
        
        self.lbl = tk.Label(
            self,
            text="CPU: 0%  RAM: 0%  GPU: 0%",
            font=("Consolas", 10, "bold"),
            fg="#00FF00", # Vivid lime green
            bg="black",
            padx=0,
            pady=0
        )
        self.lbl.pack()
        
        # Bind dragging to both labels
        self.lbl.bind("<Button-1>", self.start_drag)
        self.lbl.bind("<B1-Motion>", self.drag)
        self.lbl.bind("<ButtonRelease-1>", self.save_position)
        
        self.lbl_shadow.bind("<Button-1>", self.start_drag)
        self.lbl_shadow.bind("<B1-Motion>", self.drag)
        self.lbl_shadow.bind("<ButtonRelease-1>", self.save_position)
        
        self.update_stats()

    def start_drag(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def drag(self, event):
        deltax = event.x - self._drag_x
        deltay = event.y - self._drag_y
        x = self.winfo_x() + deltax
        y = self.winfo_y() + deltay
        self.geometry(f"+{x}+{y}")

    def save_position(self, event):
        x = self.winfo_x()
        y = self.winfo_y()
        self.app.config["overlay_x"] = x
        self.app.config["overlay_y"] = y
        self.app.save_config()

    def get_stress_color(self, cpu, ram, gpu):
        stress = max(cpu, ram, gpu)
        if stress < 70:
            return "#00FF00"  # Lime green
        elif stress < 85:
            return "#FF9F43"  # Vibrant warning orange
        else:
            return "#FF4D4D"  # Alert red

    def update_stats(self):
        if self.app.stats_collector:
            cpu = self.app.stats_collector.cpu
            ram = self.app.stats_collector.ram
            gpu = self.app.stats_collector.gpu
            
            stats_text = f"CPU: {cpu}%  RAM: {ram}%  GPU: {gpu}%"
            self.lbl.configure(text=stats_text)
            self.lbl_shadow.configure(text=stats_text)
            
            # Dynamic Stress Color based on resources
            color = self.get_stress_color(cpu, ram, gpu)
            self.lbl.configure(fg=color)
            
        self.after(1000, self.update_stats)


class PhotoshopAutoGUI(ctk.CTk):
    def __init__(self, master=None, embedded=False):
        self.embedded = bool(embedded and master is not None)
        self._host_root = master.winfo_toplevel() if self.embedded else None

        if self.embedded:
            ctk.CTkFrame.__init__(self, master, fg_color="transparent", corner_radius=0)
        else:
            super().__init__()

        if not self.embedded:
            # Bind Ctrl + Alt + X key event at the Tkinter level for redundancy
            self.bind_all("<Control-Alt-x>", lambda e: self.quit_app())
            self.bind_all("<Control-Alt-X>", lambda e: self.quit_app())
        
        # Load configuration
        self.load_config()
        
        self.stats_collector = None
        self.overlay_window = None
        
        if self.embedded:
            self.configure(fg_color="transparent")
            self.pack(fill="both", expand=True)
        else:
            # Window settings for a compact floating dashboard widget (200x225)
            self.geometry("200x225")
            self.overrideredirect(True)      # Remove standard OS title bar
            self.attributes("-topmost", True)  # Always stay on top of Photoshop

        # Drag variables
        self._drag_x = 0
        self._drag_y = 0
        
        # Connection status variables
        self.last_ping_time = 0
        self.active_po = "Chua nhan"
        
        # Settings window reference
        self.settings_window = None
        self.selected_files_list = []
        self.glow_dot = None
        self.gui_hidden = False
        
        # ACC2019 theme (synced with main hub)
        self.bg_color = "#0c0c14"
        self.border_color = "#252538"
        self.card_color = "#141424"
        self.accent_purple = "#00d2ff"
        self.accent_teal = "#00e676"
        self.text_muted = "#82829c"
        self.text_color = "#ffffff"
        
        if not self.embedded:
            self.configure(fg_color=self.bg_color)

        # Main Outer Container
        self.outer_frame = ctk.CTkFrame(
            self,
            fg_color=self.bg_color,
            border_color=self.border_color,
            border_width=1,
            corner_radius=8,
        )
        self.outer_frame.pack(fill="both", expand=True)

        # --- 1. Title Bar (compact header; hidden drag/close when embedded) ---
        self.title_bar = ctk.CTkFrame(self.outer_frame, height=22, fg_color=self.card_color, corner_radius=0)
        self.title_bar.pack(fill="x", side="top")
        self.title_bar.pack_propagate(False)

        self.title_label = ctk.CTkLabel(
            self.title_bar,
            text="PET",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=self.accent_purple,
        )
        self.title_label.pack(side="left", padx=8)

        if not self.embedded:
            self.title_bar.bind("<Button-1>", self.start_drag)
            self.title_bar.bind("<B1-Motion>", self.drag)
            self.title_label.bind("<Button-1>", self.start_drag)
            self.title_label.bind("<B1-Motion>", self.drag)

            self.close_btn = ctk.CTkButton(
                self.title_bar,
                text="×",
                width=20,
                height=20,
                fg_color="transparent",
                hover_color="#ff4757",
                text_color="#A4A4A6",
                font=ctk.CTkFont(size=14, weight="bold"),
                corner_radius=0,
                command=self.quit_app,
            )
            self.close_btn.pack(side="right")

        self.tm_status_dot = ctk.CTkLabel(
            self.title_bar,
            text="●",
            font=ctk.CTkFont(size=9),
            text_color="#747d8c",
            width=8,
        )
        self.tm_status_dot.pack(side="right", padx=(0, 6))

        self.tm_status_label = ctk.CTkLabel(
            self.title_bar,
            text="TM: Offline",
            font=ctk.CTkFont(size=8, weight="bold"),
            text_color="#A4A4A6",
        )
        self.tm_status_label.pack(side="right", padx=(0, 2))
        
        # --- 2. Main Content Area ---
        self.content_frame = ctk.CTkFrame(self.outer_frame, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True, padx=8, pady=2)
        
        # Product selector and Settings Gear Row Frame (Placed side-by-side!)
        self.prod_row_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.prod_row_frame.pack(fill="x", pady=(2, 2))
        
        self.product_var = tk.StringVar(value=self.config.get("active_product", ""))
        self.product_list = list(self.config.get("products", {}).keys())
        
        self.product_dropdown = ctk.CTkComboBox(
            self.prod_row_frame,
            values=self.product_list if self.product_list else ["-- None --"],
            variable=self.product_var,
            command=self.on_product_changed,
            height=22,
            width=150,
            font=ctk.CTkFont(size=9),
            dropdown_font=ctk.CTkFont(size=9),
            fg_color=self.card_color,
            border_color=self.border_color,
            button_color="#23233c",
            button_hover_color="#2d2d48",
            corner_radius=4
        )
        self.product_dropdown.pack(side="left", fill="x", expand=True)
        
        self.settings_btn = ctk.CTkButton(
            self.prod_row_frame,
            text="⚙️",
            font=ctk.CTkFont(size=12),
            width=24,
            height=22,
            fg_color="#23233c",
            hover_color="#2d2d48",
            corner_radius=4,
            command=self.open_settings
        )
        self.settings_btn.pack(side="right", padx=(4, 0))
        
        # Custom PO status display block
        self.po_frame = ctk.CTkFrame(self.content_frame, height=18, fg_color=self.card_color, corner_radius=4)
        self.po_frame.pack(fill="x", pady=1, padx=2)
        self.po_frame.pack_propagate(False)
        
        self.po_title_label = ctk.CTkLabel(
            self.po_frame,
            text="PO:",
            font=ctk.CTkFont(size=8, weight="bold"),
            text_color="#8A8A8E"
        )
        self.po_title_label.pack(side="left", padx=(6, 2))
        
        # PO value label
        self.po_val_label = ctk.CTkLabel(
            self.po_frame,
            text="Chờ...",
            font=ctk.CTkFont(size=8, weight="bold"),
            text_color="#A4A4A6"
        )
        self.po_val_label.pack(side="left", padx=0, fill="x", expand=True, anchor="w")
        
        # PO value entry (initially hidden, used when checkbox is checked)
        self.po_val_entry = ctk.CTkEntry(
            self.po_frame,
            font=ctk.CTkFont(size=8, weight="bold"),
            text_color="#3498db",
            fg_color="#2D2D35",
            border_color="#4F4F56",
            height=14,
            corner_radius=2
        )
        
        # Checkbox to edit PO name freely (Tiny, nested inside the PO frame!)
        self.edit_po_var = tk.IntVar(value=0)
        self.chk_edit_po = ctk.CTkCheckBox(
            self.po_frame,
            text="", # No text for ultimate compactness
            variable=self.edit_po_var,
            command=self.toggle_po_edit,
            fg_color=self.accent_teal,
            hover_color="#0f8c6b",
            width=16,
            checkbox_width=12,
            checkbox_height=12
        )
        self.chk_edit_po.pack(side="right", padx=(0, 4))
        
        # Dynamic Source Folder Stats Label
        self.stats_label = ctk.CTkLabel(
            self.content_frame,
            text="Chưa kết nối thư mục nguồn",
            font=ctk.CTkFont(size=8),
            text_color="#8A8A8E",
            justify="center"
        )
        self.stats_label.pack(pady=2)
        
        # Action Buttons Row Frame (Action Photoshop and Packaging side-by-side!)
        self.btn_row_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.btn_row_frame.pack(fill="x", pady=2)
        
        # Action Button: Trigger Photoshop Action
        self.action_btn = ctk.CTkButton(
            self.btn_row_frame,
            text="Action 🚀",
            font=ctk.CTkFont(size=9, weight="bold"),
            fg_color=self.accent_purple,
            hover_color="#00b8e6",
            height=22,
            width=75,
            corner_radius=4,
            command=self.run_photoshop_action
        )
        self.action_btn.pack(side="left", padx=(0, 2))
        
        # Package Button: Compress Files (Wider for full packaging text display!)
        self.package_btn = ctk.CTkButton(
            self.btn_row_frame,
            text="Đóng gói 📦",
            font=ctk.CTkFont(size=9, weight="bold"),
            fg_color=self.accent_teal,
            hover_color="#00c966",
            height=22,
            width=105,
            corner_radius=4,
            command=self.run_packaging
        )
        self.package_btn.pack(side="right", padx=(2, 0))
        
        # Xếp Ảnh Button: Full-width image arrange tool
        self.arrange_btn = ctk.CTkButton(
            self.content_frame,
            text="Xếp Ảnh 🖼️",
            font=ctk.CTkFont(size=9, weight="bold"),
            fg_color="#ff9d00",
            hover_color="#e68a00",
            height=22,
            corner_radius=4,
            command=self.open_image_arranger
        )
        self.arrange_btn.pack(fill="x", pady=(0, 2))
        
        # Open Input Directory Icon Button & Trash Can Button side-by-side! (Extremely compact!)
        self.dir_row_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.dir_row_frame.pack(pady=2)
        
        self.open_dir_btn = ctk.CTkButton(
            self.dir_row_frame,
            text="📂",
            font=ctk.CTkFont(size=12),
            width=30,
            height=22,
            fg_color="#3A3A42",
            hover_color="#4F4F56",
            corner_radius=4,
            command=self.open_input_folder
        )
        self.open_dir_btn.pack(side="left", padx=(0, 2))
        
        self.trash_btn = ctk.CTkButton(
            self.dir_row_frame,
            text="🗑️",
            font=ctk.CTkFont(size=10),
            width=30,
            height=22,
            fg_color="#d63031",
            hover_color="#b2bec3",
            corner_radius=4,
            command=self.manual_clean_input_folder
        )
        self.trash_btn.pack(side="left", padx=(2, 0))
        


        # Active Execution State Label (Packed at the very bottom!)
        self.state_label = ctk.CTkLabel(
            self.content_frame,
            text="Trạng thái: Sẵn sàng",
            font=ctk.CTkFont(size=8, weight="bold"),
            text_color="#2ecc71",
            height=14
        )
        self.state_label.pack(side="bottom", pady=(2, 0))
        
        # --- 3. Launch Background Watchdogs ---
        self.start_http_server()
        self.check_connection_timeout()
        self.update_source_stats()
        
        # Start global hotkeys watchdog thread (Windows only, standalone mode)
        if sys.platform == "win32" and not self.embedded:
            self.hotkey_thread = HotkeyThread(self)
            self.hotkey_thread.start()

        self.start_stats_collector()
        if not self.embedded:
            self.show_overlay_window()
        
    # --- Dynamic PO Name resolution Property ---
    @property
    def current_po_name(self):
        if self.edit_po_var.get() == 1:
            return self.po_val_entry.get().strip()
        return self.active_po

    def toggle_po_edit(self):
        if self.edit_po_var.get() == 1:
            # Hide text label, reveal input box
            self.po_val_label.pack_forget()
            self.po_val_entry.pack(side="left", fill="x", expand=True, padx=(2, 2))
            self.po_val_entry.delete(0, tk.END)
            self.po_val_entry.insert(0, self.active_po)
            self.po_val_entry.focus()
        else:
            # Read from input, hide entry, reveal locked label
            manual_text = self.po_val_entry.get().strip()
            if manual_text:
                self.active_po = manual_text
            self.po_val_entry.pack_forget()
            self.po_val_label.pack(side="left", padx=0, fill="x", expand=True, anchor="w")
            
            display_po = self.active_po
            if len(display_po) > 22:
                display_po = display_po[:21] + ".."
            self.po_val_label.configure(text=display_po, text_color="#3498db")
            
        # Re-trigger Stats calculations immediately
        self.update_source_stats()

    # --- Windows Hide & Show Toggle Dot ---
    def hide_gui_to_icon(self):
        if not self.gui_hidden:
            # Hide main GUI
            self.withdraw()
            self.gui_hidden = True
            
            # Show glowing neon dot in top left corner (5, 5)
            if self.glow_dot is None:
                self.glow_dot = ctk.CTkToplevel(self)
                self.glow_dot.overrideredirect(True)
                self.glow_dot.attributes("-topmost", True)
                self.glow_dot.geometry("14x14+5+5") # Compact dimensions
                self.glow_dot.configure(fg_color="#1E1E24")
                
                # Outer indicator frame
                dot_frame = ctk.CTkFrame(
                    self.glow_dot,
                    width=14,
                    height=14,
                    fg_color="#00d2d3", # Glowing neon cyan
                    border_color="#1E1E24",
                    border_width=2,
                    corner_radius=7
                )
                dot_frame.pack(fill="both", expand=True)
                dot_frame.bind("<Button-1>", lambda e: self.toggle_gui_visibility())
            else:
                self.glow_dot.deiconify()

    def show_gui_from_icon(self):
        if self.gui_hidden:
            # Restore main GUI
            self.deiconify()
            self.focus_force()
            self.attributes("-topmost", True)
            self.gui_hidden = False
            
            # Hide glowing dot
            if self.glow_dot:
                self.glow_dot.withdraw()

    def toggle_gui_visibility(self):
        if not self.gui_hidden:
            self.hide_gui_to_icon()
        else:
            self.show_gui_from_icon()

    def quit_app(self):
        if self.stats_collector:
            self.stats_collector.running = False
        if self.glow_dot:
            try:
                self.glow_dot.destroy()
            except Exception:
                pass
        if self.embedded:
            self.pack_forget()
            return
        self.destroy()
        sys.exit(0)

    # --- Overlay & System Stats Controllers ---
    def start_stats_collector(self):
        if not self.stats_collector:
            self.stats_collector = StatsCollector()
            self.stats_collector.start()

    def show_overlay_window(self):
        if not self.overlay_window or not self.overlay_window.winfo_exists():
            self.overlay_window = SystemOverlay(self)
        else:
            self.overlay_window.deiconify()
            self.overlay_window.attributes("-topmost", True)

    def hide_overlay_window(self):
        if self.overlay_window and self.overlay_window.winfo_exists():
            self.overlay_window.withdraw()

    def toggle_system_overlay(self):
        show = self.show_overlay_var.get() == 1
        self.config["show_system_overlay"] = show
        self.save_config()
        
        if show:
            self.start_stats_collector()
            self.show_overlay_window()
            self.update_state("Hiện overlay", "#2ecc71")
        else:
            self.hide_overlay_window()
            self.update_state("Ẩn overlay", "#2ecc71")

    # --- Local Server Heartbeat & Callbacks ---
    def start_http_server(self):
        def run_server():
            try:
                # Bind strictly to 127.0.0.1 on port 18080
                server = POHTTPServer(("127.0.0.1", 18080), POHTTPRequestHandler, self)
                print("[Server] Listening on http://127.0.0.1:18080")
                server.serve_forever()
            except Exception as e:
                print(f"[Server ERROR] Failed to bind: {e}")
                self.after(0, self.update_state, "Port Lock", "#e74c3c")
                
        t = threading.Thread(target=run_server, daemon=True)
        t.start()
        
    def on_ping_received(self):
        # Refresh connection watchdog
        self.after(0, self.update_connection_live)
        
    def update_connection_live(self):
        self.last_ping_time = time.time()
        self.tm_status_label.configure(text="TM: Live ⚡", text_color="#00d2d3")
        self.tm_status_dot.configure(text_color="#00d2d3")  # Cyan for live connection
        
    def on_po_received_thread_safe(self, po_name):
        self.after(0, self.update_po_data, po_name)
        
    def update_po_data(self, po_name):
        cleaned_po = po_name.strip()
        self.active_po = cleaned_po
        self.last_ping_time = time.time()
        
        # Refresh TM live display
        self.update_connection_live()
        
        # If edit checkbox is checked, insert into entry box
        if self.edit_po_var.get() == 1:
            self.po_val_entry.delete(0, tk.END)
            self.po_val_entry.insert(0, cleaned_po)
        else:
            # Shorten text if it overflows the small panel
            display_po = cleaned_po
            if len(display_po) > 22:
                display_po = display_po[:21] + ".."
            self.po_val_label.configure(text=display_po, text_color="#3498db")
            
        self.update_state("Da nhan PO tu Web", "#3498db")
        self.update_source_stats()
        
    def check_connection_timeout(self):
        # Heartbeat verification: if no request in past 15 seconds, set Offline
        if time.time() - self.last_ping_time > 15:
            self.tm_status_label.configure(text="TM: Offline", text_color="#A4A4A6")
            self.tm_status_dot.configure(text_color="#747d8c")
        self.after(2000, self.check_connection_timeout)

    def trigger_success_flash_thread_safe(self):
        self.after(0, self.trigger_success_flash)

    def trigger_success_flash(self):
        if self.gui_hidden:
            self.show_gui_from_icon()
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.focus_force()
        self.flash_window(20, True)

    def flash_window(self, count=20, color_toggle=True):
        if count <= 0:
            self.outer_frame.configure(fg_color=self.bg_color)
            self.title_bar.configure(fg_color="#141416")
            self.update_state("Sẵn sàng", "#2ecc71")
            return
            
        flash_color = "#ff4d4d" if color_toggle else "#2ecc71"
        self.outer_frame.configure(fg_color=flash_color)
        self.title_bar.configure(fg_color=flash_color)
        self.update_state("SUCCESS! 🟢🔴", color="#ffffff" if color_toggle else "#000000")
        
        self.after(200, lambda: self.flash_window(count - 1, not color_toggle))

    # --- Dynamic SOURCE Directory Compact Horizontal Stats Label ---
    def update_source_stats(self):
        prod_name = self.product_var.get()
        if not prod_name or prod_name == "-- None --":
            self.stats_label.configure(text="Chưa chọn sản phẩm")
            return
            
        prod_data = self.config.get("products", {}).get(prod_name, {})
        input_folder = prod_data.get("input_folder", "")
        
        if not input_folder or not os.path.exists(input_folder):
            self.stats_label.configure(text="Nguồn: Chưa kết nối")
            return
            
        try:
            files = os.listdir(input_folder)
            total_files = 0
            ext_counts = {}
            
            for f in files:
                f_path = os.path.join(input_folder, f)
                if os.path.isfile(f_path):
                    total_files += 1
                    _, ext = os.path.splitext(f)
                    ext_clean = ext.replace(".", "").lower()
                    if ext_clean:
                        ext_counts[ext_clean] = ext_counts.get(ext_clean, 0) + 1
            
            if total_files == 0:
                stats_text = "Nguồn: 0 file"
            else:
                details = ", ".join([f"{count} {ext}" for ext, count in sorted(ext_counts.items())])
                stats_text = f"Nguồn: {total_files} file ({details})"
                
        except Exception:
            stats_text = "Lỗi đọc thư mục nguồn"
            
        self.stats_label.configure(text=stats_text)
        # Scan continuously every 2 seconds
        self.after(2000, self.update_source_stats)

    # --- Config Management ---
    def load_config(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
            except Exception as e:
                print(f"Error loading config: {e}")
                self.config = {"active_product": "", "products": {}}
        else:
            self.config = {"active_product": "", "products": {}}
            self.save_config()

    def save_config(self):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving config: {e}")
            
    def on_product_changed(self, choice):
        if choice != "-- None --":
            self.config["active_product"] = choice
            self.save_config()
            self.update_state("Da thay doi sp", "#2ecc71")
            self.update_source_stats()
            
    def update_state(self, text, color="#2ecc71"):
        # Updates the Executing State Label dynamically
        self.state_label.configure(text=f"Trạng thái: {text}", text_color=color)

    # --- Window Drag-to-Move Logic ---
    def start_drag(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def drag(self, event):
        deltax = event.x - self._drag_x
        deltay = event.y - self._drag_y
        x = self.winfo_x() + deltax
        y = self.winfo_y() + deltay
        self.geometry(f"+{x}+{y}")

    # --- Helper: Get active file extensions for Action (Photoshop) ---
    def get_active_extensions(self, prod_data):
        file_types = prod_data.get("file_types", ["jpg", "png", "tif"])
        custom_str = prod_data.get("custom_extensions", "")
        
        exts = [e.strip().lower() for e in file_types if e.strip()]
        if custom_str:
            custom_parts = [e.strip().replace(".", "").lower() for e in custom_str.split(",") if e.strip()]
            exts.extend(custom_parts)
        return list(set(exts))

    # --- Helper: Get active file extensions for Packaging ---
    def get_active_pack_extensions(self, prod_data):
        pack_file_types = prod_data.get("pack_file_types", ["jpg", "png", "tif"])
        custom_str = prod_data.get("pack_custom_extensions", "")
        
        exts = [e.strip().lower() for e in pack_file_types if e.strip()]
        if custom_str:
            custom_parts = [e.strip().replace(".", "").lower() for e in custom_str.split(",") if e.strip()]
            exts.extend(custom_parts)
        return list(set(exts))

    # --- Photoshop Action Orchestrator (Iterative File Batching + % progress indicator) ---
    def run_photoshop_action(self):
        prod_name = self.product_var.get()
        if not prod_name or prod_name == "-- None --":
            messagebox.showwarning("Cảnh báo", "Vui lòng cấu hình và chọn một sản phẩm trước!")
            return
            
        prod_data = self.config.get("products", {}).get(prod_name)
        if not prod_data:
            messagebox.showerror("Lỗi", "Không tìm thấy cấu hình của sản phẩm này!")
            return
            
        action_set = prod_data.get("photoshop_action_set", "")
        action_name = prod_data.get("photoshop_action_name", "")
        input_folder = prod_data.get("input_folder", "")
        
        # Validation checks
        if not input_folder or not os.path.exists(input_folder):
            messagebox.showerror(
                "Lỗi", 
                f"Thư mục đầu vào không tồn tại hoặc chưa cấu hình:\n{input_folder}\n\n"
                f"Vui lòng thiết lập trong Cài đặt (⚙️)."
            )
            return
            
        # Scan input folder for files matching active extensions (Action specific)
        exts = self.get_active_extensions(prod_data)
        matched_files = []
        for file_name in os.listdir(input_folder):
            file_path = os.path.join(input_folder, file_name)
            if os.path.isfile(file_path):
                _, ext = os.path.splitext(file_name)
                ext_clean = ext.replace(".", "").lower()
                if ext_clean in exts:
                    matched_files.append(file_path)
                    
        if not matched_files:
            messagebox.showinfo(
                "Thông báo",
                f"Không tìm thấy file ảnh có định dạng phù hợp trong thư mục đầu vào:\n{input_folder}"
            )
            return
            
        # Start Progress Indicator
        self.update_state("Đang chạy (0%)", "#f1c40f")  # Orange/Yellow
        self.update()
        
        # Photoshop Batch Loop
        if not PHOTOSHOP_AVAILABLE:
            total_files = len(matched_files)
            for idx, file_path in enumerate(matched_files, 1):
                # Simulated delay to visualize progress nicely
                time.sleep(0.5)
                percent = int((idx / total_files) * 100)
                self.update_state(f"Đang chạy ({percent}%)", "#f1c40f")
                self.update()
                
            self.update_state("Hoàn thành! (100%)", "#00d2d3")
            
            # Hands-Free Auto-Packaging Trigger (Simulated path)
            if prod_data.get("auto_package_after_action", False):
                self.after(500, self.run_packaging)
            return

        try:
            # Active instance check
            ps_app = win32com.client.Dispatch("Photoshop.Application")
            
            # Process each file
            processed_count = 0
            total_files = len(matched_files)
            for file_path in matched_files:
                # Open document
                doc = ps_app.Open(file_path)
                
                # Execute Photoshop Action
                ps_app.DoAction(action_name, action_set)
                
                # Save and Close (1 representing psSaveChanges)
                doc.Close(1)
                processed_count += 1
                
                # Update progress percentage on GUI in real-time
                percent = int((processed_count / total_files) * 100)
                self.update_state(f"Đang chạy ({percent}%)", "#f1c40f")
                self.update()
                
            self.update_state("Hoàn thành! (100%)", "#00d2d3")  # Cyan for completed
            
            # Hands-Free Auto-Packaging Trigger (Photoshop path)
            if prod_data.get("auto_package_after_action", False):
                self.after(500, self.run_packaging)
                
        except Exception as e:
            self.update_state("Lỗi Photoshop", "#e74c3c")
            messagebox.showerror(
                "Lỗi Photoshop", 
                f"Không thể kích hoạt Action Photoshop!\n\n"
                f"Chi tiết: {str(e)}\n\n"
                f"Mẹo: Hãy chắc chắn Photoshop đang mở, và Action '{action_name}' tồn tại trong Set '{action_set}'."
            )

    # --- Real-Time ZIP or Folder Packaging Orchestrator ---
    def run_packaging(self):
        prod_name = self.product_var.get()
        if not prod_name or prod_name == "-- None --":
            messagebox.showwarning("Cảnh báo", "Vui lòng cấu hình và chọn một sản phẩm trước!")
            return
            
        prod_data = self.config.get("products", {}).get(prod_name)
        if not prod_data:
            return
            
        # Get settings
        input_folder = prod_data.get("input_folder", "")
        delete_after = prod_data.get("delete_after_packaging", True)
        delete_source = prod_data.get("delete_source_folder_after_packaging", False)
        match_len = prod_data.get("match_prefix_length", 0)
        action_type = prod_data.get("action_type", "pack_all_zip")
        selected_files = prod_data.get("selected_package_files", [])
        
        # Validation checks
        if not input_folder or not os.path.exists(input_folder):
            messagebox.showerror(
                "Lỗi", 
                f"Thư mục đầu vào không hợp lệ hoặc không tồn tại:\n{input_folder}"
            )
            return
            
        # Get packaging extensions (Packaging specific)
        exts_to_match = self.get_active_pack_extensions(prod_data)
        
        # Dynamic directory structure
        current_date = datetime.datetime.now().strftime("%Y-%m-%d")
        desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
        target_parent = os.path.join(desktop_path, current_date, "Print")
        os.makedirs(target_parent, exist_ok=True)
        
        self.update_state("Đóng gói (0%)", "#f1c40f")
        self.update()
        
        try:
            if action_type == "pack_prefix_zip":
                # --- AUTOMATED BATCH PREFIX GROUPING & PACKAGING ---
                # Scan input folder for files matching packaging extensions
                all_files = []
                for file_name in os.listdir(input_folder):
                    file_path = os.path.join(input_folder, file_name)
                    if os.path.isfile(file_path):
                        _, ext = os.path.splitext(file_name)
                        ext_clean = ext.replace(".", "").lower()
                        if ext_clean in exts_to_match:
                            all_files.append((file_name, file_path))
                            
                if not all_files:
                    self.update_state("Không có file", "#e74c3c")
                    return
                    
                # Group files by prefix of length match_len
                prefix_groups = {}
                for file_name, file_path in all_files:
                    name_without_ext = os.path.splitext(file_name)[0]
                    if match_len > 0 and len(name_without_ext) >= match_len:
                        prefix = name_without_ext[:match_len]
                    else:
                        prefix = name_without_ext
                        
                    if prefix not in prefix_groups:
                        prefix_groups[prefix] = []
                    prefix_groups[prefix].append(file_path)
                    
                # Create a ZIP for each prefix group
                total_groups = len(prefix_groups)
                processed_groups = 0
                
                for prefix, file_paths in prefix_groups.items():
                    zip_file_path = os.path.join(target_parent, f"{prefix}.zip")
                    with zipfile.ZipFile(zip_file_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        for f_path in file_paths:
                            f_name = os.path.basename(f_path)
                            zipf.write(f_path, f_name)
                            
                    # Clean up original files if delete_after is enabled
                    if delete_after:
                        for f_path in file_paths:
                            try:
                                os.remove(f_path)
                            except Exception as err:
                                print(f"Error deleting file: {err}")
                                
                    processed_groups += 1
                    percent = int((processed_groups / total_groups) * 100)
                    self.update_state(f"Đóng gói ({percent}%)", "#f1c40f")
                    self.update()
                    
                # Robust full source folder deletion and empty rebuild if enabled
                if delete_source:
                    try:
                        shutil.rmtree(input_folder, ignore_errors=True)
                        os.makedirs(input_folder, exist_ok=True)
                    except Exception as folder_err:
                        print(f"Error wiping source folder: {folder_err}")
                        
                self.update_state("Hoàn thành! (100%)", "#2ecc71")
                self.update_source_stats()
                return
                
            else:
                # --- SINGLE PO PACKAGING (ZIP, Copy, or PO Match) ---
                po_name = self.current_po_name
                if not po_name or po_name == "Chua nhan":
                    self.update_state("Thiếu PO", "#e74c3c")
                    messagebox.showwarning(
                        "Thiếu tên PO",
                        "Chưa nhận được tên PO!\n\n"
                        "Hãy bắn dữ liệu PO từ web, hoặc tích chọn 'Tự sửa PO' để đặt tên thủ công."
                    )
                    self.update_state("Sẵn sàng", "#2ecc71")
                    return
                    
                matched_files = []
                if selected_files:
                    # Package strictly specified files
                    for f_path in selected_files:
                        if os.path.exists(f_path) and os.path.isfile(f_path):
                            matched_files.append(f_path)
                else:
                    # Default: Scan input folder using action rules
                    for file_name in os.listdir(input_folder):
                        file_path = os.path.join(input_folder, file_name)
                        if os.path.isfile(file_path):
                            _, ext = os.path.splitext(file_name)
                            ext_clean = ext.replace(".", "").lower()
                            
                            if ext_clean in exts_to_match:
                                if action_type == "pack_all_zip" or action_type == "copy_all_folder":
                                    matched_files.append(file_path)
                                elif action_type == "pack_list_zip":
                                    if po_name.lower() in file_name.lower():
                                        matched_files.append(file_path)
                                        
                if not matched_files:
                    self.update_state("Không có file", "#e74c3c")
                    return
                    
                total_files = len(matched_files)
                pack_to_zip = (action_type != "copy_all_folder")
                
                if pack_to_zip:
                    zip_file_path = os.path.join(target_parent, f"{po_name}.zip")
                    with zipfile.ZipFile(zip_file_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        for idx, file_path in enumerate(matched_files, 1):
                            f_name = os.path.basename(file_path)
                            zipf.write(file_path, f_name)
                            
                            # Clean original
                            if delete_after:
                                try:
                                    os.remove(file_path)
                                except Exception as err:
                                    print(f"Error deleting file: {err}")
                                    
                            percent = int((idx / total_files) * 100)
                            self.update_state(f"Đóng gói ({percent}%)", "#f1c40f")
                            self.update()
                else:
                    target_dir = os.path.join(target_parent, po_name)
                    os.makedirs(target_dir, exist_ok=True)
                    for idx, file_path in enumerate(matched_files, 1):
                        shutil.copy2(file_path, target_dir)
                        
                        # Clean original
                        if delete_after:
                            try:
                                os.remove(file_path)
                            except Exception as err:
                                print(f"Error deleting file: {err}")
                                
                        percent = int((idx / total_files) * 100)
                        self.update_state(f"Đóng gói ({percent}%)", "#f1c40f")
                        self.update()
                        
                # Robust full source folder deletion and empty rebuild if enabled
                if delete_source:
                    try:
                        shutil.rmtree(input_folder, ignore_errors=True)
                        os.makedirs(input_folder, exist_ok=True)
                    except Exception as folder_err:
                        print(f"Error wiping source folder: {folder_err}")
                        
                self.update_state("Hoàn thành! (100%)", "#2ecc71")
                self.update_source_stats()
                
        except Exception as e:
            self.update_state("Lỗi đóng gói", "#e74c3c")
            print(f"Packaging error: {e}")

    # ─────────────────────────────────────────────────────────────────────
    # IMAGE ARRANGER FEATURE
    # ─────────────────────────────────────────────────────────────────────

    def open_image_arranger(self):
        """One-click: pick folder → auto-generate print sheet like 1.png."""
        if not PIL_AVAILABLE:
            messagebox.showerror("Thiếu thư viện", "Cần cài đặt Pillow:\n  pip install Pillow")
            return
        folder = filedialog.askdirectory(title="Chọn thư mục ảnh cần xếp")
        if not folder:
            return
        self.update_state("Đang xếp ảnh...", "#e67e22")
        threading.Thread(target=self._do_arrange_images, args=(folder,), daemon=True).start()

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _parse_wo_info(filename):
        """
        Parse WO filename into (seq, positions_list, color, size, wo_code).
        Pattern: WO{date}-{x}-{num}-{seq}-{type}-{hash}-...-{Color}-{Size}-{Sides}.ext
        positions_list: e.g. ['Front', 'Left Arm'] from '2 Sides' logic,
                        or from explicit segment like 'Front', 'Left Arm', 'Right Arm'.
        """
        name = os.path.splitext(filename)[0]
        parts = name.split("-")

        # --- sequence number: first all-digit segment at index >= 3 ---
        seq = 9999
        for i, p in enumerate(parts):
            if i >= 3 and p.strip().isdigit():
                seq = int(p.strip())
                break

        # --- last segment: sides / explicit position ---
        last = parts[-1].strip() if parts else ""

        # Known explicit position labels
        EXPLICIT = {"Front", "Back", "Left Arm", "Right Arm",
                    "Left Chest", "Right Chest", "Sleeve"}
        if last in EXPLICIT:
            positions = [last]
        elif "2 Side" in last or last == "2 Sides":
            positions = ["Front", "Left Arm"]
        elif "3 Side" in last:
            positions = ["Front", "Left Arm", "Right Arm"]
        else:
            positions = ["Front"]   # default

        # --- color and size: last 3 segments before the sides segment ---
        # typical tail: ...-{Color}-{Size}-{Sides}
        color, size = "", ""
        # --- WO order code: first 3 dash segments ---
        wo_code = "-".join(parts[:3]) if len(parts) >= 3 else name[:20]

        return seq, positions, color, size, wo_code

    @staticmethod
    def _auto_trim(img_rgba):
        """Crop image to its non-transparent bounding box. Falls back to content if fully opaque."""
        r, g, b, a = img_rgba.split()
        # Try alpha channel first
        bbox = a.getbbox()
        if bbox:
            return img_rgba.crop(bbox)
        # Fall back: trim near-white rows/cols (for white-background images)
        from PIL import ImageOps
        rgb = img_rgba.convert("RGB")
        inverted = ImageOps.invert(rgb)
        bbox2 = inverted.getbbox()
        if bbox2:
            return img_rgba.crop(bbox2)
        return img_rgba

    # ── Main generation ──────────────────────────────────────────────────

    def _do_arrange_images(self, folder):
        """
        Generate print sheet matching 1.png style:
        - Canvas width is exactly 58cm (6850px at 300DPI).
        - Crop PSD slots and trim. No resizing of original crops.
        - Add WO code and Position above small items (Arms, Sides), using 2 lines.
        - Rotate Front/Back by 90 degrees CW and ATTACH 2-line side text.
        - Use Skyline 2D packing for optimal space usage.
        - Save output at 300 DPI.
        """
        try:
            Image.MAX_IMAGE_PIXELS = None

            PSD_W, PSD_H = 12589, 11716
            PSD_SLOTS = {
                "Right Arm":  (0,    2110, 4196,  6914),
                "Front":      (4186, 2110, 8386,  6913),
                "Left Arm":   (8389, 2110, 12589, 6914),
                "Back":       (4180, 6913, 8380,  11716),
                "Right Side": (0,    6914, 4206,  11716),
                "Left Side":  (8375, 6914, 12589, 11716),
            }

            def auto_trim(img_in, padding=10):
                try:
                    a = img_in.split()[-1]
                    bbox = a.getbbox()
                    if not bbox: return None
                    crop = img_in.crop(bbox)
                    new_img = Image.new("RGBA", (crop.width + padding*2, crop.height + padding*2), (0,0,0,0))
                    new_img.alpha_composite(crop, (padding, padding))
                    return new_img
                except Exception:
                    return None

            IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}
            entries = []
            for fn in os.listdir(folder):
                ext = os.path.splitext(fn)[1].lower()
                if ext in IMAGE_EXTS and "_sheet" not in fn:
                    entries.append(fn)

            if not entries:
                self.after(0, lambda: messagebox.showinfo("Không có ảnh", f"Không tìm thấy file ảnh trong:\n{folder}"))
                self.after(0, self.update_state, "Sẵn sàng", "#2ecc71")
                return

            def parse_filename(fn):
                if "-PPSW-" in fn:
                    prefix, suffix = fn.split("-PPSW-", 1)
                    parts = prefix.split("-")
                    seq_str = parts[-1]
                    try: seq = int(seq_str)
                    except: seq = 999
                    wo_code = "-".join(parts[:-1]) + "-" + seq_str
                    sku = "-".join(suffix.split("-")[:4])
                    return seq, wo_code, sku
                else:
                    return 999, fn[:20], "UNKNOWN"

            entries.sort(key=lambda x: parse_filename(x)[0])

            FONT_PT = 45
            try:
                f_lbl  = ImageFont.truetype("arial.ttf", FONT_PT)
            except Exception:
                f_lbl  = ImageFont.load_default()

            MAX_WIDTH = 6850
            GAP = 50

            class SkylinePacker:
                def __init__(self, width):
                    self.width = width
                    self.skyline = [(0, width, 0)]
                    self.max_y = 0

                def add_rect(self, w, h):
                    best_i, best_y, best_x = -1, float('inf'), -1
                    
                    for i in range(len(self.skyline)):
                        x, sw, y = self.skyline[i]
                        total_w = 0
                        max_y_in_span = y
                        can_fit = False
                        for j in range(i, len(self.skyline)):
                            cx, csw, cy = self.skyline[j]
                            max_y_in_span = max(max_y_in_span, cy)
                            total_w += csw
                            if total_w >= w:
                                can_fit = True
                                break
                        
                        if can_fit and max_y_in_span < best_y:
                            best_y = max_y_in_span
                            best_x = x
                            best_i = i

                    if best_i == -1: return None

                    new_skyline = []
                    for x, sw, y in self.skyline:
                        if x + sw <= best_x or x >= best_x + w:
                            new_skyline.append((x, sw, y))
                        else:
                            if x < best_x: new_skyline.append((x, best_x - x, y))
                            if x + sw > best_x + w: new_skyline.append((best_x + w, (x + sw) - (best_x + w), y))
                                
                    new_skyline.append((best_x, w, best_y + h))
                    new_skyline.sort(key=lambda seg: seg[0])
                    
                    merged = []
                    for seg in new_skyline:
                        if not merged: merged.append(seg)
                        else:
                            last_x, last_sw, last_y = merged[-1]
                            x, sw, y = seg
                            if last_y == y and last_x + last_sw == x:
                                merged[-1] = (last_x, last_sw + sw, y)
                            else: merged.append(seg)
                                
                    self.skyline = merged
                    self.max_y = max(self.max_y, best_y + h)
                    return (best_x, best_y)

            packer = SkylinePacker(MAX_WIDTH)
            placements = []

            for fn in entries:
                fpath = os.path.join(folder, fn)
                try:
                    img = Image.open(fpath).convert("RGBA")
                except Exception:
                    continue
                    
                seq, wo_code, sku = parse_filename(fn)
                iw, ih = img.size
                parts_to_pack = []

                if iw == 4200 and ih in [4800, 4803]:
                    trimmed = auto_trim(img)
                    if trimmed:
                        p_img = trimmed.transpose(Image.ROTATE_270)
                        text = fn
                        bbox = ImageDraw.Draw(Image.new("RGBA", (1,1))).textbbox((0,0), text, font=f_lbl)
                        tw, th = int(bbox[2] - bbox[0]), int(bbox[3] - bbox[1])
                        if tw > p_img.width + 100:
                            ti = Image.new("RGBA", (tw + 20, th + 20), (0,0,0,0))
                            ImageDraw.Draw(ti).text((10,10), text, fill=(0,0,0,255), font=f_lbl)
                            ti = ti.transpose(Image.ROTATE_270)
                            block_w = p_img.width + ti.width + 10
                            block_h = max(p_img.height, ti.height)
                            block = Image.new("RGBA", (block_w, block_h), (0,0,0,0))
                            block.alpha_composite(p_img, (0, (block_h - p_img.height)//2))
                            block.alpha_composite(ti, (p_img.width + 10, (block_h - ti.height)//2))
                            parts_to_pack.append(block)
                        else:
                            block_w = max(p_img.width, tw + 20)
                            block_h = p_img.height + th + 20
                            block = Image.new("RGBA", (block_w, block_h), (0,0,0,0))
                            draw = ImageDraw.Draw(block)
                            draw.text(((block_w - tw)//2, 5), text, fill=(0,0,0,255), font=f_lbl)
                            block.alpha_composite(p_img, ((block_w - p_img.width)//2, th + 20))
                            parts_to_pack.append(block)
                else:
                    sx = iw / PSD_W
                    sy = ih / PSD_H

                    extracted = {}
                    for slot_name, (pl, pt, pr, pb) in PSD_SLOTS.items():
                        sl, st = max(0, int(pl * sx)), max(0, int(pt * sy))
                        sr, sb = min(iw, int(pr * sx)), min(ih, int(pb * sy))
                        if sr <= sl or sb <= st: continue
                        
                        crop = img.crop((sl, st, sr, sb))
                        trimmed = auto_trim(crop)
                        if trimmed: extracted[slot_name] = trimmed

                    if not extracted: continue

                    for slot_name in ["Right Arm", "Left Arm", "Right Side", "Left Side"]:
                        if slot_name in extracted:
                            p_img = extracted[slot_name]
                            
                            text_2lines = f"{wo_code} - {sku}\n{slot_name}"
                            bbox2 = ImageDraw.Draw(Image.new("RGBA", (1,1))).multiline_textbbox((0,0), text_2lines, font=f_lbl, align="center")
                            tw2, th2 = int(bbox2[2] - bbox2[0]), int(bbox2[3] - bbox2[1])
                            
                            text_1line = f"{wo_code} - {sku} - {slot_name}"
                            bbox1 = ImageDraw.Draw(Image.new("RGBA", (1,1))).textbbox((0,0), text_1line, font=f_lbl)
                            tw1, th1 = int(bbox1[2] - bbox1[0]), int(bbox1[3] - bbox1[1])
                            
                            if tw2 > p_img.width + 100:
                                # Too narrow for top text, use 1-line rotated on side
                                ti = Image.new("RGBA", (tw1 + 20, th1 + 20), (0,0,0,0))
                                ImageDraw.Draw(ti).text((10,10), text_1line, fill=(0,0,0,255), font=f_lbl)
                                ti = ti.transpose(Image.ROTATE_270)
                                block_w = p_img.width + ti.width + 10
                                block_h = max(p_img.height, ti.height)
                                block = Image.new("RGBA", (block_w, block_h), (0,0,0,0))
                                block.alpha_composite(p_img, (0, (block_h - p_img.height)//2))
                                block.alpha_composite(ti, (p_img.width + 10, (block_h - ti.height)//2))
                                parts_to_pack.append(block)
                            else:
                                # Use 2-line top text
                                block_w = max(p_img.width, tw2 + 20)
                                block_h = p_img.height + th2 + 20
                                block = Image.new("RGBA", (block_w, block_h), (0,0,0,0))
                                draw = ImageDraw.Draw(block)
                                draw.multiline_text(((block_w - tw2)//2, 5), text_2lines, fill=(0,0,0,255), font=f_lbl, align="center")
                                block.alpha_composite(p_img, ((block_w - p_img.width)//2, th2 + 20))
                                parts_to_pack.append(block)

                    for slot_name in ["Front", "Back"]:
                        if slot_name in extracted:
                            p_img = extracted[slot_name].transpose(Image.ROTATE_270)
                            
                            side_text = f"{sku} - {wo_code}\n{slot_name}"
                            bbox = ImageDraw.Draw(Image.new("RGBA", (1,1))).multiline_textbbox((0,0), side_text, font=f_lbl, align="center")
                            tw, th = int(bbox[2] - bbox[0]), int(bbox[3] - bbox[1])
                            
                            ti = Image.new("RGBA", (tw + 40, th + 40), (0,0,0,0))
                            ImageDraw.Draw(ti).multiline_text((20,20), side_text, fill=(0,0,0,255), font=f_lbl, align="center")
                            ti = ti.transpose(Image.ROTATE_270)
                            
                            block_w = p_img.width + ti.width + 10
                            block_h = max(p_img.height, ti.height)
                            block = Image.new("RGBA", (block_w, block_h), (0,0,0,0))
                            
                            block.alpha_composite(p_img, (0, (block_h - p_img.height)//2))
                            block.alpha_composite(ti, (p_img.width + 10, (block_h - ti.height)//2))
                            
                            parts_to_pack.append(block)

                for block in parts_to_pack:
                    pos = packer.add_rect(block.width + GAP, block.height + GAP)
                    if pos: placements.append((block, pos[0], pos[1]))

            if not placements:
                self.after(0, lambda: messagebox.showwarning("Lỗi", "Không thể trích xuất chi tiết nào từ ảnh!"))
                self.after(0, self.update_state, "Sẵn sàng", "#2ecc71")
                return

            sheet_h = packer.max_y + GAP
            sheet = Image.new("RGBA", (MAX_WIDTH, sheet_h), (0, 0, 0, 0))
            for block, x, y in placements:
                sheet.alpha_composite(block, (x, y))

            folder_name = os.path.basename(folder.rstrip("/\\"))
            out_path = os.path.join(folder, f"{folder_name}_sheet.png")
            sheet.save(out_path, "PNG", dpi=(300, 300))

            def _done():
                self.update_state("Xếp ảnh xong!", "#e67e22")
                if messagebox.askyesno(
                        "Hoàn thành",
                        f"Đã cắt và xếp ảnh thành công!\n"
                        f"Thuật toán mới (Skyline) đã nén tối đa diện tích.\n"
                        f"Lưu tại:\n{out_path}\n\nMở file kết quả?"):
                    os.startfile(out_path)
            self.after(0, _done)

        except Exception as exc:
            import traceback
            traceback.print_exc()
            self.after(0, lambda: messagebox.showerror("Lỗi xếp ảnh", str(exc)))
            self.after(0, self.update_state, "Lỗi xếp ảnh", "#e74c3c")

    def open_input_folder(self):
        prod_name = self.product_var.get()
        if not prod_name or prod_name == "-- None --":
            messagebox.showwarning("Cảnh báo", "Vui lòng cấu hình và chọn một sản phẩm trước!")
            return
            
        prod_data = self.config.get("products", {}).get(prod_name)
        if not prod_data:
            return
            
        input_folder = prod_data.get("input_folder", "")
        if not input_folder:
            messagebox.showwarning("Cảnh báo", "Chưa cấu hình thư mục đầu vào cho sản phẩm này!")
            return
            
        # Create folder if it doesn't exist
        os.makedirs(input_folder, exist_ok=True)
        
        try:
            os.startfile(input_folder)
            self.update_state("Mở thư mục đầu vào", "#00d2d3")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể mở thư mục đầu vào:\n{str(e)}")

    # --- Manual Clean Input Folder Command (Icon Button) ---
    def manual_clean_input_folder(self):
        prod_name = self.product_var.get()
        if not prod_name or prod_name == "-- None --":
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn một cấu hình sản phẩm trước!")
            return
            
        prod_data = self.config.get("products", {}).get(prod_name)
        if not prod_data:
            return
            
        input_folder = prod_data.get("input_folder", "")
        if not input_folder or not os.path.exists(input_folder):
            messagebox.showwarning("Cảnh báo", "Thư mục đầu vào không tồn tại hoặc chưa được thiết lập!")
            return
            
        confirm = messagebox.askyesno(
            "Xác nhận xóa sạch",
            f"Bạn có chắc chắn muốn XÓA SẠCH toàn bộ file bên trong thư mục đầu vào:\n{input_folder}?\n\n"
            f"⚠️ Hành động này không thể hoàn tác!"
        )
        if confirm:
            deleted_count = 0
            for file_name in os.listdir(input_folder):
                file_path = os.path.join(input_folder, file_name)
                if os.path.isfile(file_path):
                    try:
                        os.remove(file_path)
                        deleted_count += 1
                    except Exception as err:
                        print(f"Error deleting file: {err}")
            
            self.update_source_stats()
            self.update_state(f"Đã dọn dẹp {deleted_count} file", "#00d2d3")

    # --- Choose Specific files to package in current configuration ---
    def choose_specific_packaging_files(self):
        input_folder = self.ent_input_folder.get().strip()
        initial_dir = input_folder if input_folder and os.path.exists(input_folder) else os.path.expanduser("~")
        
        # Build dynamic file types filter list based on PACKAGING checked options and PACKAGING custom entry!
        prod_data = {
            "pack_file_types": [],
            "pack_custom_extensions": self.ent_pack_custom_exts.get().strip()
        }
        if self.chk_pack_jpg_var.get() == 1:
            prod_data["pack_file_types"].append("jpg")
            prod_data["pack_file_types"].append("jpeg")
        if self.chk_pack_png_var.get() == 1:
            prod_data["pack_file_types"].append("png")
        if self.chk_pack_tif_var.get() == 1:
            prod_data["pack_file_types"].append("tif")
            prod_data["pack_file_types"].append("tiff")
            
        exts = self.get_active_pack_extensions(prod_data)
        
        # Build filetypes filter for dialog
        filter_patterns = " ".join([f"*.{ext}" for ext in exts]) if exts else "*.*"
        filetypes_arg = [
            ("Supported Packaging Image Files", filter_patterns),
            ("TIFF Image (*.tif, *.tiff)", "*.tif *.tiff"),
            ("PNG Image (*.png)", "*.png"),
            ("JPEG Image (*.jpg, *.jpeg)", "*.jpg *.jpeg"),
            ("All Files (*.*)", "*.*")
        ]
        
        files = filedialog.askopenfilenames(
            title="Chọn các file ảnh cần đóng gói",
            initialdir=initial_dir,
            filetypes=filetypes_arg
        )
        if files:
            self.selected_files_list = list(files)
            self.lbl_selected_files_count.configure(
                text=f"Đã chọn: {len(self.selected_files_list)} file",
                text_color="#2ecc71"
            )
        else:
            self.selected_files_list = []
            self.lbl_selected_files_count.configure(
                text="Đã chọn: Toàn bộ (Mặc định)",
                text_color="#8A8A8E"
            )

    # --- Configuration Popup Dialog (Extended with Pack & Match configurations) ---
    def open_settings(self):
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.focus()
            return
            
        # Initialize floating CTkToplevel settings popup
        self.settings_window = ctk.CTkToplevel(self)
        self.settings_window.title("Cấu hình Chi Tiết Sản Phẩm")
        self.settings_window.geometry("440x720") # Custom size to hold all scrollable components perfectly
        self.settings_window.resizable(False, False)
        self.settings_window.attributes("-topmost", True)
        
        # Form Title
        title_lbl = ctk.CTkLabel(
            self.settings_window, 
            text="QUẢN LÝ CẤU HÌNH SẢN PHẨM", 
            font=ctk.CTkFont(size=13, weight="bold")
        )
        title_lbl.pack(pady=(12, 4))
        
        # Master selector frame inside settings popup
        selector_frame = ctk.CTkFrame(self.settings_window, fg_color="transparent")
        selector_frame.pack(fill="x", padx=15, pady=5)
        
        ctk.CTkLabel(selector_frame, text="Chọn cấu hình chỉnh sửa:", font=ctk.CTkFont(size=10)).pack(side="left", padx=(0, 5))
        
        self.settings_prod_var = tk.StringVar()
        self.settings_prod_dropdown = ctk.CTkComboBox(
            selector_frame,
            values=self.product_list if self.product_list else ["-- Chọn --"],
            variable=self.settings_prod_var,
            command=self.load_product_to_inputs,
            width=220,
            height=24,
            font=ctk.CTkFont(size=10)
        )
        self.settings_prod_dropdown.pack(side="left", fill="x", expand=True)
        
        # --- Scrollable Frame to avoid clipping ---
        form_scroll_frame = ctk.CTkScrollableFrame(self.settings_window, fg_color="transparent")
        form_scroll_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # 1. Product Title field
        ctk.CTkLabel(form_scroll_frame, text="Tên Sản Phẩm:", font=ctk.CTkFont(size=10, weight="bold")).pack(anchor="w", padx=10, pady=(4, 0))
        self.ent_prod_name = ctk.CTkEntry(form_scroll_frame, placeholder_text="Ví dụ: Sản phẩm A", height=24, font=ctk.CTkFont(size=10))
        self.ent_prod_name.pack(fill="x", padx=10, pady=2)
        
        # 2. Action Set name
        ctk.CTkLabel(form_scroll_frame, text="Photoshop Action Set:", font=ctk.CTkFont(size=10, weight="bold")).pack(anchor="w", padx=10, pady=(4, 0))
        self.ent_action_set = ctk.CTkEntry(form_scroll_frame, placeholder_text="Ví dụ: Default Actions", height=24, font=ctk.CTkFont(size=10))
        self.ent_action_set.pack(fill="x", padx=10, pady=2)
        
        # 3. Action Name
        ctk.CTkLabel(form_scroll_frame, text="Photoshop Action Name:", font=ctk.CTkFont(size=10, weight="bold")).pack(anchor="w", padx=10, pady=(4, 0))
        self.ent_action_name = ctk.CTkEntry(form_scroll_frame, placeholder_text="Ví dụ: Vibe Resize A", height=24, font=ctk.CTkFont(size=10))
        self.ent_action_name.pack(fill="x", padx=10, pady=2)
        
        # 4. Input Path Folder Select
        ctk.CTkLabel(form_scroll_frame, text="Thư Mục Đầu Vào Chứa Ảnh Gốc:", font=ctk.CTkFont(size=10, weight="bold")).pack(anchor="w", padx=10, pady=(4, 0))
        path_frame = ctk.CTkFrame(form_scroll_frame, fg_color="transparent")
        path_frame.pack(fill="x", padx=10, pady=2)
        
        self.ent_input_folder = ctk.CTkEntry(path_frame, placeholder_text="Chọn đường dẫn thư mục ảnh đầu vào...", height=24, font=ctk.CTkFont(size=10))
        self.ent_input_folder.pack(side="left", fill="x", expand=True)
        
        browse_btn = ctk.CTkButton(
            path_frame, 
            text="Chọn 📂", 
            width=60, 
            height=24,
            command=self.browse_input_dir,
            fg_color="#3A3A42",
            hover_color="#4F4F56",
            font=ctk.CTkFont(size=10)
        )
        browse_btn.pack(side="right", padx=(5, 0))
        
        # --- Section 1: Loại file sẽ xử lý (Action Photoshop specific) ---
        self.file_types_frame = ctk.CTkFrame(form_scroll_frame, border_width=1, border_color="#4F4F56", fg_color="transparent", corner_radius=6)
        self.file_types_frame.pack(fill="x", padx=10, pady=8)
        
        ctk.CTkLabel(
            self.file_types_frame, 
            text="Loại file sẽ xử lý (Photoshop)", 
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#A4A4A6"
        ).pack(anchor="w", padx=12, pady=(6, 0))
        
        cb_row = ctk.CTkFrame(self.file_types_frame, fg_color="transparent")
        cb_row.pack(fill="x", padx=12, pady=4)
        
        self.chk_jpg_var = tk.IntVar(value=1)
        self.chk_jpg = ctk.CTkCheckBox(cb_row, text=".jpg", variable=self.chk_jpg_var, font=ctk.CTkFont(size=10), checkbox_width=16, checkbox_height=16)
        self.chk_jpg.pack(side="left", padx=(0, 15))
        
        self.chk_png_var = tk.IntVar(value=1)
        self.chk_png = ctk.CTkCheckBox(cb_row, text=".png", variable=self.chk_png_var, font=ctk.CTkFont(size=10), checkbox_width=16, checkbox_height=16)
        self.chk_png.pack(side="left", padx=(0, 15))
        
        self.chk_tif_var = tk.IntVar(value=1)
        self.chk_tif = ctk.CTkCheckBox(cb_row, text=".tif", variable=self.chk_tif_var, font=ctk.CTkFont(size=10), checkbox_width=16, checkbox_height=16)
        self.chk_tif.pack(side="left", padx=(0, 15))
        
        self.ent_custom_exts = ctk.CTkEntry(self.file_types_frame, placeholder_text=".pdf, .eps, ...", height=24, font=ctk.CTkFont(size=10))
        self.ent_custom_exts.pack(fill="x", padx=12, pady=(4, 6))

        # --- Section 1.5: Loại file sẽ đóng gói (Packaging specific) ---
        self.pack_file_types_frame = ctk.CTkFrame(form_scroll_frame, border_width=1, border_color="#4F4F56", fg_color="transparent", corner_radius=6)
        self.pack_file_types_frame.pack(fill="x", padx=10, pady=8)
        
        ctk.CTkLabel(
            self.pack_file_types_frame, 
            text="Loại file sẽ đóng gói", 
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#A4A4A6"
        ).pack(anchor="w", padx=12, pady=(6, 0))
        
        pack_cb_row = ctk.CTkFrame(self.pack_file_types_frame, fg_color="transparent")
        pack_cb_row.pack(fill="x", padx=12, pady=4)
        
        self.chk_pack_jpg_var = tk.IntVar(value=1)
        self.chk_pack_jpg = ctk.CTkCheckBox(pack_cb_row, text=".jpg", variable=self.chk_pack_jpg_var, font=ctk.CTkFont(size=10), checkbox_width=16, checkbox_height=16)
        self.chk_pack_jpg.pack(side="left", padx=(0, 15))
        
        self.chk_pack_png_var = tk.IntVar(value=1)
        self.chk_pack_png = ctk.CTkCheckBox(pack_cb_row, text=".png", variable=self.chk_pack_png_var, font=ctk.CTkFont(size=10), checkbox_width=16, checkbox_height=16)
        self.chk_pack_png.pack(side="left", padx=(0, 15))
        
        self.chk_pack_tif_var = tk.IntVar(value=1)
        self.chk_pack_tif = ctk.CTkCheckBox(pack_cb_row, text=".tif", variable=self.chk_pack_tif_var, font=ctk.CTkFont(size=10), checkbox_width=16, checkbox_height=16)
        self.chk_pack_tif.pack(side="left", padx=(0, 15))
        
        self.ent_pack_custom_exts = ctk.CTkEntry(self.pack_file_types_frame, placeholder_text=".pdf, .eps, ...", height=24, font=ctk.CTkFont(size=10))
        self.ent_pack_custom_exts.pack(fill="x", padx=12, pady=(4, 6))
        
        # New Row: Choose specific files to package
        file_select_row = ctk.CTkFrame(self.pack_file_types_frame, fg_color="transparent")
        file_select_row.pack(fill="x", padx=12, pady=(2, 10))
        
        self.btn_select_files = ctk.CTkButton(
            file_select_row,
            text="Tùy chọn file cần đóng... 📄",
            font=ctk.CTkFont(size=10, weight="bold"),
            height=24,
            width=160,
            fg_color="#3A3A42",
            hover_color="#4F4F56",
            command=self.choose_specific_packaging_files
        )
        self.btn_select_files.pack(side="left")
        
        self.lbl_selected_files_count = ctk.CTkLabel(
            file_select_row,
            text="Đã chọn: Toàn bộ (Mặc định)",
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color="#8A8A8E"
        )
        self.lbl_selected_files_count.pack(side="left", padx=(10, 0))
        
        # --- Section 2: Hành động (With your precise Radio Button layout) ---
        self.action_frame = ctk.CTkFrame(form_scroll_frame, border_width=1, border_color="#4F4F56", fg_color="transparent", corner_radius=6)
        self.action_frame.pack(fill="x", padx=10, pady=8)
        
        ctk.CTkLabel(
            self.action_frame, 
            text="Hành động", 
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#A4A4A6"
        ).pack(anchor="w", padx=12, pady=(6, 0))
        
        self.action_type_var = tk.StringVar(value="pack_all_zip")
        
        self.r_pack_all = ctk.CTkRadioButton(
            self.action_frame, 
            text="Nén các file đã qua xử lý", 
            variable=self.action_type_var,
            value="pack_all_zip",
            font=ctk.CTkFont(size=10),
            radiobutton_width=14,
            radiobutton_height=14,
            command=self.on_action_type_changed
        )
        self.r_pack_all.pack(anchor="w", padx=12, pady=4)
        
        self.r_copy_all = ctk.CTkRadioButton(
            self.action_frame, 
            text="Sao chép các file đã qua xử lý", 
            variable=self.action_type_var,
            value="copy_all_folder",
            font=ctk.CTkFont(size=10),
            radiobutton_width=14,
            radiobutton_height=14,
            command=self.on_action_type_changed
        )
        self.r_copy_all.pack(anchor="w", padx=12, pady=4)
        
        self.r_pack_prefix = ctk.CTkRadioButton(
            self.action_frame, 
            text="Nén theo nhóm ký tự trùng khớp", 
            variable=self.action_type_var,
            value="pack_prefix_zip",
            font=ctk.CTkFont(size=10),
            radiobutton_width=14,
            radiobutton_height=14,
            command=self.on_action_type_changed
        )
        self.r_pack_prefix.pack(anchor="w", padx=12, pady=4)
        
        # Sub-input inline under prefix choice
        self.prefix_input_frame = ctk.CTkFrame(self.action_frame, fg_color="transparent")
        self.prefix_input_frame.pack(fill="x", padx=32, pady=(0, 2))
        
        ctk.CTkLabel(self.prefix_input_frame, text="Số ký tự khớp (từ trái qua phải):", font=ctk.CTkFont(size=9)).pack(side="left")
        self.ent_match_len = ctk.CTkEntry(self.prefix_input_frame, width=50, height=20, font=ctk.CTkFont(size=9))
        self.ent_match_len.pack(side="left", padx=5)
        self.ent_match_len.insert(0, "0")
        
        self.r_pack_list = ctk.CTkRadioButton(
            self.action_frame, 
            text="Nén theo danh sách tên từ thư mục Nguồn", 
            variable=self.action_type_var,
            value="pack_list_zip",
            font=ctk.CTkFont(size=10),
            radiobutton_width=14,
            radiobutton_height=14,
            command=self.on_action_type_changed
        )
        self.r_pack_list.pack(anchor="w", padx=12, pady=4)
        
        ctk.CTkLabel(
            self.action_frame, 
            text="Tên file ZIP/thư mục sẽ ở màn hình chính", 
            font=ctk.CTkFont(size=9, slant="italic"),
            text_color="#8A8A8E"
        ).pack(anchor="w", padx=12, pady=(6, 8))
        
        # --- Section 3: Tùy chọn sau xử lý (Xóa file gốc, Tự động đóng gói, Xóa thư mục nguồn) ---
        self.post_process_frame = ctk.CTkFrame(form_scroll_frame, border_width=1, border_color="#4F4F56", fg_color="transparent", corner_radius=6)
        self.post_process_frame.pack(fill="x", padx=10, pady=8)
        
        ctk.CTkLabel(
            self.post_process_frame, 
            text="Tùy chọn sau xử lý", 
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#A4A4A6"
        ).pack(anchor="w", padx=12, pady=(6, 0))
        
        self.delete_after_var = tk.IntVar(value=1)
        self.chk_delete_after = ctk.CTkCheckBox(
            self.post_process_frame, 
            text="Xóa các file gốc sau khi đóng gói",
            variable=self.delete_after_var,
            font=ctk.CTkFont(size=10),
            fg_color=self.accent_teal,
            hover_color="#0f8c6b",
            checkbox_width=16,
            checkbox_height=16
        )
        self.chk_delete_after.pack(anchor="w", padx=12, pady=(4, 4))
        
        self.auto_pack_var = tk.IntVar(value=0)
        self.chk_auto_pack = ctk.CTkCheckBox(
            self.post_process_frame, 
            text="Tự động đóng gói sau khi chạy Action",
            variable=self.auto_pack_var,
            font=ctk.CTkFont(size=10),
            fg_color=self.accent_purple,
            hover_color="#6c5ce7",
            checkbox_width=16,
            checkbox_height=16
        )
        self.chk_auto_pack.pack(anchor="w", padx=12, pady=(4, 4))

        self.delete_source_var = tk.IntVar(value=0)
        self.chk_delete_source = ctk.CTkCheckBox(
            self.post_process_frame, 
            text="Xóa thư mục nguồn sau khi đóng gói",
            variable=self.delete_source_var,
            font=ctk.CTkFont(size=10),
            fg_color="#d63031",
            hover_color="#b2bec3",
            checkbox_width=16,
            checkbox_height=16
        )
        self.chk_delete_source.pack(anchor="w", padx=12, pady=(4, 10))
        
        # --- Control Action Buttons Panel (Delete, Add New, Save) ---
        btn_panel = ctk.CTkFrame(self.settings_window, fg_color="transparent")
        btn_panel.pack(fill="x", padx=15, pady=10)
        
        btn_delete = ctk.CTkButton(
            btn_panel,
            text="Xóa 🗑️",
            fg_color="#d63031",
            hover_color="#b2bec3",
            width=80,
            command=self.delete_product_config,
            font=ctk.CTkFont(size=10, weight="bold")
        )
        btn_delete.pack(side="left", padx=2)
        
        btn_add = ctk.CTkButton(
            btn_panel,
            text="Thêm Mới ➕",
            fg_color="#3498db",
            hover_color="#2980b9",
            width=90,
            command=self.add_new_product_config,
            font=ctk.CTkFont(size=10, weight="bold")
        )
        btn_add.pack(side="left", padx=2)
        
        btn_save = ctk.CTkButton(
            btn_panel,
            text="Lưu Cấu Hình 💾",
            fg_color=self.accent_teal,
            hover_color="#0f8c6b",
            width=120,
            command=self.save_product_config,
            font=ctk.CTkFont(size=10, weight="bold")
        )
        btn_save.pack(side="right", padx=2)
        
        # Initial loading: populate fields with active product
        if self.product_var.get() and self.product_var.get() != "-- None --":
            self.settings_prod_var.set(self.product_var.get())
            self.load_product_to_inputs(self.product_var.get())

    # --- Settings Dialog Actions ---
    def on_action_type_changed(self):
        val = self.action_type_var.get()
        if val == "pack_prefix_zip":
            self.ent_match_len.configure(state="normal")
        else:
            self.ent_match_len.configure(state="disabled")

    def load_product_to_inputs(self, prod_name):
        if not prod_name or prod_name == "-- Chọn --":
            return
        
        prod_data = self.config.get("products", {}).get(prod_name, {})
        
        # Clear fields
        self.ent_prod_name.delete(0, tk.END)
        self.ent_action_set.delete(0, tk.END)
        self.ent_action_name.delete(0, tk.END)
        self.ent_input_folder.delete(0, tk.END)
        self.ent_custom_exts.delete(0, tk.END)
        self.ent_pack_custom_exts.delete(0, tk.END)
        self.ent_match_len.delete(0, tk.END)
        
        # Insert configuration data
        self.ent_prod_name.insert(0, prod_name)
        self.ent_action_set.insert(0, prod_data.get("photoshop_action_set", ""))
        self.ent_action_name.insert(0, prod_data.get("photoshop_action_name", ""))
        self.ent_input_folder.insert(0, prod_data.get("input_folder", ""))
        self.ent_custom_exts.insert(0, prod_data.get("custom_extensions", ""))
        self.ent_pack_custom_exts.insert(0, prod_data.get("pack_custom_extensions", ""))
        self.ent_match_len.insert(0, str(prod_data.get("match_prefix_length", 0)))
        
        # Set Photoshop Action file types checkboxes
        file_types = prod_data.get("file_types", ["jpg", "png", "tif"])
        if "jpg" in file_types:
            self.chk_jpg.select()
        else:
            self.chk_jpg.deselect()
            
        if "png" in file_types:
            self.chk_png.select()
        else:
            self.chk_png.deselect()
            
        if "tif" in file_types:
            self.chk_tif.select()
        else:
            self.chk_tif.deselect()
            
        # Set Packaging file types checkboxes
        pack_file_types = prod_data.get("pack_file_types", ["jpg", "png", "tif"])
        if "jpg" in pack_file_types:
            self.chk_pack_jpg.select()
        else:
            self.chk_pack_jpg.deselect()
            
        if "png" in pack_file_types:
            self.chk_pack_png.select()
        else:
            self.chk_pack_png.deselect()
            
        if "tif" in pack_file_types:
            self.chk_pack_tif.select()
        else:
            self.chk_pack_tif.deselect()
            
        # Load specific selected files if any
        self.selected_files_list = prod_data.get("selected_package_files", [])
        if self.selected_files_list:
            self.lbl_selected_files_count.configure(
                text=f"Đã chọn: {len(self.selected_files_list)} file",
                text_color="#2ecc71"
            )
        else:
            self.lbl_selected_files_count.configure(
                text="Đã chọn: Toàn bộ (Mặc định)",
                text_color="#8A8A8E"
            )
            
        # Set action type radio buttons
        action_type = prod_data.get("action_type", "pack_all_zip")
        self.action_type_var.set(action_type)
        self.on_action_type_changed()
            
        # Set Delete packaging checkbox value
        delete_val = prod_data.get("delete_after_packaging", True)
        if delete_val:
            self.chk_delete_after.select()
        else:
            self.chk_delete_after.deselect()
            
        # Set Auto Packaging checkbox value
        auto_pack_val = prod_data.get("auto_package_after_action", False)
        if auto_pack_val:
            self.chk_auto_pack.select()
        else:
            self.chk_auto_pack.deselect()
            
        # Set Delete source folder checkbox value
        delete_src_val = prod_data.get("delete_source_folder_after_packaging", False)
        if delete_src_val:
            self.chk_delete_source.select()
        else:
            self.chk_delete_source.deselect()

    def browse_input_dir(self):
        folder = filedialog.askdirectory(title="Chọn Thư Mục Chứa Ảnh Đầu Vào")
        if folder:
            self.ent_input_folder.delete(0, tk.END)
            self.ent_input_folder.insert(0, folder)

    def add_new_product_config(self):
        # Reset form fields for creating a new product
        self.ent_prod_name.delete(0, tk.END)
        self.ent_action_set.delete(0, tk.END)
        self.ent_action_name.delete(0, tk.END)
        self.ent_input_folder.delete(0, tk.END)
        self.ent_custom_exts.delete(0, tk.END)
        self.ent_pack_custom_exts.delete(0, tk.END)
        self.ent_match_len.delete(0, tk.END)
        
        self.chk_jpg.select()
        self.chk_png.select()
        self.chk_tif.select()
        
        self.chk_pack_jpg.select()
        self.chk_pack_png.select()
        self.chk_pack_tif.select()
        
        self.selected_files_list = []
        self.lbl_selected_files_count.configure(
            text="Đã chọn: Toàn bộ (Mặc định)",
            text_color="#8A8A8E"
        )
        
        self.action_type_var.set("pack_all_zip")
        self.on_action_type_changed()
        self.chk_delete_after.select()
        self.chk_auto_pack.deselect()
        self.chk_delete_source.deselect()
        
        self.ent_prod_name.insert(0, "Sản phẩm Mới")
        self.ent_match_len.insert(0, "0")
        self.ent_prod_name.focus()

    def delete_product_config(self):
        current_selection = self.settings_prod_var.get()
        if not current_selection or current_selection == "-- Chọn --":
            return
            
        confirm = messagebox.askyesno(
            "Xác nhận xóa", 
            f"Bạn có chắc muốn xóa cấu hình '{current_selection}'?",
            parent=self.settings_window
        )
        if confirm:
            # Delete from internal dict
            if current_selection in self.config.get("products", {}):
                del self.config["products"][current_selection]
                
                # Check if it was active product
                if self.config.get("active_product") == current_selection:
                    rem_keys = list(self.config["products"].keys())
                    self.config["active_product"] = rem_keys[0] if rem_keys else ""
                
                self.save_config()
                self.refresh_main_dropdown()
                
                # Close/repopulate
                messagebox.showinfo("Đã xóa", f"Đã xóa cấu hình '{current_selection}' thành công!", parent=self.settings_window)
                
                # Reload dropdown in settings
                self.product_list = list(self.config.get("products", {}).keys())
                self.settings_prod_dropdown.configure(values=self.product_list if self.product_list else ["-- Chọn --"])
                if self.product_list:
                    self.settings_prod_var.set(self.product_list[0])
                    self.load_product_to_inputs(self.product_list[0])
                else:
                    self.settings_prod_var.set("-- Chọn --")
                    self.ent_prod_name.delete(0, tk.END)
                    self.ent_action_set.delete(0, tk.END)
                    self.ent_action_name.delete(0, tk.END)
                    self.ent_input_folder.delete(0, tk.END)
                    self.ent_custom_exts.delete(0, tk.END)
                    self.ent_pack_custom_exts.delete(0, tk.END)
                    self.ent_match_len.delete(0, tk.END)
                    self.chk_jpg.deselect()
                    self.chk_png.deselect()
                    self.chk_tif.deselect()
                    self.chk_pack_jpg.deselect()
                    self.chk_pack_png.deselect()
                    self.chk_pack_tif.deselect()
                    self.selected_files_list = []
                    self.lbl_selected_files_count.configure(
                        text="Đã chọn: Toàn bộ (Mặc định)",
                        text_color="#8A8A8E"
                    )
                    self.chk_delete_after.deselect()
                    self.chk_auto_pack.deselect()
                    self.chk_delete_source.deselect()

    def save_product_config(self):
        name = self.ent_prod_name.get().strip()
        if not name:
            messagebox.showerror("Lỗi", "Tên sản phẩm không được để trống!", parent=self.settings_window)
            return
            
        action_set = self.ent_action_set.get().strip()
        action_name = self.ent_action_name.get().strip()
        input_folder = self.ent_input_folder.get().strip()
        custom_extensions = self.ent_custom_exts.get().strip()
        pack_custom_extensions = self.ent_pack_custom_exts.get().strip()
        
        # Load Photoshop Action checkboxes
        file_types = []
        if self.chk_jpg_var.get() == 1:
            file_types.append("jpg")
        if self.chk_png_var.get() == 1:
            file_types.append("png")
        if self.chk_tif_var.get() == 1:
            file_types.append("tif")
            
        # Load Packaging checkboxes
        pack_file_types = []
        if self.chk_pack_jpg_var.get() == 1:
            pack_file_types.append("jpg")
        if self.chk_pack_png_var.get() == 1:
            pack_file_types.append("png")
        if self.chk_pack_tif_var.get() == 1:
            pack_file_types.append("tif")
            
        # Prefix Match characters constraint
        match_len = 0
        try:
            match_len = int(self.ent_match_len.get().strip())
        except ValueError:
            match_len = 0
            
        # Action selection
        action_type = self.action_type_var.get()
        
        # Post cleanup selection
        delete_after = True if self.delete_after_var.get() == 1 else False
        
        # Auto package selection
        auto_package_after_action = True if self.auto_pack_var.get() == 1 else False
        
        # Source directory wipe selection
        delete_source_folder = True if self.delete_source_var.get() == 1 else False
        
        # Fetch the selected file paths from class instance
        selected_package_files = getattr(self, "selected_files_list", [])
        
        # Save to config dictionary
        if "products" not in self.config:
            self.config["products"] = {}
            
        self.config["products"][name] = {
            "photoshop_action_set": action_set,
            "photoshop_action_name": action_name,
            "input_folder": input_folder,
            "file_types": file_types,
            "custom_extensions": custom_extensions,
            "pack_file_types": pack_file_types,
            "pack_custom_extensions": pack_custom_extensions,
            "selected_package_files": selected_package_files,
            "action_type": action_type,
            "match_prefix_length": match_len,
            "delete_after_packaging": delete_after,
            "auto_package_after_action": auto_package_after_action,
            "delete_source_folder_after_packaging": delete_source_folder
        }
        
        # Set active product if empty
        if not self.config.get("active_product") or self.config["active_product"] == "-- None --":
            self.config["active_product"] = name
            
        self.save_config()
        self.refresh_main_dropdown()
        
        # Update settings dropdown list
        self.product_list = list(self.config["products"].keys())
        self.settings_prod_dropdown.configure(values=self.product_list)
        self.settings_prod_var.set(name)
        
        messagebox.showinfo("Thành công", f"Đã lưu cấu hình '{name}' thành công!", parent=self.settings_window)
        # Update target folder watchdog structure
        self.update_source_stats()

    def refresh_main_dropdown(self):
        self.product_list = list(self.config.get("products", {}).keys())
        self.product_dropdown.configure(values=self.product_list if self.product_list else ["-- None --"])
        active = self.config.get("active_product", "")
        if active in self.product_list:
            self.product_var.set(active)
        elif self.product_list:
            self.product_var.set(self.product_list[0])
            self.config["active_product"] = self.product_list[0]
            self.save_config()
        else:
            self.product_var.set("-- None --")
            self.config["active_product"] = ""
            self.save_config()

if __name__ == "__main__":
    app = PhotoshopAutoGUI()
    app.mainloop()
