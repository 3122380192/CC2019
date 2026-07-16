"""Launcher for ChestEMB (Thêu bảng đơn)."""

import os
import subprocess
import sys


def resolve_theu_dir(base_dir=None, config=None):
    base_dir = base_dir or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if config:
        raw = config.get("theu_path", "")
        if raw:
            if os.path.isabs(raw):
                return raw
            return os.path.normpath(os.path.join(base_dir, raw))

    return os.environ.get(
        "ACC2019_THEU_PATH",
        r"E:\AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\vibecoder\ChestEMB",
    )


def find_entry(theu_dir):
    candidates = [
        os.path.join(theu_dir, "app.py"),
        os.path.join(theu_dir, "dist", "Tx6.exe"),
        os.path.join(theu_dir, "Tx6.exe"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def launch(theu_dir=None, base_dir=None, config=None):
    theu_dir = theu_dir or resolve_theu_dir(base_dir=base_dir, config=config)
    entry = find_entry(theu_dir)
    if not entry:
        raise FileNotFoundError(f"Không tìm thấy ChestEMB tại:\n{theu_dir}")

    if entry.lower().endswith(".py"):
        return subprocess.Popen([sys.executable, entry], cwd=theu_dir)
    return subprocess.Popen([entry], cwd=os.path.dirname(entry) or theu_dir)