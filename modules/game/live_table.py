"""
Sòng live LAN — chu kỳ 20s cho Tài xỉu / Xóc đĩa / Bầu cua.
Tự host khi mở tool; ghi history; admin force + cộng điểm người chơi.
"""

from __future__ import annotations

import json
import os
import random
import threading
import time
from datetime import datetime
from typing import Any, Callable

from modules.game.lan_net import RoomHost, TCP_PORT, local_ip

ROUND_SEC = 20
BAUCUA = ["Cá", "Cua", "Tôm", "Nai", "Gà", "Bầu"]


class LiveCasinoEngine:
    """
    Host 1 phòng live, xoay game cược theo chu kỳ 20s.
    Bets: name -> {game_choice fields, amount}
    """

    def __init__(
        self,
        host_name: str,
        base_dir: str,
        on_tick: Callable[[dict], None] | None = None,
        games: tuple[str, ...] = ("taixiu", "xocdia", "baucua"),
    ) -> None:
        self.host_name = host_name
        self.base_dir = base_dir
        self.on_tick = on_tick
        self.games = list(games)
        self.game_i = 0
        self.running = False
        self.host: RoomHost | None = None
        self._thread: threading.Thread | None = None
        self.force_result: str | None = None  # admin
        self.history_path = os.path.join(base_dir, "game_live_history.json")
        self.round_history: list[dict] = []
        self._load_hist()

    def _load_hist(self) -> None:
        if os.path.isfile(self.history_path):
            try:
                with open(self.history_path, encoding="utf-8") as f:
                    self.round_history = json.load(f)[:300]
            except Exception:
                self.round_history = []

    def _save_hist(self) -> None:
        try:
            with open(self.history_path, "w", encoding="utf-8") as f:
                json.dump(self.round_history[:300], f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    @property
    def current_game(self) -> str:
        return self.games[self.game_i % len(self.games)]

    def start(self) -> str:
        if self.running:
            return self.host.room_id if self.host else ""
        self.host = RoomHost(
            self.host_name,
            game="live_casino",
            title=f"Sòng Live · {self.host_name}",
            on_state=self._on_client_side,
        )
        # handle client messages
        original = self.host.on_state

        def wrapped(state):
            if isinstance(state, dict) and state.get("__client_msg__"):
                self._handle_client_msg(state)
                return
            if original:
                original(state)

        self.host.on_state = wrapped
        self.host.start()
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self.host.room_id

    def stop(self) -> None:
        self.running = False
        if self.host:
            self.host.stop()
            self.host = None

    def _on_client_side(self, state: dict) -> None:
        if self.on_tick and not state.get("__client_msg__"):
            try:
                self.on_tick(state)
            except Exception:
                pass

    def _handle_client_msg(self, packet: dict) -> None:
        msg = packet.get("msg") or {}
        name = packet.get("from", "?")
        t = msg.get("type")
        if t == "LIVE_BET" and self.host:
            amount = int(msg.get("amount") or 0)
            choice = str(msg.get("choice") or "")
            if amount <= 0 or not choice:
                return

            def mut(st):
                if st.get("phase") != "betting":
                    return
                bets = st.setdefault("bets", {})
                bets[name] = {"choice": choice, "amount": amount, "ts": time.time()}

            self.host.mutate(mut)
        elif t == "ADMIN_ADD" and self.host:
            # only trusted if from host process — admin applies locally via add_points_to
            pass

    def set_force(self, result: str | None) -> None:
        self.force_result = result or None

    def add_points_broadcast(self, player: str, amount: int) -> None:
        """Gửi lệnh cộng điểm tới client (client tự cộng local nếu tên khớp)."""
        if not self.host:
            return
        self.host._broadcast({
            "type": "ADMIN_POINTS",
            "player": player,
            "amount": int(amount),
            "broadcast": True,
        })
        def mut(st):
            chat = st.setdefault("chat", [])
            chat.append(f"[ADMIN] +{amount} → {player}")
            st["chat"] = chat[-40:]
        self.host.mutate(mut)

    def _loop(self) -> None:
        while self.running and self.host:
            game = self.current_game
            # BETTING phase
            for left in range(ROUND_SEC, 0, -1):
                if not self.running:
                    return
                self.host.update_state(
                    phase="betting",
                    live_game=game,
                    time_left=left,
                    payload={"hint": f"Đặt cược {game} — còn {left}s"},
                    result="",
                )
                if self.on_tick:
                    try:
                        self.on_tick(self.host.state)
                    except Exception:
                        pass
                time.sleep(1)

            if not self.running or not self.host:
                return

            # ROLL
            self.host.update_state(phase="rolling", time_left=0, payload={"hint": "Đang lắc…"})
            time.sleep(1.2)
            result = self._roll(game)
            # settle info for UI (actual points settled on each client by choice match)
            record = {
                "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "game": game,
                "result": result,
                "bets": dict(self.host.state.get("bets") or {}),
            }
            self.round_history.insert(0, record)
            self._save_hist()

            def mut(st):
                st["phase"] = "result"
                st["result"] = result
                st["payload"] = {"result": result, "game": game}
                hist = st.setdefault("history", [])
                hist.insert(0, f"{game}:{result}")
                st["history"] = hist[:30]
                # clear bets for next
                st["bets"] = {}

            self.host.mutate(mut)
            if self.on_tick:
                try:
                    self.on_tick(self.host.state)
                except Exception:
                    pass
            time.sleep(4)
            self.force_result = None
            self.game_i += 1

    def _roll(self, game: str) -> str:
        if self.force_result:
            return self.force_result
        if game == "taixiu":
            dice = [random.randint(1, 6) for _ in range(3)]
            total = sum(dice)
            side = "tai" if total >= 11 else "xiu"
            if len(set(dice)) == 1:
                return f"bao:{total}:{dice}"
            return f"{side}:{total}:{dice}"
        if game == "xocdia":
            bits = [random.randint(0, 1) for _ in range(4)]
            red = sum(bits)
            parity = "chan" if red % 2 == 0 else "le"
            return f"{parity}:{red}:{bits}"
        if game == "baucua":
            faces = [random.randint(0, 5) for _ in range(3)]
            names = [BAUCUA[i] for i in faces]
            return f"bc:{','.join(names)}:{faces}"
        return "none"
