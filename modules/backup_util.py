"""Backup / restore cấu hình ACC2019."""

from __future__ import annotations

import os
import shutil
import zipfile
from datetime import datetime

# File / folder quan trọng cần backup
BACKUP_ITEMS = (
    "acc2019_window.json",
    "acc2019_config.json",
    "acc2019_history.txt",
    "quick_links.json",
    "patch_crop_config.json",
    "emb_pins.json",
    "csv_reader/products_config.json",
    "csv_reader/emb_daily_stats.json",
)


def _desktop() -> str:
    for p in (
        os.path.join(os.path.expanduser("~"), "Desktop"),
        os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop"),
    ):
        if os.path.isdir(p):
            return p
    return os.path.expanduser("~")


def create_backup(base_dir: str, dest_dir: str | None = None) -> str:
    """
    Nén config → Desktop/ACC2019_backup_YYYYMMDD_HHMMSS.zip
    Trả về đường dẫn file zip.
    """
    dest_dir = dest_dir or _desktop()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = os.path.join(dest_dir, f"ACC2019_backup_{stamp}.zip")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in BACKUP_ITEMS:
            full = os.path.join(base_dir, rel.replace("/", os.sep))
            if os.path.isfile(full):
                zf.write(full, arcname=rel.replace("\\", "/"))
        # meta
        meta = f"ACC2019 backup\nbase={base_dir}\ntime={stamp}\n"
        zf.writestr("_backup_meta.txt", meta)

    return zip_path


def restore_backup(zip_path: str, base_dir: str) -> list[str]:
    """Giải nén backup vào base_dir. Trả về list file đã restore."""
    restored: list[str] = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            if name.startswith("_") or name.endswith("/"):
                continue
            target = os.path.join(base_dir, name.replace("/", os.sep))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(name) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            restored.append(name)
    return restored
