# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — ACC2019 Hub.

Build:
  pyinstaller ACC2019.spec --noconfirm

Output: dist/ACC2019/ACC2019.exe (+ _internal/)
"""

from __future__ import annotations

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None
ROOT = Path(SPECPATH).resolve()

# ── Hidden imports (lazy tabs + optional libs) ─────────────────
hidden = [
    "windnd",
    "PIL",
    "PIL.Image",
    "PIL.ImageTk",
    "PIL.ImageGrab",
    "cv2",
    "numpy",
    "tifffile",
    "bs4",
    "pyautogui",
    "pyperclip",
    "keyboard",
    "psutil",
    "websockets",
    "qrcode",
    "qrcode.image.pil",
    "win32api",
    "win32con",
    "win32gui",
    "win32process",
    "pythoncom",
    "pywintypes",
    "ctypes",
    "ctypes.wintypes",
    "tkinter",
    "tkinter.filedialog",
    "tkinter.messagebox",
    "tkinter.scrolledtext",
    "tkinter.ttk",
    "acc2019_core",
    "patch_crop",
    "dxf_convert",
    "spot_color_tif",
    "image_to_dxf",
    "csv_reader",
    "csv_reader.config",
    "csv_reader.copy_engine",
    "csv_reader.detector",
    "csv_reader.loki_mapper",
    "csv_reader.reader",
    "csv_reader.gui",
]
hidden += collect_submodules("modules")
hidden += collect_submodules("csv_reader")

# ── Data files (JSON config, assets) ───────────────────────────
datas = [
    (str(ROOT / "assets"), "assets"),
    (str(ROOT / "csv_reader" / "products_config.json"), "csv_reader"),
    (str(ROOT / "csv_reader" / "loki_products.json"), "csv_reader"),
    (str(ROOT / "csv_reader" / "loki_products_raw.json"), "csv_reader"),
    (str(ROOT / "modules" / "pet" / "config.json"), os.path.join("modules", "pet")),
]
# optional local configs (không bắt buộc)
for name in (
    "pack_config.json",
    "patch_crop_config.json",
    "quick_links.json",
    "telegram_config.json",
    "acc2019_config.json",
):
    p = ROOT / name
    if p.is_file():
        datas.append((str(p), "."))

# exclude huge / conflict (Qt multi-binding, ML, dev)
excludes = [
    "matplotlib",
    "scipy",
    "pandas",
    "IPython",
    "jupyter",
    "notebook",
    "pytest",
    "unittest",
    "test",
    "tests",
    # Qt — app dùng tkinter; yt_dlp hook kéo PyQt5+PySide6 → crash build
    "PyQt5",
    "PyQt5.QtCore",
    "PyQt5.QtGui",
    "PyQt5.QtWidgets",
    "PyQt6",
    "PySide2",
    "PySide6",
    "shiboken2",
    "shiboken6",
    # optional heavy (không cần cho hub)
    "skimage",
    "sklearn",
    "torch",
    "tensorflow",
    "cv2.gapi",
]

a = Analysis(
    [str(ROOT / "acc2019.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ACC2019",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # GUI — log trong app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=True,  # xin Admin (cài Adobe / system)
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ACC2019",
)
