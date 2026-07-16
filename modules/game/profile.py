"""Hồ sơ người chơi — điểm, daily, lịch sử, tên thiết bị."""

from __future__ import annotations

import json
import os
import socket
import time
from datetime import datetime
from typing import Any

DAILY_BONUS = 10_000
DEFAULT_POINTS = 10_000
ADMIN_PASS = "TX"
HISTORY_MAX = 200


def default_device_name() -> str:
    try:
        return socket.gethostname() or "Player"
    except Exception:
        return "Player"


class PlayerProfile:
    def __init__(self, base_dir: str) -> None:
        self.path = os.path.join(base_dir, "game_profile.json")
        self.data: dict[str, Any] = {
            "name": default_device_name(),
            "points": DEFAULT_POINTS,
            "last_daily_ts": 0,
            "total_won": 0,
            "total_lost": 0,
            "games_played": 0,
            "history": [],
            "stats": {},  # game_id -> {wins, losses, wagered}
        }
        self.load()
        self.claim_daily_if_due()

    def load(self) -> None:
        if not os.path.isfile(self.path):
            # lần đầu: điểm mặc định, daily bắt đầu đếm từ bây giờ
            self.data["last_daily_ts"] = time.time()
            self.save()
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                self.data.update(raw)
        except (OSError, json.JSONDecodeError):
            pass
        if not self.data.get("name"):
            self.data["name"] = default_device_name()

    def save(self) -> None:
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    @property
    def name(self) -> str:
        return str(self.data.get("name") or default_device_name())

    @name.setter
    def name(self, v: str) -> None:
        self.data["name"] = (v or default_device_name()).strip()[:24]
        self.save()

    @property
    def points(self) -> int:
        return int(self.data.get("points", 0))

    def set_points(self, n: int) -> None:
        self.data["points"] = max(0, int(n))
        self.save()

    def add_points(self, n: int, *, reason: str = "") -> int:
        self.data["points"] = max(0, self.points + int(n))
        if n > 0:
            self.data["total_won"] = int(self.data.get("total_won", 0)) + n
        elif n < 0:
            self.data["total_lost"] = int(self.data.get("total_lost", 0)) - n
        self.save()
        return self.points

    def claim_daily_if_due(self) -> int:
        """Cộng 10000 nếu đã qua 24h. Trả về số điểm nhận (0 nếu chưa đến hạn)."""
        now = time.time()
        last = float(self.data.get("last_daily_ts") or 0)
        if now - last >= 24 * 3600:
            self.data["last_daily_ts"] = now
            self.data["points"] = self.points + DAILY_BONUS
            self.save()
            return DAILY_BONUS
        return 0

    def seconds_to_daily(self) -> int:
        last = float(self.data.get("last_daily_ts") or 0)
        left = 24 * 3600 - (time.time() - last)
        return max(0, int(left))

    def record_game(
        self,
        game: str,
        result: str,
        bet: int,
        delta: int,
        detail: str = "",
    ) -> None:
        self.data["games_played"] = int(self.data.get("games_played", 0)) + 1
        st = self.data.setdefault("stats", {})
        g = st.setdefault(game, {"wins": 0, "losses": 0, "wagered": 0})
        g["wagered"] = int(g.get("wagered", 0)) + abs(bet)
        if delta > 0:
            g["wins"] = int(g.get("wins", 0)) + 1
        elif delta < 0:
            g["losses"] = int(g.get("losses", 0)) + 1
        hist = self.data.setdefault("history", [])
        hist.insert(0, {
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "game": game,
            "result": result,
            "bet": bet,
            "delta": delta,
            "detail": detail[:80],
            "points_after": self.points,
        })
        self.data["history"] = hist[:HISTORY_MAX]
        self.save()

    def history(self, limit: int = 50) -> list[dict]:
        return list(self.data.get("history", [])[:limit])
