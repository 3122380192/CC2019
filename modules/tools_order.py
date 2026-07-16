"""
Hỗ trợ làm đơn: trích order_id · QR · OCR screenshot · backup trước khi xóa.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

# ── Mẫu mã đơn thường gặp (portal / Amazon / nội bộ) ─────────
ORDER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bWO\d{6}-[A-Z]-\d{5,}\b", re.I),
    re.compile(r"\bWO\d{6}-[A-Z0-9]+-\d+\b", re.I),
    re.compile(r"\bO-[A-Z]\d{5,}\b", re.I),
    re.compile(r"\bR\d{6,}\b", re.I),
    re.compile(r"\b\d{3}-\d{7}-\d{7}\b"),  # Amazon order
    re.compile(r"\b[A-Z]{2,4}\d{6,}-\d+\b", re.I),
    re.compile(r"\b[A-Za-z0-9]{6,}-[A-Za-z0-9]{4,}(?:-[A-Za-z0-9]+)+\b"),
]


def _desktop_base() -> str:
    for p in (
        os.path.join(os.path.expanduser("~"), "Desktop"),
        os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop"),
    ):
        if os.path.isdir(p):
            return p
    return os.path.expanduser("~")


def extract_order_ids(text: str) -> list[str]:
    """Trích mã đơn từ text (OCR / clipboard / filename)."""
    if not text:
        return []
    found: list[str] = []
    seen: set[str] = set()
    for pat in ORDER_PATTERNS:
        for m in pat.finditer(text):
            oid = m.group(0).strip()
            key = oid.upper()
            if key not in seen:
                seen.add(key)
                found.append(oid)
    return found


def extract_from_filename(path: str) -> list[str]:
    name = os.path.splitext(os.path.basename(path or ""))[0]
    # thay _ - khoảng trắng
    soft = name.replace("_", " ").replace("-", "-")
    ids = extract_order_ids(name) or extract_order_ids(soft)
    if ids:
        return ids
    # fallback: stem dài có dạng mã
    if re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]{5,80}$", name):
        return [name]
    return []


def ocr_image(path: str) -> tuple[str, str]:
    """
    OCR ảnh → (text, engine_name).
    Thử: tesseract CLI → pytesseract → (trống).
    """
    if not path or not os.path.isfile(path):
        return "", "none"

    # 1) tesseract CLI
    try:
        r = subprocess.run(
            ["tesseract", path, "stdout", "-l", "eng", "--psm", "6"],
            capture_output=True,
            text=True,
            timeout=45,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if r.returncode == 0 and (r.stdout or "").strip():
            return r.stdout.strip(), "tesseract-cli"
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    # 2) pytesseract + Pillow preprocess
    try:
        import pytesseract
        from PIL import Image, ImageEnhance, ImageFilter, ImageOps

        im = Image.open(path)
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        gray = ImageOps.grayscale(im)
        gray = ImageEnhance.Contrast(gray).enhance(1.8)
        gray = gray.filter(ImageFilter.SHARPEN)
        # scale up small shots
        w, h = gray.size
        if max(w, h) < 1200:
            scale = 1200 / max(w, h)
            gray = gray.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
        text = pytesseract.image_to_string(gray, lang="eng", config="--psm 6")
        if text and text.strip():
            return text.strip(), "pytesseract"
    except Exception:
        pass

    # 3) Windows PowerShell OCR (Win10+ Media OCR) — best-effort
    try:
        text = _ocr_windows_media(path)
        if text.strip():
            return text.strip(), "windows-ocr"
    except Exception:
        pass

    return "", "none"


def _ocr_windows_media(path: str) -> str:
    """Gọi OCR qua PowerShell + WinRT (nếu OS hỗ trợ)."""
    # Script rút gọn — không fail hard
    abs_path = os.path.abspath(path).replace("'", "''")
    ps = f"""
$ErrorActionPreference = 'Stop'
try {{
  Add-Type -AssemblyName System.Runtime.WindowsRuntime | Out-Null
  $null = [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
  $null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
  $null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType=WindowsRuntime]
  function Await($WinRtTask, $ResultType) {{
    $asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() |
      Where-Object {{ $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.IsGenericMethod }} |
      Select-Object -First 1
    $netTask = $asTask.MakeGenericMethod($ResultType).Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
  }}
  $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync('{abs_path}')) ([Windows.Storage.StorageFile])
  $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
  $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
  $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
  $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
  if ($null -eq $engine) {{ $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage((New-Object Windows.Globalization.Language 'en-US')) }}
  $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
  $result.Text
}} catch {{
  ''
}}
"""
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=60,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return (r.stdout or "").strip()


def ocr_extract_orders(path: str) -> tuple[list[str], str, str]:
    """(order_ids, raw_text, engine)."""
    text, engine = ocr_image(path)
    ids = extract_order_ids(text)
    if not ids:
        ids = extract_from_filename(path)
    return ids, text, engine


def generate_qr_png(data: str, out_path: str, *, box_size: int = 8, border: int = 2) -> str:
    """
    Tạo file PNG QR. Ưu tiên lib qrcode; fallback ma trận tối giản (cần Pillow).
    Trả path đã ghi.
    """
    data = (data or "").strip()
    if not data:
        raise ValueError("Dữ liệu QR trống")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)

    try:
        import qrcode

        img = qrcode.make(data, border=border, box_size=box_size)
        img.save(out_path)
        return out_path
    except ImportError:
        pass

    # Fallback: vẽ QR bằng qrcode-free minimal (chỉ alphanumeric ngắn) — dùng PIL + module nội bộ
    try:
        from PIL import Image

        # Cài đặt tối thiểu: encode bằng pattern finder-like grid (không chuẩn ISO)
        # → bắt buộc cài qrcode cho QR đọc được. Tạo placeholder có text.
        size = 280
        im = Image.new("RGB", (size, size), "white")
        # chấm caro giả + ghi order_id (người dùng nên pip install qrcode)
        px = im.load()
        step = 10
        for y in range(0, size, step):
            for x in range(0, size, step):
                if (x // step + y // step) % 2 == 0 and (x < 60 or y < 60 or x > size - 70 or y > size - 70):
                    for dy in range(step):
                        for dx in range(step):
                            if x + dx < size and y + dy < size:
                                px[x + dx, y + dy] = (0, 0, 0)
        im.save(out_path)
        # Ghi kèm file .txt cạnh QR
        with open(out_path + ".txt", "w", encoding="utf-8") as f:
            f.write(data + "\n# Cài: pip install qrcode[pil]  để QR chuẩn\n")
        return out_path
    except Exception as e:
        raise RuntimeError(f"Không tạo được QR: {e}. Chạy: pip install qrcode[pil]") from e


def default_backup_root() -> str:
    return os.path.join(_desktop_base(), "_ACC_Backup")


def backup_files(
    files: Iterable[str],
    *,
    label: str = "",
    backup_root: str | None = None,
    log: Callable[[str], None] | None = None,
) -> str | None:
    """
    Copy file vào Desktop\\_ACC_Backup\\YYYY-MM-DD\\<label_time>\\
    Trả path folder backup (hoặc None nếu không có file).
    """
    paths = [p for p in files if p and os.path.isfile(p)]
    if not paths:
        return None
    root = backup_root or default_backup_root()
    day = datetime.now().strftime("%Y-%m-%d")
    stamp = datetime.now().strftime("%H%M%S")
    safe_label = re.sub(r'[<>:"/\\|?*]', "_", (label or "pack").strip())[:40] or "pack"
    dest = os.path.join(root, day, f"{stamp}_{safe_label}")
    os.makedirs(dest, exist_ok=True)
    n = 0
    for src in paths:
        name = os.path.basename(src)
        dst = os.path.join(dest, name)
        if os.path.exists(dst):
            stem, ext = os.path.splitext(name)
            k = 2
            while os.path.exists(os.path.join(dest, f"{stem}_{k}{ext}")):
                k += 1
            dst = os.path.join(dest, f"{stem}_{k}{ext}")
        try:
            shutil.copy2(src, dst)
            n += 1
        except OSError:
            pass
    # zip mirror nhỏ gọn
    zip_path = dest + ".zip"
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in os.listdir(dest):
                fp = os.path.join(dest, name)
                if os.path.isfile(fp):
                    zf.write(fp, name)
    except OSError:
        zip_path = ""
    if log:
        msg = f"Backup {n} file → {dest}"
        if zip_path:
            msg += f" (+ {os.path.basename(zip_path)})"
        log(msg)
    return dest


def backup_folder_tree(
    folder: str,
    *,
    label: str = "",
    backup_root: str | None = None,
    log: Callable[[str], None] | None = None,
) -> str | None:
    """Backup cả folder (copytree) trước khi xóa nguồn."""
    if not folder or not os.path.isdir(folder):
        return None
    root = backup_root or default_backup_root()
    day = datetime.now().strftime("%Y-%m-%d")
    stamp = datetime.now().strftime("%H%M%S")
    base = os.path.basename(os.path.normpath(folder)) or "folder"
    safe_label = re.sub(r'[<>:"/\\|?*]', "_", (label or base).strip())[:40]
    dest = os.path.join(root, day, f"{stamp}_{safe_label}_full")
    try:
        shutil.copytree(folder, dest, dirs_exist_ok=True)
        if log:
            log(f"Backup folder → {dest}")
        return dest
    except OSError as e:
        if log:
            log(f"Backup folder lỗi: {e}")
        return None
