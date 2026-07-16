"""LAN room host/client — UDP discover + TCP JSON rooms."""

from __future__ import annotations

import json
import socket
import threading
import time
import uuid
from typing import Any, Callable

UDP_PORT = 54331
TCP_PORT = 54330
DISCOVER_INTERVAL = 1.5


def local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def discover_rooms(timeout: float = 1.8) -> list[dict]:
    """Listen UDP HOST_ANNOUNCE briefly, return unique rooms."""
    found: dict[str, dict] = {}
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("", UDP_PORT))
    except OSError:
        # port busy — try alternate
        try:
            s.bind(("", 0))
        except OSError:
            s.close()
            return []
    s.settimeout(0.3)
    end = time.time() + timeout
    while time.time() < end:
        try:
            data, addr = s.recvfrom(2048)
            msg = json.loads(data.decode("utf-8", errors="ignore"))
            if msg.get("type") == "HOST_ANNOUNCE":
                key = f"{addr[0]}:{msg.get('room_id', '')}"
                found[key] = {
                    "host_ip": addr[0],
                    "host_name": msg.get("host_name", "?"),
                    "room_id": msg.get("room_id", ""),
                    "game": msg.get("game", ""),
                    "players": msg.get("players", 0),
                    "title": msg.get("title", "Phòng"),
                }
        except socket.timeout:
            continue
        except Exception:
            continue
    s.close()
    return list(found.values())


class RoomHost:
    """Host authoritative room state; broadcast to players + spectators."""

    def __init__(
        self,
        host_name: str,
        game: str,
        title: str = "",
        on_state: Callable[[dict], None] | None = None,
    ) -> None:
        self.host_name = host_name
        self.game = game
        self.title = title or f"{game} · {host_name}"
        self.room_id = uuid.uuid4().hex[:8]
        self.on_state = on_state
        self._running = False
        self._lock = threading.Lock()
        self._clients: list[socket.socket] = []
        self._roles: dict[socket.socket, str] = {}  # player | spectator
        self._names: dict[socket.socket, str] = {}
        self.state: dict[str, Any] = {
            "room_id": self.room_id,
            "game": game,
            "title": self.title,
            "host": host_name,
            "phase": "lobby",  # lobby | betting | playing | result
            "players": [host_name],
            "spectators": [],
            "scores": {host_name: 0},  # display only; real points local
            "bets": {},
            "payload": {},
            "history": [],
            "chat": [],
            "admin_note": "",
        }
        self._tcp = None
        self._udp = None

    def start(self) -> None:
        self._running = True
        threading.Thread(target=self._tcp_loop, daemon=True).start()
        threading.Thread(target=self._udp_loop, daemon=True).start()

    def stop(self) -> None:
        self._running = False
        for c in list(self._clients):
            try:
                c.close()
            except Exception:
                pass
        self._clients.clear()
        if self._tcp:
            try:
                self._tcp.close()
            except Exception:
                pass
        if self._udp:
            try:
                self._udp.close()
            except Exception:
                pass

    def update_state(self, **kwargs) -> None:
        with self._lock:
            self.state.update(kwargs)
            snap = json.loads(json.dumps(self.state))
        self._broadcast({"type": "STATE", "state": snap})
        if self.on_state:
            try:
                self.on_state(snap)
            except Exception:
                pass

    def mutate(self, fn: Callable[[dict], None]) -> None:
        with self._lock:
            fn(self.state)
            snap = json.loads(json.dumps(self.state))
        self._broadcast({"type": "STATE", "state": snap})
        if self.on_state:
            try:
                self.on_state(snap)
            except Exception:
                pass

    def _broadcast(self, msg: dict) -> None:
        raw = (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")
        dead = []
        with self._lock:
            clients = list(self._clients)
        for c in clients:
            try:
                c.sendall(raw)
            except Exception:
                dead.append(c)
        for c in dead:
            self._drop(c)

    def _drop(self, conn: socket.socket) -> None:
        with self._lock:
            name = self._names.pop(conn, None)
            self._roles.pop(conn, None)
            if conn in self._clients:
                self._clients.remove(conn)
            if name:
                if name in self.state["players"]:
                    self.state["players"] = [p for p in self.state["players"] if p != name]
                if name in self.state["spectators"]:
                    self.state["spectators"] = [p for p in self.state["spectators"] if p != name]
            snap = json.loads(json.dumps(self.state))
        try:
            conn.close()
        except Exception:
            pass
        self._broadcast({"type": "STATE", "state": snap})
        if self.on_state:
            try:
                self.on_state(snap)
            except Exception:
                pass

    def _udp_loop(self) -> None:
        self._udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while self._running:
            try:
                with self._lock:
                    n = len(self.state.get("players", []))
                    msg = {
                        "type": "HOST_ANNOUNCE",
                        "host_name": self.host_name,
                        "room_id": self.room_id,
                        "game": self.game,
                        "title": self.title,
                        "players": n,
                    }
                self._udp.sendto(json.dumps(msg).encode(), ("255.255.255.255", UDP_PORT))
            except Exception:
                pass
            time.sleep(DISCOVER_INTERVAL)

    def _tcp_loop(self) -> None:
        self._tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._tcp.bind(("", TCP_PORT))
        self._tcp.listen(24)
        self._tcp.settimeout(1.0)
        while self._running:
            try:
                conn, _ = self._tcp.accept()
                threading.Thread(target=self._client_loop, args=(conn,), daemon=True).start()
            except socket.timeout:
                continue
            except Exception:
                if not self._running:
                    break

    def _client_loop(self, conn: socket.socket) -> None:
        buf = b""
        try:
            conn.settimeout(60.0)
            with self._lock:
                self._clients.append(conn)
            # send hello state
            with self._lock:
                snap = json.loads(json.dumps(self.state))
            conn.sendall((json.dumps({"type": "STATE", "state": snap}) + "\n").encode())
            while self._running:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        msg = json.loads(line.decode("utf-8"))
                    except json.JSONDecodeError:
                        continue
                    self._handle(conn, msg)
        except Exception:
            pass
        finally:
            self._drop(conn)

    def _handle(self, conn: socket.socket, msg: dict) -> None:
        t = msg.get("type")
        if t == "JOIN":
            name = str(msg.get("name", "Player"))[:24]
            role = "spectator" if msg.get("spectator") else "player"
            with self._lock:
                self._names[conn] = name
                self._roles[conn] = role
                if role == "player":
                    if name not in self.state["players"]:
                        self.state["players"].append(name)
                    if name in self.state["spectators"]:
                        self.state["spectators"] = [x for x in self.state["spectators"] if x != name]
                else:
                    if name not in self.state["spectators"]:
                        self.state["spectators"].append(name)
                snap = json.loads(json.dumps(self.state))
            self._broadcast({"type": "STATE", "state": snap})
            if self.on_state:
                try:
                    self.on_state(snap)
                except Exception:
                    pass
        elif t == "CHAT":
            name = self._names.get(conn, "?")
            text = str(msg.get("text", ""))[:120]
            with self._lock:
                self.state.setdefault("chat", []).append(f"{name}: {text}")
                self.state["chat"] = self.state["chat"][-40:]
                snap = json.loads(json.dumps(self.state))
            self._broadcast({"type": "STATE", "state": snap})
        elif t in ("MSG", "LIVE_BET", "ADMIN_POINTS"):
            name = self._names.get(conn, "?")
            # Live bet from client
            action = msg.get("action") or t
            if action == "LIVE_BET" or t == "LIVE_BET":
                amount = int(msg.get("amount") or 0)
                choice = str(msg.get("choice") or "")
                if amount > 0 and choice:
                    with self._lock:
                        if self.state.get("phase") == "betting":
                            self.state.setdefault("bets", {})[name] = {
                                "choice": choice, "amount": amount,
                            }
                        snap = json.loads(json.dumps(self.state))
                    self._broadcast({"type": "STATE", "state": snap})
                    if self.on_state:
                        try:
                            self.on_state(snap)
                        except Exception:
                            pass
                return
            if self.on_state:
                try:
                    self.on_state({"__client_msg__": True, "from": name, "msg": msg})
                except Exception:
                    pass
            if msg.get("broadcast") or t == "ADMIN_POINTS":
                self._broadcast(msg)


class RoomClient:
    def __init__(
        self,
        host_ip: str,
        name: str,
        *,
        spectator: bool = False,
        on_state: Callable[[dict], None] | None = None,
        on_msg: Callable[[dict], None] | None = None,
    ) -> None:
        self.host_ip = host_ip
        self.name = name
        self.spectator = spectator
        self.on_state = on_state
        self.on_msg = on_msg
        self._sock: socket.socket | None = None
        self._running = False
        self.state: dict = {}

    def connect(self) -> bool:
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.settimeout(4.0)
            self._sock.connect((self.host_ip, TCP_PORT))
            self._sock.settimeout(None)
            self._running = True
            self.send({"type": "JOIN", "name": self.name, "spectator": self.spectator})
            threading.Thread(target=self._recv_loop, daemon=True).start()
            return True
        except Exception:
            self._running = False
            return False

    def send(self, msg: dict) -> None:
        if not self._sock:
            return
        try:
            self._sock.sendall((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
        except Exception:
            self.close()

    def close(self) -> None:
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def _recv_loop(self) -> None:
        buf = b""
        while self._running and self._sock:
            try:
                chunk = self._sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        msg = json.loads(line.decode("utf-8"))
                    except json.JSONDecodeError:
                        continue
                    if msg.get("type") == "STATE":
                        self.state = msg.get("state") or {}
                        if self.on_state:
                            self.on_state(self.state)
                    elif self.on_msg:
                        self.on_msg(msg)
            except Exception:
                break
        self.close()
