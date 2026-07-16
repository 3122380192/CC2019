"""Gửi thông báo mã đơn lên Telegram (không chặn UI)."""

from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

_BASE = Path(__file__).resolve().parents[1]
CONFIG_NAME = "telegram_config.json"

# Mặc định theo cấu hình user (có thể sửa file telegram_config.json)
_DEFAULT = {
    "enabled": True,
    "bot_token": "7931663050:AAH3E2d7rDq3A553o7V9okU8TQixX1HAGcg",
    "chat_id": "-5022971494",
}


def config_path(base_dir: str | None = None) -> str:
    root = base_dir or str(_BASE)
    return os.path.join(root, CONFIG_NAME)


def load_config(base_dir: str | None = None) -> dict:
    path = config_path(base_dir)
    data = dict(_DEFAULT)
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                data.update(raw)
        except (OSError, json.JSONDecodeError):
            pass
    else:
        # tạo file để user chỉnh sau
        try:
            save_config(data, base_dir)
        except OSError:
            pass
    return data


def save_config(cfg: dict, base_dir: str | None = None) -> None:
    path = config_path(base_dir)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _resolve_base_dir(base_dir: str | None) -> str:
    """Ưu tiên base_dir app, fallback thư mục project (chứa telegram_config.json)."""
    candidates = []
    if base_dir:
        candidates.append(base_dir)
    candidates.append(str(_BASE))
    # cwd khi chạy run.bat
    try:
        candidates.append(os.getcwd())
    except Exception:
        pass
    for c in candidates:
        if c and os.path.isfile(os.path.join(c, CONFIG_NAME)):
            return c
    return base_dir or str(_BASE)


def send_message(
    text: str,
    *,
    base_dir: str | None = None,
    token: str | None = None,
    chat_id: str | None = None,
    timeout: float = 15.0,
    retries: int = 2,
) -> tuple[bool, str]:
    """Gửi tin nhắn (tự động, có retry). Trả (ok, detail)."""
    base = _resolve_base_dir(base_dir)
    cfg = load_config(base)
    if not cfg.get("enabled", True):
        return False, "Telegram tắt (enabled=false trong telegram_config.json)"
    token = (token or cfg.get("bot_token") or _DEFAULT["bot_token"] or "").strip()
    chat_id = str(chat_id or cfg.get("chat_id") or _DEFAULT["chat_id"] or "").strip()
    if not token or not chat_id:
        return False, "Thiếu bot_token / chat_id"
    if not (text or "").strip():
        return False, "Tin trống"

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text[:4000],
        "disable_web_page_preview": "true",
    }).encode("utf-8")

    last_err = ""
    for attempt in range(max(1, retries)):
        req = urllib.request.Request(
            url,
            data=payload,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", errors="ignore")
            try:
                data = json.loads(body)
                if data.get("ok"):
                    return True, "sent"
                last_err = str(data.get("description") or body)[:200]
            except json.JSONDecodeError:
                return True, "sent"
        except urllib.error.HTTPError as e:
            try:
                err = e.read().decode("utf-8", errors="ignore")[:200]
            except Exception:
                err = str(e)
            last_err = f"HTTP {e.code}: {err}"
        except Exception as e:
            last_err = str(e)[:200]
        if attempt + 1 < retries:
            import time
            time.sleep(0.6 * (attempt + 1))
    return False, last_err or "send failed"


def send_message_async(
    text: str,
    *,
    base_dir: str | None = None,
    on_done: Callable[[bool, str], None] | None = None,
) -> None:
    """Gửi nền — tự động, không block UI, không cần phím tắt."""

    def _work():
        ok, detail = send_message(text, base_dir=base_dir, retries=2)
        if on_done:
            try:
                on_done(ok, detail)
            except Exception:
                pass

    threading.Thread(target=_work, daemon=True, name="tg-send").start()


def format_order_message(
    order_id: str,
    product_name: str = "",
    *,
    tool_count: int = 0,
    folder_count: int = 0,
    time_str: str = "",
    date_str: str = "",
    folder_path: str = "",
) -> str:
    """Tin nhắn thống kê khi nhận đơn mới (không trùng)."""
    lines = [
        "📦 ĐƠN MỚI",
        f"Mã: {order_id}",
    ]
    if product_name:
        lines.append(f"SP: {product_name[:80]}")
    if time_str:
        lines.append(f"Giờ: {time_str}")
    lines.append("")
    lines.append("📊 Thống kê hôm nay")
    lines.append(f"• Đơn tool (không trùng): {tool_count}")
    lines.append(f"• Folder trên Desktop\\ngày: {folder_count}")
    if date_str:
        lines.append(f"• Ngày: {date_str}")
    if folder_path:
        lines.append(f"• Path: {folder_path}")
    return "\n".join(lines)


def notify_new_order(
    order_id: str,
    product_name: str = "",
    *,
    base_dir: str | None = None,
    tool_count: int = 0,
    folder_count: int = 0,
    time_str: str = "",
    date_str: str = "",
    folder_path: str = "",
    on_done: Callable[[bool, str], None] | None = None,
) -> None:
    """Gửi Telegram khi pick đơn mới (caller đã check không trùng)."""
    text = format_order_message(
        order_id,
        product_name,
        tool_count=tool_count,
        folder_count=folder_count,
        time_str=time_str,
        date_str=date_str,
        folder_path=folder_path,
    )
    send_message_async(text, base_dir=base_dir, on_done=on_done)
