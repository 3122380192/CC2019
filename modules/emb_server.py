"""HTTP + WebSocket + Clipboard receiver cho Tampermonkey EMB V5.7."""

from __future__ import annotations

import asyncio
import json
import threading
import tkinter as tk
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable

APP_NAME = "ACC2019 EMB"
APP_VERSION = "2.8.0"
HTTP_PORT = 5000
WS_PORT = 5001
CLIP_MARKER = "TX_EMB::"
CLIP_POLL_MS = 400


class _EmbHttpHandler(BaseHTTPRequestHandler):
    server_version = "ACC2019-EMB/1.0"

    def log_message(self, format, *args) -> None:
        return

    def _send_json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path in ("/info", "/ws_info"):
            self._send_json(200, {
                "name": APP_NAME,
                "version": APP_VERSION,
                "ws_port": WS_PORT,
                "ws_url": f"ws://127.0.0.1:{WS_PORT}",
            })
        elif path == "/cmd/download_image":
            ok = False
            try:
                ok = bool(self.server.request_download_image())  # type: ignore[attr-defined]
            except Exception:
                ok = False
            self._send_json(200 if ok else 503, {
                "status": "ok" if ok else "no_clients",
                "action": "download_image",
                "clients": getattr(self.server, "ws_client_count", lambda: 0)(),
            })
        else:
            self._send_json(404, {"status": "not_found"})

    def do_POST(self) -> None:
        path = self.path.split("?")[0]
        if path == "/cmd/download_image":
            ok = False
            try:
                ok = bool(self.server.request_download_image())  # type: ignore[attr-defined]
            except Exception:
                ok = False
            self._send_json(200 if ok else 503, {
                "status": "ok" if ok else "no_clients",
                "action": "download_image",
            })
            return
        if path != "/receive":
            self._send_json(404, {"status": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            data = json.loads(raw.decode("utf-8") or "{}")
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "test" not in item:
                        self.server.on_data(item)  # type: ignore[attr-defined]
            elif isinstance(data, dict) and "test" not in data:
                self.server.on_data(data)  # type: ignore[attr-defined]
            self._send_json(200, {"status": "success"})
        except Exception as exc:
            self._send_json(500, {"status": "error", "message": str(exc)})


class EmbDataServer:
    """HTTP server + WebSocket (download_image) + clipboard polling."""

    def __init__(self, on_data: Callable[[dict], None], root) -> None:
        self._on_data = on_data
        self._root = root
        self._http: HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._ws_thread: threading.Thread | None = None
        self._last_clip = ""
        self._clip_job = None
        self.running = False

        # WebSocket state (asyncio loop lives in background thread)
        self._ws_loop: asyncio.AbstractEventLoop | None = None
        self._ws_clients: set = set()
        self._ws_lock = threading.Lock()

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._start_http()
        self._start_ws()
        self._schedule_clip_poll()

    def stop(self) -> None:
        self.running = False
        if self._clip_job:
            try:
                self._root.after_cancel(self._clip_job)
            except Exception:
                pass
        if self._http:
            try:
                self._http.shutdown()
            except Exception:
                pass
        if self._ws_loop:
            try:
                self._ws_loop.call_soon_threadsafe(self._ws_loop.stop)
            except Exception:
                pass

    # ── public API ──────────────────────────────────────────────────────────

    def request_download_image(self) -> bool:
        """Gửi {action: download_image} tới mọi client Tampermonkey (WS)."""
        payload = json.dumps({"action": "download_image"})
        with self._ws_lock:
            clients = list(self._ws_clients)
        if not clients or not self._ws_loop:
            return False

        async def _broadcast():
            dead = []
            for ws in clients:
                try:
                    await ws.send(payload)
                except Exception:
                    dead.append(ws)
            if dead:
                with self._ws_lock:
                    for ws in dead:
                        self._ws_clients.discard(ws)

        try:
            fut = asyncio.run_coroutine_threadsafe(_broadcast(), self._ws_loop)
            fut.result(timeout=2.0)
            return True
        except Exception:
            return False

    def ws_client_count(self) -> int:
        with self._ws_lock:
            return len(self._ws_clients)

    # ── HTTP ────────────────────────────────────────────────────────────────

    def _start_http(self) -> None:
        outer = self

        class Server(HTTPServer):
            def on_data(self, data: dict) -> None:
                outer._emit_data(data)

            def request_download_image(self) -> bool:
                return outer.request_download_image()

            def ws_client_count(self) -> int:
                return outer.ws_client_count()

        try:
            self._http = Server(("127.0.0.1", HTTP_PORT), _EmbHttpHandler)
        except OSError as exc:
            self._emit_data({"__error__": f"HTTP :{HTTP_PORT} — {exc}"})
            return

        def run():
            try:
                self._http.serve_forever(poll_interval=0.5)
            except Exception:
                pass

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    # ── WebSocket ───────────────────────────────────────────────────────────

    def _start_ws(self) -> None:
        def run():
            try:
                import websockets
            except ImportError:
                self._emit_data({"__error__": "Thiếu package websockets — pip install websockets"})
                return

            # websockets 10+ / 16: prefer asyncio.server, fallback legacy
            try:
                from websockets.asyncio.server import serve as ws_serve
            except ImportError:
                try:
                    from websockets.server import serve as ws_serve
                except ImportError:
                    ws_serve = websockets.serve  # type: ignore[attr-defined]

            async def handler(ws, *args):
                with self._ws_lock:
                    self._ws_clients.add(ws)
                try:
                    try:
                        await ws.send(json.dumps({
                            "name": APP_NAME,
                            "version": APP_VERSION,
                        }))
                    except Exception:
                        pass
                    async for message in ws:
                        try:
                            data = json.loads(message)
                        except (json.JSONDecodeError, TypeError):
                            continue
                        if isinstance(data, dict) and "test" not in data and "action" not in data:
                            if data.get("order_id") or data.get("image_url"):
                                self._emit_data(data)
                finally:
                    with self._ws_lock:
                        self._ws_clients.discard(ws)

            async def main():
                async with ws_serve(handler, "127.0.0.1", WS_PORT):
                    await asyncio.Future()

            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                self._ws_loop = loop
                loop.run_until_complete(main())
            except OSError as exc:
                self._emit_data({"__error__": f"WS :{WS_PORT} — {exc}"})
            except Exception as exc:
                self._emit_data({"__error__": f"WS lỗi: {exc}"})

        self._ws_thread = threading.Thread(target=run, daemon=True)
        self._ws_thread.start()

    def _emit_data(self, data: dict) -> None:
        if "__error__" in data:
            self._root.after(0, lambda: self._on_data(data))
            return
        self._root.after(0, lambda d=dict(data): self._on_data(d))

    def _schedule_clip_poll(self) -> None:
        if not self.running:
            return
        self._poll_clipboard()
        self._clip_job = self._root.after(CLIP_POLL_MS, self._schedule_clip_poll)

    def _poll_clipboard(self) -> None:
        try:
            text = self._root.clipboard_get().strip()
        except tk.TclError:
            return
        except Exception:
            return

        if not text or text == self._last_clip or not text.startswith(CLIP_MARKER):
            return

        payload_str = text[len(CLIP_MARKER):]
        try:
            data = json.loads(payload_str)
        except json.JSONDecodeError:
            return

        if not isinstance(data, dict) or "test" in data:
            return

        self._last_clip = ""
        try:
            self._root.clipboard_clear()
        except Exception:
            pass
        self._emit_data(data)
