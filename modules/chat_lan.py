"""Tab Chat LAN — text màu, kéo thả file/ảnh, preview + download khi nhận."""

from __future__ import annotations

import base64
import json
import os
import socket
import threading
import time
import tkinter as tk
import uuid
from datetime import datetime
from tkinter import colorchooser, filedialog, messagebox, scrolledtext, simpledialog

UDP_PORT = 54341
TCP_PORT = 54340
MAX_FILE_B = 4_000_000  # 4MB raw

BG, CARD, TEXT, MUTED = "#0c0c14", "#141424", "#e8e8f0", "#82829c"
ACCENT, SUCCESS, GOLD = "#00d2ff", "#00e676", "#fbbf24"


def _local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _device_name() -> str:
    try:
        return socket.gethostname()[:20]
    except Exception:
        return "User"


def _safe_drop_path(f) -> str:
    """Decode path từ windnd (bytes/str) — chống crash encoding Windows."""
    try:
        if isinstance(f, bytes):
            # force_unicode thường trả str; nếu vẫn bytes thử nhiều codec
            for enc in ("utf-16-le", "utf-8", "mbcs", "cp1258", "latin-1"):
                try:
                    p = f.decode(enc)
                    p = p.replace("\x00", "").strip().strip("{}").strip('"')
                    if p and (os.path.isfile(p) or "\\" in p or "/" in p):
                        # verify exists if possible
                        if os.path.exists(p) or enc == "mbcs":
                            return p if os.path.exists(p) else p
                except Exception:
                    continue
            p = f.decode("utf-8", errors="ignore").replace("\x00", "")
            return p.strip().strip("{}").strip('"')
        p = str(f).replace("\x00", "").strip().strip("{}").strip('"')
        return p
    except Exception:
        return ""


class ChatLanPanel:
    def __init__(self, parent: tk.Misc, app) -> None:
        self.parent = parent
        self.app = app
        self.base_dir = getattr(app, "base_dir", ".")
        self.name = _device_name()
        self.color = "#7dd3fc"
        self._running = True
        self._peers: dict[str, float] = {}
        self._seen_ids: set[str] = set()
        self._pending: dict[str, dict] = {}  # id -> {path, name, kind, from}
        self.hist_path = os.path.join(self.base_dir, "chat_lan_history.json")
        self.recv_dir = os.path.join(self.base_dir, "chat_received")
        self.pending_dir = os.path.join(self.recv_dir, "_pending")
        os.makedirs(self.pending_dir, exist_ok=True)
        os.makedirs(self.recv_dir, exist_ok=True)

        self.frame = tk.Frame(parent, bg=BG)
        self.frame.pack(fill=tk.BOTH, expand=True)
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(1, weight=1)
        self._build()
        self._setup_drop()
        self._start_net()
        self._load_hist_ui()

    def _build(self) -> None:
        top = tk.Frame(self.frame, bg=CARD)
        top.grid(row=0, column=0, sticky="ew")
        tk.Label(top, text="💬 CHAT LAN", font=("Segoe UI", 9, "bold"), fg=ACCENT, bg=CARD).pack(
            side=tk.LEFT, padx=6, pady=3,
        )
        self.lbl_me = tk.Label(top, text=f"{self.name} · {_local_ip()}", font=("Segoe UI", 7), fg=MUTED, bg=CARD)
        self.lbl_me.pack(side=tk.LEFT, padx=4)
        self.lbl_peers = tk.Label(top, text="online: —", font=("Segoe UI", 7), fg=SUCCESS, bg=CARD)
        self.lbl_peers.pack(side=tk.LEFT, padx=6)
        tk.Label(top, text="⬇ kéo thả file/ảnh vào khung chat", font=("Segoe UI", 6), fg=MUTED, bg=CARD).pack(
            side=tk.LEFT, padx=6,
        )
        tk.Button(top, text="✎ Tên", font=("Segoe UI", 7), bg=BG, fg=TEXT, bd=0, padx=4,
                  command=self._rename, cursor="hand2").pack(side=tk.RIGHT, padx=2)
        self.btn_color = tk.Button(
            top, text="🎨 Màu", font=("Segoe UI", 7), bg=BG, fg=self.color, bd=0, padx=4,
            command=self._pick_color, cursor="hand2",
        )
        self.btn_color.pack(side=tk.RIGHT, padx=2)

        # drop zone + log
        mid = tk.Frame(self.frame, bg=BG)
        mid.grid(row=1, column=0, sticky="nsew")
        mid.columnconfigure(0, weight=1)
        mid.rowconfigure(0, weight=1)

        self.log = scrolledtext.ScrolledText(
            mid, height=12, bg="#07070a", fg=TEXT, font=("Segoe UI", 9),
            bd=0, state=tk.DISABLED, wrap=tk.WORD,
        )
        self.log.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        self.log.tag_config("meta", foreground=MUTED, font=("Segoe UI", 7))
        self.log.tag_config("sys", foreground="#a78bfa", font=("Segoe UI", 8, "italic"))

        # preview strip (trước khi gửi)
        self.preview_fr = tk.Frame(mid, bg=CARD)
        self.preview_fr.grid(row=1, column=0, sticky="ew", padx=2, pady=1)
        self.preview_fr.grid_remove()
        self._preview_lbl = tk.Label(self.preview_fr, text="", font=("Segoe UI", 8), fg=TEXT, bg=CARD, anchor="w")
        self._preview_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6, pady=4)
        self._preview_thumb = tk.Label(self.preview_fr, bg=CARD)
        self._preview_thumb.pack(side=tk.LEFT, padx=4)
        tk.Button(
            self.preview_fr, text="Gửi file ▶", font=("Segoe UI", 8, "bold"), bg=SUCCESS, fg="#000",
            bd=0, padx=8, command=self._confirm_send_preview, cursor="hand2",
        ).pack(side=tk.RIGHT, padx=2)
        tk.Button(
            self.preview_fr, text="Hủy", font=("Segoe UI", 7), bg=BG, fg=MUTED, bd=0, padx=6,
            command=self._cancel_preview, cursor="hand2",
        ).pack(side=tk.RIGHT)
        self._preview_path: str | None = None
        self._preview_photo = None

        bot = tk.Frame(self.frame, bg=BG)
        bot.grid(row=2, column=0, sticky="ew", padx=2, pady=2)
        bot.columnconfigure(0, weight=1)
        self.entry = tk.Entry(bot, font=("Segoe UI", 9), bg=CARD, fg=TEXT, insertbackground=TEXT, bd=0)
        self.entry.grid(row=0, column=0, sticky="ew", ipady=4, padx=(0, 4))
        self.entry.bind("<Return>", lambda _e: self._send_text())
        tk.Button(bot, text="Gửi", font=("Segoe UI", 8, "bold"), bg=ACCENT, fg="#000", bd=0, padx=10,
                  command=self._send_text, cursor="hand2").grid(row=0, column=1)
        tk.Button(bot, text="🖼", font=("Segoe UI", 8), bg=CARD, fg=SUCCESS, bd=0, padx=6,
                  command=self._pick_image, cursor="hand2").grid(row=0, column=2, padx=1)
        tk.Button(bot, text="📎", font=("Segoe UI", 8), bg=CARD, fg=GOLD, bd=0, padx=6,
                  command=self._pick_file, cursor="hand2").grid(row=0, column=3, padx=1)
        tk.Button(bot, text="📂", font=("Segoe UI", 8), bg=CARD, fg=MUTED, bd=0, padx=4,
                  command=self._open_recv, cursor="hand2").grid(row=0, column=4, padx=1)

    def _setup_drop(self) -> None:
        """Kéo thả file — an toàn thread (windnd callback không ở main thread)."""
        self._drop_hooked = False

        def on_drop(files):
            try:
                paths = []
                for f in (files or []):
                    p = _safe_drop_path(f)
                    if p and os.path.isfile(p):
                        paths.append(p)
                if not paths:
                    return
                path0 = paths[0]
                # luôn marshal về UI thread
                try:
                    self.frame.after(0, lambda p=path0: self._safe_queue_preview(p))
                except Exception:
                    pass
            except Exception:
                # không để exception thoát ra windnd (gây crash process)
                try:
                    self.frame.after(
                        0,
                        lambda: self._append("⚠ Lỗi đọc file kéo thả", color="#f44"),
                    )
                except Exception:
                    pass

        def try_hook():
            try:
                import windnd
                # chỉ hook frame (không hook ScrolledText — dễ crash)
                windnd.hook_dropfiles(self.frame, func=on_drop, force_unicode=True)
                self._drop_hooked = True
            except Exception:
                try:
                    self._append("⚠ Cài windnd: pip install windnd", color="#a78bfa")
                except Exception:
                    pass

        # delay hook sau khi widget map — tránh crash khởi tạo
        try:
            self.frame.after(200, try_hook)
        except Exception:
            try_hook()

    def _safe_queue_preview(self, path: str) -> None:
        try:
            self._queue_preview(path)
        except Exception as exc:
            try:
                self._append(f"⚠ Preview lỗi: {exc}", color="#f44")
            except Exception:
                pass

    def _queue_preview(self, path: str) -> None:
        """Hiển thị review trước khi gửi."""
        if not path or not os.path.isfile(path):
            return
        try:
            size = os.path.getsize(path)
        except OSError:
            self._append("⚠ Không đọc được file", color="#f44")
            return
        if size > MAX_FILE_B:
            try:
                messagebox.showwarning(
                    "Chat", f"File tối đa {MAX_FILE_B // 1_000_000}MB", parent=self.frame,
                )
            except Exception:
                pass
            return
        self._preview_path = path
        name = os.path.basename(path)
        ext = os.path.splitext(name)[1].lower()
        is_img = ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")
        try:
            self._preview_lbl.config(
                text=f"📎 Sẵn sàng gửi: {name}  ({max(1, size // 1024)} KB)"
                + (" · ảnh" if is_img else ""),
            )
        except tk.TclError:
            return
        self._preview_photo = None
        try:
            self._preview_thumb.config(image="", text="")
        except tk.TclError:
            pass
        if is_img:
            try:
                from PIL import Image, ImageTk
                with Image.open(path) as im0:
                    im = im0.convert("RGB")
                    im.thumbnail((64, 64))
                    self._preview_photo = ImageTk.PhotoImage(im)
                self._preview_thumb.config(image=self._preview_photo)
            except Exception:
                pass
        try:
            self.preview_fr.grid()
        except tk.TclError:
            pass

    def _cancel_preview(self) -> None:
        self._preview_path = None
        self._preview_photo = None
        self.preview_fr.grid_remove()

    def _confirm_send_preview(self) -> None:
        path = self._preview_path
        self._cancel_preview()
        if path:
            self._send_file_path(path)

    def _pick_image(self) -> None:
        path = filedialog.askopenfilename(
            title="Chọn ảnh", filetypes=[("Image", "*.png;*.jpg;*.jpeg;*.gif;*.bmp;*.webp")],
            parent=self.frame,
        )
        if path:
            self._queue_preview(path)

    def _pick_file(self) -> None:
        path = filedialog.askopenfilename(title="Chọn file", parent=self.frame)
        if path:
            self._queue_preview(path)

    def _start_net(self) -> None:
        threading.Thread(target=self._udp_beacon_loop, daemon=True).start()
        threading.Thread(target=self._udp_listen_loop, daemon=True).start()
        threading.Thread(target=self._tcp_server_loop, daemon=True).start()
        self.frame.after(2000, self._refresh_peers)

    def _udp_beacon_loop(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        while self._running:
            try:
                msg = json.dumps({
                    "type": "CHAT_HELLO", "name": self.name, "ip": _local_ip(), "ts": time.time(),
                }).encode()
                sock.sendto(msg, ("255.255.255.255", UDP_PORT))
            except Exception:
                pass
            time.sleep(2.0)
        sock.close()

    def _udp_listen_loop(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("", UDP_PORT))
        except OSError:
            return
        sock.settimeout(1.0)
        while self._running:
            try:
                data, addr = sock.recvfrom(65535)
                msg = json.loads(data.decode("utf-8", errors="ignore"))
                t = msg.get("type")
                if t == "CHAT_HELLO":
                    ip = msg.get("ip") or addr[0]
                    if ip != _local_ip():
                        self._peers[ip] = time.time()
                elif t == "CHAT_MSG":
                    mid = msg.get("id", "")
                    if mid and mid in self._seen_ids:
                        continue
                    if mid:
                        self._seen_ids.add(mid)
                        if len(self._seen_ids) > 400:
                            self._seen_ids = set(list(self._seen_ids)[-250:])
                    if msg.get("from_ip") == _local_ip() and msg.get("name") == self.name:
                        continue
                    self.frame.after(0, lambda m=msg: self._on_msg(m))
            except socket.timeout:
                continue
            except Exception:
                continue
        sock.close()

    def _tcp_server_loop(self) -> None:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            srv.bind(("", TCP_PORT))
            srv.listen(8)
            srv.settimeout(1.0)
        except OSError:
            return
        while self._running:
            try:
                conn, addr = srv.accept()
                threading.Thread(target=self._tcp_recv_file, args=(conn, addr), daemon=True).start()
            except socket.timeout:
                continue
            except Exception:
                if not self._running:
                    break
        try:
            srv.close()
        except Exception:
            pass

    def _tcp_recv_file(self, conn: socket.socket, addr) -> None:
        try:
            # protocol: first line JSON meta, then raw bytes length-prefixed or base64 line
            buf = b""
            conn.settimeout(60)
            while b"\n" not in buf:
                chunk = conn.recv(4096)
                if not chunk:
                    return
                buf += chunk
            header, rest = buf.split(b"\n", 1)
            meta = json.loads(header.decode())
            size = int(meta.get("size") or 0)
            if size <= 0 or size > MAX_FILE_B:
                return
            while len(rest) < size:
                chunk = conn.recv(min(65536, size - len(rest)))
                if not chunk:
                    break
                rest += chunk
            raw = rest[:size]
            fid = meta.get("fid") or uuid.uuid4().hex[:12]
            name = os.path.basename(meta.get("filename", "file.bin"))
            pending_path = os.path.join(self.pending_dir, f"{fid}_{name}")
            with open(pending_path, "wb") as f:
                f.write(raw)
            who = meta.get("name", addr[0])
            kind = meta.get("kind", "file")
            self._pending[fid] = {
                "path": pending_path, "name": name, "kind": kind,
                "from": who, "size": size,
            }
            self.frame.after(0, lambda: self._show_incoming_file(fid, who, name, kind, size, raw if kind == "image" else None))
        except Exception as exc:
            self.frame.after(0, lambda: self._append(f"Lỗi nhận file: {exc}", color="#f44"))
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _show_incoming_file(self, fid: str, who: str, name: str, kind: str, size: int, raw: bytes | None) -> None:
        """Review trước — bấm Download mới lưu & mở."""
        self.log.configure(state=tk.NORMAL)
        fr = tk.Frame(self.log, bg=CARD, padx=4, pady=4)
        head = f"📎 {who} gửi {kind}: {name} ({size // 1024} KB)"
        tk.Label(fr, text=head, font=("Segoe UI", 8), fg=GOLD, bg=CARD, anchor="w").pack(fill=tk.X)
        thumb_ref = {"p": None}
        if kind == "image" and raw:
            try:
                from PIL import Image, ImageTk
                import io
                im = Image.open(io.BytesIO(raw)).convert("RGB")
                im.thumbnail((120, 120))
                thumb_ref["p"] = ImageTk.PhotoImage(im)
                tk.Label(fr, image=thumb_ref["p"], bg=CARD).pack(anchor="w", pady=2)
            except Exception:
                pass
        tk.Label(fr, text="Chưa tải — bấm Download để lưu & mở", font=("Segoe UI", 7), fg=MUTED, bg=CARD).pack(anchor="w")
        tk.Button(
            fr, text="⬇ Download", font=("Segoe UI", 8, "bold"), bg=SUCCESS, fg="#000",
            bd=0, padx=8, pady=2, cursor="hand2",
            command=lambda: self._download_pending(fid, fr),
        ).pack(anchor="w", pady=2)
        self.log.window_create(tk.END, window=fr)
        self.log.insert(tk.END, "\n")
        # keep photo ref
        if not hasattr(self, "_thumb_refs"):
            self._thumb_refs = []
        if thumb_ref["p"]:
            self._thumb_refs.append(thumb_ref["p"])
            self._thumb_refs = self._thumb_refs[-30:]
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)
        self._save_hist_line(f"[pending] {who}: {name}")

    def _download_pending(self, fid: str, fr: tk.Frame) -> None:
        info = self._pending.get(fid)
        if not info:
            messagebox.showinfo("Chat", "File không còn / đã tải", parent=self.frame)
            return
        src = info["path"]
        name = info["name"]
        dest = os.path.join(self.recv_dir, f"{int(time.time())}_{name}")
        try:
            import shutil
            shutil.copy2(src, dest)
            try:
                os.remove(src)
            except OSError:
                pass
            del self._pending[fid]
            for w in fr.winfo_children():
                if isinstance(w, tk.Button):
                    w.config(text="✓ Đã tải", state=tk.DISABLED, bg=MUTED)
            self._append(f"✓ Đã tải: {name} → chat_received/", color=SUCCESS)
            try:
                os.startfile(dest)
            except OSError:
                os.startfile(self.recv_dir)
        except Exception as exc:
            messagebox.showerror("Chat", str(exc), parent=self.frame)

    def _broadcast_msg(self, payload: dict) -> None:
        payload["id"] = f"{time.time()}_{self.name}_{os.urandom(3).hex()}"
        payload["from_ip"] = _local_ip()
        payload["name"] = self.name
        payload["ts"] = datetime.now().strftime("%H:%M:%S")
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            sock.sendto(raw, ("255.255.255.255", UDP_PORT))
        except Exception:
            pass
        for ip in list(self._peers.keys()):
            try:
                sock.sendto(raw, (ip, UDP_PORT))
            except Exception:
                pass
        sock.close()
        self._seen_ids.add(payload["id"])

    def _send_text(self) -> None:
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, tk.END)
        self._broadcast_msg({"type": "CHAT_MSG", "kind": "text", "text": text, "color": self.color})
        self._append(f"[{datetime.now().strftime('%H:%M:%S')}] Bạn: {text}", color=self.color)
        self._save_hist_line(f"me: {text}")

    def _send_file_path(self, path: str) -> None:
        try:
            size = os.path.getsize(path)
            if size > MAX_FILE_B:
                messagebox.showwarning("Chat", f"File tối đa {MAX_FILE_B // 1_000_000}MB", parent=self.frame)
                return
            with open(path, "rb") as f:
                data = f.read()
            name = os.path.basename(path)
            ext = os.path.splitext(name)[1].lower()
            kind = "image" if ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp") else "file"
            fid = uuid.uuid4().hex[:12]
            meta = json.dumps({
                "filename": name, "name": self.name, "kind": kind,
                "size": size, "fid": fid,
            }, ensure_ascii=False).encode() + b"\n"
            payload = meta + data
            peers = list(self._peers.keys())
            if not peers:
                messagebox.showinfo("Chat", "Chưa thấy máy LAN online (đợi ~2s)", parent=self.frame)
            ok = 0
            for ip in peers:
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(15)
                    s.connect((ip, TCP_PORT))
                    s.sendall(payload)
                    s.close()
                    ok += 1
                except Exception:
                    pass
            self._broadcast_msg({
                "type": "CHAT_MSG", "kind": "file_notice",
                "text": f"đã gửi {kind} «{name}» ({size // 1024}KB) → {ok} máy (chờ download)",
                "color": GOLD,
            })
            self._append(f"Bạn gửi {kind}: {name} → {ok} máy (họ bấm Download)", color=GOLD)
            # local preview card
            self._append(f"✓ Đã gửi «{name}»", color=SUCCESS)
        except Exception as exc:
            messagebox.showerror("Chat", str(exc), parent=self.frame)

    def broadcast_work_status(self, order_id: str, product: str = "") -> None:
        """(11) Báo LAN: đang làm mã … — không spam cùng mã liên tục."""
        oid = (order_id or "").strip()
        if not oid or oid in ("—", "Unknown", "?"):
            return
        last = getattr(self, "_last_work_oid", None)
        last_ts = getattr(self, "_last_work_ts", 0.0)
        now = time.time()
        if last == oid and (now - last_ts) < 45:
            return
        self._last_work_oid = oid
        self._last_work_ts = now
        prod = (product or "").strip()
        text = f"đang làm mã {oid}"
        if prod and prod not in ("—", "?"):
            text += f" · {prod[:40]}"
        payload = {
            "type": "CHAT_MSG",
            "kind": "work_status",
            "text": text,
            "order_id": oid,
            "color": GOLD,
        }
        self._broadcast_msg(payload)
        self._append(f"[{datetime.now().strftime('%H:%M:%S')}] 🛠 Bạn: {text}", color=GOLD)
        self._save_hist_line(f"me work: {text}")

    def _on_msg(self, msg: dict) -> None:
        kind = msg.get("kind", "text")
        who = msg.get("name", "?")
        ts = msg.get("ts", "")
        color = msg.get("color") or "#ccc"
        text = msg.get("text", "")
        if kind == "work_status":
            line = f"[{ts}] 🛠 {who}: {text}"
            self._append(line, color=GOLD)
            self._save_hist_line(f"{who} work: {text}")
            # tag system style
            try:
                self.log.configure(state=tk.NORMAL)
                # last line already inserted — ok
                self.log.configure(state=tk.DISABLED)
            except tk.TclError:
                pass
        elif kind == "text":
            self._append(f"[{ts}] {who}: {text}", color=color)
            self._save_hist_line(f"{who}: {text}")
        else:
            self._append(f"[{ts}] {who}: {text}", color=color or GOLD)

    def _append(self, line: str, color: str = TEXT) -> None:
        tag = f"c_{abs(hash(color)) % 10**8}"
        self.log.configure(state=tk.NORMAL)
        try:
            self.log.tag_config(tag, foreground=color)
        except tk.TclError:
            pass
        self.log.insert(tk.END, line + "\n", tag)
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _save_hist_line(self, line: str) -> None:
        try:
            data = []
            if os.path.isfile(self.hist_path):
                with open(self.hist_path, encoding="utf-8") as f:
                    data = json.load(f)
            data.append({"ts": datetime.now().isoformat(timespec="seconds"), "line": line})
            with open(self.hist_path, "w", encoding="utf-8") as f:
                json.dump(data[-300:], f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_hist_ui(self) -> None:
        try:
            if not os.path.isfile(self.hist_path):
                return
            with open(self.hist_path, encoding="utf-8") as f:
                data = json.load(f)
            for item in data[-30:]:
                self._append(item.get("line", ""), color=MUTED)
        except Exception:
            pass

    def _refresh_peers(self) -> None:
        if not self._running:
            return
        now = time.time()
        self._peers = {ip: t for ip, t in self._peers.items() if now - t < 8}
        self.lbl_peers.config(text=f"online: {len(self._peers)}")
        self.frame.after(2000, self._refresh_peers)

    def _rename(self) -> None:
        n = simpledialog.askstring("Tên chat", "Tên hiển thị:", initialvalue=self.name, parent=self.frame)
        if n:
            self.name = n.strip()[:20]
            self.lbl_me.config(text=f"{self.name} · {_local_ip()}")

    def _pick_color(self) -> None:
        c = colorchooser.askcolor(color=self.color, title="Màu chữ chat", parent=self.frame)
        if c and c[1]:
            self.color = c[1]
            self.btn_color.config(fg=self.color)

    def _open_recv(self) -> None:
        try:
            os.startfile(self.recv_dir)
        except OSError:
            pass

    def destroy(self) -> None:
        self._running = False
