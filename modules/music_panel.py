"""Tab Nhạc — dán link YouTube, phát audio-only (không video/cửa sổ).

Backend: yt-dlp tải audio → phát headless (ffplay/mpv/pygame/MediaPlayer).
"""

from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import tkinter as tk
from tkinter import messagebox
from typing import Any
from urllib.parse import urlparse, parse_qs

BG, CARD, TEXT, MUTED = "#0c0c14", "#141424", "#e8e8f0", "#82829c"
ACCENT, SUCCESS, GOLD, DANGER = "#00d2ff", "#00e676", "#fbbf24", "#ff6b8a"
MUSIC = "#c084fc"

YT_RE = re.compile(
    r"(https?://)?(www\.)?(youtube\.com|youtu\.be|music\.youtube\.com)/[\w\-?=&%./]+",
    re.I,
)


def _which(name: str) -> str | None:
    return shutil.which(name)


def _extract_urls(text: str) -> list[str]:
    urls = []
    for m in YT_RE.finditer(text or ""):
        u = m.group(0)
        if not u.startswith("http"):
            u = "https://" + u
        urls.append(u.split()[0].rstrip(".,);\"'"))
    t = (text or "").strip()
    if t.startswith("http") and "youtu" in t.lower() and t not in urls:
        urls.insert(0, t.split()[0])
    out, seen = [], set()
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _video_id(url: str) -> str:
    try:
        p = urlparse(url)
        if "youtu.be" in (p.netloc or ""):
            return (p.path or "").strip("/").split("/")[0][:20]
        qs = parse_qs(p.query or "")
        if "v" in qs:
            return qs["v"][0][:20]
        parts = [x for x in (p.path or "").split("/") if x]
        if parts:
            return parts[-1][:20]
    except Exception:
        pass
    return str(abs(hash(url)) % 10**10)


class _PlayerBackend:
    """Phát file audio local, không hiện cửa sổ video."""

    def __init__(self) -> None:
        self._mode = "none"
        self._proc: subprocess.Popen | None = None
        self._ps: subprocess.Popen | None = None
        self._path: str | None = None
        self._volume = 0.7
        self._detect()

    def _detect(self) -> None:
        if _which("ffplay"):
            self._mode = "ffplay"
        elif _which("mpv"):
            self._mode = "mpv"
        else:
            try:
                import pygame  # noqa: F401
                self._mode = "pygame"
            except ImportError:
                self._mode = "wpf"  # PowerShell MediaPlayer

    @property
    def mode_label(self) -> str:
        return {
            "ffplay": "ffplay",
            "mpv": "mpv",
            "pygame": "pygame",
            "wpf": "MediaPlayer",
            "none": "—",
        }.get(self._mode, self._mode)

    def set_volume(self, vol: float) -> None:
        self._volume = max(0.0, min(1.0, float(vol)))
        if self._mode == "pygame":
            try:
                import pygame
                pygame.mixer.music.set_volume(self._volume)
            except Exception:
                pass
        elif self._mode == "wpf" and self._ps and self._ps.poll() is None:
            try:
                self._ps.stdin.write(f"vol {self._volume:.2f}\n")
                self._ps.stdin.flush()
            except Exception:
                pass

    def play(self, path: str) -> bool:
        self.stop()
        if not path or not os.path.isfile(path):
            return False
        self._path = path
        try:
            if self._mode == "ffplay":
                self._proc = subprocess.Popen(
                    [
                        "ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet",
                        "-volume", str(int(self._volume * 100)), path,
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                return True
            if self._mode == "mpv":
                self._proc = subprocess.Popen(
                    [
                        "mpv", "--no-video", "--really-quiet",
                        f"--volume={int(self._volume * 100)}", path,
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                return True
            if self._mode == "pygame":
                import pygame
                if not pygame.mixer.get_init():
                    pygame.mixer.init()
                pygame.mixer.music.load(path)
                pygame.mixer.music.set_volume(self._volume)
                pygame.mixer.music.play()
                return True
            # WPF MediaPlayer via long-lived PowerShell
            return self._wpf_play(path)
        except Exception:
            return False

    def _ensure_ps(self) -> bool:
        if self._ps and self._ps.poll() is None:
            return True
        script = r"""
Add-Type -AssemblyName presentationCore
$player = New-Object System.Windows.Media.MediaPlayer
$player.Volume = 0.7
while ($true) {
  $line = [Console]::In.ReadLine()
  if ($null -eq $line) { break }
  if ($line -eq 'quit') { break }
  if ($line.StartsWith('open ')) {
    $p = $line.Substring(5).Trim()
    try {
      $player.Stop()
      $player.Close()
      $player.Open([Uri]$p)
      Start-Sleep -Milliseconds 200
      $player.Play()
    } catch {}
  }
  elseif ($line -eq 'play') { try { $player.Play() } catch {} }
  elseif ($line -eq 'pause') { try { $player.Pause() } catch {} }
  elseif ($line -eq 'stop') { try { $player.Stop() } catch {} }
  elseif ($line.StartsWith('vol ')) {
    try { $player.Volume = [double]$line.Substring(4).Trim() } catch {}
  }
}
try { $player.Stop(); $player.Close() } catch {}
"""
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            self._ps = subprocess.Popen(
                [
                    "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-Command", script,
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=flags,
            )
            return True
        except Exception:
            self._ps = None
            return False

    def _wpf_play(self, path: str) -> bool:
        if not self._ensure_ps():
            return False
        try:
            # MediaPlayer wants file:/// URI
            uri = "file:///" + path.replace("\\", "/")
            self._ps.stdin.write(f"open {uri}\n")
            self._ps.stdin.write(f"vol {self._volume:.2f}\n")
            self._ps.stdin.flush()
            return True
        except Exception:
            return False

    def pause(self) -> None:
        if self._mode == "pygame":
            try:
                import pygame
                pygame.mixer.music.pause()
            except Exception:
                pass
        elif self._mode == "wpf" and self._ps and self._ps.poll() is None:
            try:
                self._ps.stdin.write("pause\n")
                self._ps.stdin.flush()
            except Exception:
                pass
        else:
            # ffplay/mpv: stop (no easy pause without IPC)
            self.stop()

    def resume(self) -> None:
        if self._mode == "pygame":
            try:
                import pygame
                pygame.mixer.music.unpause()
            except Exception:
                pass
        elif self._mode == "wpf" and self._ps and self._ps.poll() is None:
            try:
                self._ps.stdin.write("play\n")
                self._ps.stdin.flush()
            except Exception:
                pass
        elif self._path:
            self.play(self._path)

    def stop(self) -> None:
        if self._mode == "pygame":
            try:
                import pygame
                if pygame.mixer.get_init():
                    pygame.mixer.music.stop()
            except Exception:
                pass
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass
            try:
                self._proc.kill()
            except Exception:
                pass
        self._proc = None
        if self._mode == "wpf" and self._ps and self._ps.poll() is None:
            try:
                self._ps.stdin.write("stop\n")
                self._ps.stdin.flush()
            except Exception:
                pass

    def is_playing(self) -> bool:
        if self._mode == "pygame":
            try:
                import pygame
                return bool(pygame.mixer.get_init() and pygame.mixer.music.get_busy())
            except Exception:
                return False
        if self._proc and self._proc.poll() is None:
            return True
        # WPF: assume playing if path set (no easy poll without more IPC)
        if self._mode == "wpf" and self._ps and self._ps.poll() is None and self._path:
            return True
        return False

    def shutdown(self) -> None:
        self.stop()
        if self._ps and self._ps.poll() is None:
            try:
                self._ps.stdin.write("quit\n")
                self._ps.stdin.flush()
            except Exception:
                pass
            try:
                self._ps.terminate()
            except Exception:
                pass
        self._ps = None


class MusicPanel:
    def __init__(self, parent: tk.Misc, app) -> None:
        self.parent = parent
        self.app = app
        self.base_dir = getattr(app, "base_dir", ".")
        self.cache_dir = os.path.join(self.base_dir, "music_cache")
        self.playlist_path = os.path.join(self.base_dir, "music_playlist.json")
        os.makedirs(self.cache_dir, exist_ok=True)

        self.playlist: list[dict[str, Any]] = []  # {url, title, id, path, status}
        self.idx = -1
        self._state = "stopped"  # stopped | playing | paused | loading
        self._loop = True
        self._auto_next = True
        self._backend = _PlayerBackend()
        self._jobs: queue.Queue = queue.Queue()
        self._running = True
        self._last_status = ""
        self._download_lock = threading.Lock()
        self._play_started_at = 0.0
        self._play_duration = 0.0  # giây — auto-next khi WPF

        self.frame = tk.Frame(parent, bg=BG)
        self.frame.pack(fill=tk.BOTH, expand=True)
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(2, weight=1)
        self._build()
        self._load_playlist()
        threading.Thread(target=self._worker, daemon=True).start()
        self.frame.after(800, self._tick)

    def _build(self) -> None:
        # Header
        top = tk.Frame(self.frame, bg=CARD)
        top.grid(row=0, column=0, sticky="ew")
        tk.Label(
            top, text="🎵 NHẠC YOUTUBE", font=("Segoe UI", 9, "bold"),
            fg=MUSIC, bg=CARD,
        ).pack(side=tk.LEFT, padx=6, pady=3)
        self.lbl_engine = tk.Label(
            top, text=f"engine: {self._backend.mode_label}",
            font=("Segoe UI", 6), fg=MUTED, bg=CARD,
        )
        self.lbl_engine.pack(side=tk.LEFT, padx=4)
        tk.Label(
            top, text="chỉ audio · không video", font=("Segoe UI", 6),
            fg=MUTED, bg=CARD,
        ).pack(side=tk.LEFT, padx=4)
        tk.Button(
            top, text="📂 Cache", font=("Segoe UI", 7), bg=BG, fg=MUTED, bd=0, padx=4,
            command=self._open_cache, cursor="hand2",
        ).pack(side=tk.RIGHT, padx=2)
        tk.Button(
            top, text="🗑 Cache", font=("Segoe UI", 7), bg=BG, fg=DANGER, bd=0, padx=4,
            command=self._clear_cache, cursor="hand2",
        ).pack(side=tk.RIGHT, padx=2)

        # URL row
        url_row = tk.Frame(self.frame, bg=BG)
        url_row.grid(row=1, column=0, sticky="ew", padx=4, pady=3)
        url_row.columnconfigure(0, weight=1)
        self.url_var = tk.StringVar()
        self.url_entry = tk.Entry(
            url_row, textvariable=self.url_var, font=("Segoe UI", 9),
            bg=CARD, fg=TEXT, insertbackground=TEXT, bd=0,
        )
        self.url_entry.grid(row=0, column=0, sticky="ew", ipady=4, padx=(0, 4))
        self.url_entry.bind("<Return>", lambda _e: self._add_url())
        self.url_entry.bind("<Control-v>", lambda _e: self.frame.after(10, self._maybe_auto_add))
        tk.Button(
            url_row, text="➕ Thêm", font=("Segoe UI", 8, "bold"), bg=MUSIC, fg="#000",
            bd=0, padx=8, command=self._add_url, cursor="hand2",
        ).grid(row=0, column=1, padx=1)
        tk.Button(
            url_row, text="📋 Dán", font=("Segoe UI", 8), bg=CARD, fg=ACCENT,
            bd=0, padx=6, command=self._paste_add, cursor="hand2",
        ).grid(row=0, column=2, padx=1)
        tk.Button(
            url_row, text="▶ Phát ngay", font=("Segoe UI", 8, "bold"), bg=SUCCESS, fg="#000",
            bd=0, padx=8, command=self._paste_and_play, cursor="hand2",
        ).grid(row=0, column=3, padx=1)

        # Body: now playing + playlist
        body = tk.Frame(self.frame, bg=BG)
        body.grid(row=2, column=0, sticky="nsew", padx=4, pady=2)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)

        now = tk.Frame(body, bg=CARD)
        now.grid(row=0, column=0, sticky="ew", pady=(0, 3))
        tk.Label(now, text="Đang phát", font=("Segoe UI", 7), fg=MUTED, bg=CARD).pack(
            side=tk.LEFT, padx=6, pady=2,
        )
        self.now_var = tk.StringVar(value="— chưa có bài —")
        tk.Label(
            now, textvariable=self.now_var, font=("Segoe UI", 9, "bold"),
            fg=GOLD, bg=CARD, anchor="w",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        self.status_var = tk.StringVar(value="⏹ Dừng")
        tk.Label(
            now, textvariable=self.status_var, font=("Segoe UI", 7),
            fg=ACCENT, bg=CARD,
        ).pack(side=tk.RIGHT, padx=6)

        # Playlist
        pl_fr = tk.Frame(body, bg=BG)
        pl_fr.grid(row=1, column=0, sticky="nsew")
        pl_fr.columnconfigure(0, weight=1)
        pl_fr.rowconfigure(0, weight=1)
        self.listbox = tk.Listbox(
            pl_fr, bg="#07070a", fg=TEXT, font=("Segoe UI", 8),
            selectbackground="#3b2a5a", selectforeground=GOLD,
            activestyle="none", bd=0, highlightthickness=0,
            exportselection=False,
        )
        self.listbox.grid(row=0, column=0, sticky="nsew")
        sb = tk.Scrollbar(pl_fr, command=self.listbox.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.listbox.config(yscrollcommand=sb.set)
        self.listbox.bind("<Double-Button-1>", lambda _e: self._play_selected())
        self.listbox.bind("<Delete>", lambda _e: self._remove_selected())

        # Controls
        ctrl = tk.Frame(self.frame, bg=CARD)
        ctrl.grid(row=3, column=0, sticky="ew", padx=0, pady=2)
        for text, cmd, fg in (
            ("⏮", self.prev, MUTED),
            ("⏯", self.toggle_play, SUCCESS),
            ("⏹", self.stop, DANGER),
            ("⏭", self.next, MUTED),
        ):
            tk.Button(
                ctrl, text=text, font=("Segoe UI", 11, "bold"), bg=BG, fg=fg,
                bd=0, padx=10, pady=2, command=cmd, cursor="hand2",
            ).pack(side=tk.LEFT, padx=2, pady=3)

        self.loop_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            ctrl, text="Lặp DS", variable=self.loop_var, font=("Segoe UI", 7),
            fg=TEXT, bg=CARD, selectcolor=BG, activebackground=CARD,
            command=lambda: setattr(self, "_loop", self.loop_var.get()),
        ).pack(side=tk.LEFT, padx=6)

        tk.Label(ctrl, text="Vol", font=("Segoe UI", 7), fg=MUTED, bg=CARD).pack(side=tk.LEFT)
        self.vol_var = tk.DoubleVar(value=70)
        tk.Scale(
            ctrl, from_=0, to=100, orient=tk.HORIZONTAL, variable=self.vol_var,
            showvalue=0, length=90, bg=CARD, troughcolor=BG, highlightthickness=0,
            bd=0, command=self._on_vol,
        ).pack(side=tk.LEFT, padx=2)

        tk.Button(
            ctrl, text="Xóa bài", font=("Segoe UI", 7), bg=BG, fg=MUTED, bd=0, padx=6,
            command=self._remove_selected, cursor="hand2",
        ).pack(side=tk.RIGHT, padx=4)
        tk.Button(
            ctrl, text="Xóa hết", font=("Segoe UI", 7), bg=BG, fg=DANGER, bd=0, padx=6,
            command=self._clear_playlist, cursor="hand2",
        ).pack(side=tk.RIGHT, padx=2)

        # Tips
        tip = tk.Frame(self.frame, bg=BG)
        tip.grid(row=4, column=0, sticky="ew", padx=4, pady=(0, 2))
        tk.Label(
            tip,
            text="💡 Dán link YouTube → Thêm / Phát ngay · Double-click bài · Delete xóa · vừa làm vừa nghe",
            font=("Segoe UI", 6), fg=MUTED, bg=BG, anchor="w",
        ).pack(fill=tk.X)

    # ── Playlist IO ─────────────────────────────────────────────────────────

    def _load_playlist(self) -> None:
        try:
            if os.path.isfile(self.playlist_path):
                with open(self.playlist_path, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    self.playlist = [
                        {
                            "url": x.get("url", ""),
                            "title": x.get("title") or x.get("url", "?"),
                            "id": x.get("id") or _video_id(x.get("url", "")),
                            "path": x.get("path"),
                            "status": "ready" if x.get("path") and os.path.isfile(x.get("path", "")) else "queued",
                        }
                        for x in data if x.get("url")
                    ]
        except Exception:
            self.playlist = []
        self._refresh_list()

    def _save_playlist(self) -> None:
        try:
            slim = [
                {"url": x["url"], "title": x.get("title"), "id": x.get("id"), "path": x.get("path")}
                for x in self.playlist
            ]
            with open(self.playlist_path, "w", encoding="utf-8") as f:
                json.dump(slim, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _refresh_list(self) -> None:
        self.listbox.delete(0, tk.END)
        for i, item in enumerate(self.playlist):
            mark = "▶ " if i == self.idx and self._state in ("playing", "loading", "paused") else "  "
            st = item.get("status", "")
            badge = {"loading": "⏳", "ready": "✓", "error": "✗", "queued": "·"}.get(st, "·")
            title = (item.get("title") or item.get("url") or "?")[:70]
            self.listbox.insert(tk.END, f"{mark}{badge} {title}")
        if 0 <= self.idx < len(self.playlist):
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(self.idx)
            self.listbox.see(self.idx)

    # ── Add / paste ─────────────────────────────────────────────────────────

    def _paste_add(self) -> None:
        try:
            clip = self.frame.clipboard_get()
        except tk.TclError:
            clip = ""
        if clip:
            self.url_var.set(clip.strip())
        self._add_url()

    def _paste_and_play(self) -> None:
        try:
            clip = self.frame.clipboard_get()
        except tk.TclError:
            clip = ""
        text = (clip or self.url_var.get() or "").strip()
        if text:
            self.url_var.set(text)
        n_before = len(self.playlist)
        self._add_url(play=True)
        if len(self.playlist) > n_before:
            self.idx = n_before
            self._play_index(self.idx)

    def _maybe_auto_add(self) -> None:
        pass  # user presses Thêm; keep paste free

    def _add_url(self, play: bool = False) -> None:
        text = self.url_var.get().strip()
        urls = _extract_urls(text)
        if not urls and text.startswith("http"):
            urls = [text.split()[0]]
        if not urls:
            messagebox.showinfo("Nhạc", "Dán link YouTube (youtube.com / youtu.be)", parent=self.frame)
            return
        added = 0
        first_new = None
        for url in urls:
            if any(x.get("url") == url for x in self.playlist):
                continue
            item = {
                "url": url,
                "title": f"YouTube {_video_id(url)}…",
                "id": _video_id(url),
                "path": None,
                "status": "queued",
            }
            # reuse cache if exists
            cached = self._find_cached(item["id"])
            if cached:
                item["path"] = cached
                item["status"] = "ready"
                item["title"] = os.path.splitext(os.path.basename(cached))[0]
            self.playlist.append(item)
            if first_new is None:
                first_new = len(self.playlist) - 1
            added += 1
            self._jobs.put(("fetch_meta", len(self.playlist) - 1))
        self.url_var.set("")
        self._refresh_list()
        self._save_playlist()
        if added and hasattr(self.app, "log"):
            self.app.log(f"🎵 Thêm {added} bài vào playlist", "accent")
        if play and first_new is not None:
            self.idx = first_new
            self._play_index(self.idx)

    def _find_cached(self, vid: str) -> str | None:
        if not vid:
            return None
        try:
            for name in os.listdir(self.cache_dir):
                if name.startswith(vid) or vid in name:
                    path = os.path.join(self.cache_dir, name)
                    if os.path.isfile(path) and os.path.getsize(path) > 1000:
                        return path
        except OSError:
            pass
        return None

    # ── Playback ────────────────────────────────────────────────────────────

    def _on_vol(self, _v=None) -> None:
        self._backend.set_volume(self.vol_var.get() / 100.0)

    def toggle_play(self) -> None:
        if self._state == "playing":
            self._backend.pause()
            self._state = "paused"
            self.status_var.set("⏸ Tạm dừng")
        elif self._state == "paused":
            self._backend.resume()
            self._state = "playing"
            self.status_var.set("▶ Đang phát")
        else:
            if self.idx < 0 and self.playlist:
                self.idx = 0
            if self.idx >= 0:
                self._play_index(self.idx)
            elif not self.playlist:
                self._paste_and_play()

    def stop(self) -> None:
        self._backend.stop()
        self._state = "stopped"
        self.status_var.set("⏹ Dừng")
        self._refresh_list()

    def next(self) -> None:
        if not self.playlist:
            return
        if self.idx < 0:
            self.idx = 0
        else:
            self.idx = (self.idx + 1) % len(self.playlist)
            if self.idx == 0 and not self._loop:
                self.stop()
                self.now_var.set("— hết playlist —")
                return
        self._play_index(self.idx)

    def prev(self) -> None:
        if not self.playlist:
            return
        if self.idx <= 0:
            self.idx = len(self.playlist) - 1 if self._loop else 0
        else:
            self.idx -= 1
        self._play_index(self.idx)

    def _play_selected(self) -> None:
        sel = self.listbox.curselection()
        if not sel:
            return
        self._play_index(int(sel[0]))

    def _play_index(self, i: int) -> None:
        if i < 0 or i >= len(self.playlist):
            return
        self.idx = i
        item = self.playlist[i]
        self.now_var.set(item.get("title") or item.get("url") or "…")
        self._state = "loading"
        self.status_var.set("⏳ Tải audio…")
        self._refresh_list()
        self._jobs.put(("play", i))

    def _do_play(self, i: int) -> None:
        if i < 0 or i >= len(self.playlist):
            return
        item = self.playlist[i]
        path = item.get("path")
        if not path or not os.path.isfile(path):
            path = self._download(item)
            item["path"] = path
        if not path:
            item["status"] = "error"
            self.frame.after(0, lambda: self._on_play_fail(i, "Không tải được audio"))
            return
        item["status"] = "ready"
        self._backend.set_volume(self.vol_var.get() / 100.0)
        ok = self._backend.play(path)
        dur = float(item.get("duration") or 0)
        def ui():
            if not ok:
                self._on_play_fail(i, "Không phát được (cài ffplay/mpv/pygame?)")
                return
            self._state = "playing"
            self.status_var.set("▶ Đang phát")
            self.now_var.set(item.get("title") or "…")
            self._play_started_at = time.monotonic()
            self._play_duration = dur
            self._refresh_list()
            self._save_playlist()
            if hasattr(self.app, "log"):
                self.app.log(f"🎵 {item.get('title', '')[:50]}", "accent")
            if hasattr(self.app, "set_music_status"):
                self.app.set_music_status(item.get("title", "")[:40])
        self.frame.after(0, ui)

    def _on_play_fail(self, i: int, msg: str) -> None:
        self._state = "stopped"
        self.status_var.set("✗ Lỗi")
        self.now_var.set(msg)
        self._refresh_list()
        if hasattr(self.app, "log"):
            self.app.log(f"🎵 {msg}", "danger")

    def _download(self, item: dict) -> str | None:
        with self._download_lock:
            vid = item.get("id") or _video_id(item["url"])
            cached = self._find_cached(vid)
            if cached:
                return cached
            item["status"] = "loading"
            self.frame.after(0, self._refresh_list)
            outtmpl = os.path.join(self.cache_dir, f"{vid}.%(ext)s")
            try:
                import yt_dlp
            except ImportError:
                self.frame.after(0, lambda: messagebox.showerror(
                    "Nhạc", "Cần cài yt-dlp:\npip install yt-dlp", parent=self.frame,
                ))
                return None
            opts = {
                "format": "bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio/best",
                "outtmpl": outtmpl,
                "quiet": True,
                "no_warnings": True,
                "noprogress": True,
                "noplaylist": True,
                "extract_flat": False,
            }
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(item["url"], download=True)
                    if info:
                        title = info.get("title") or item.get("title")
                        item["title"] = title
                        if info.get("duration"):
                            item["duration"] = float(info["duration"])
                        # probe cache
                        path = self._find_cached(vid)
                        if not path and info.get("id"):
                            path = self._find_cached(info["id"])
                        if not path:
                            # prepared filename
                            try:
                                path = ydl.prepare_filename(info)
                                if path and not os.path.isfile(path):
                                    base, _ = os.path.splitext(path)
                                    for ext in (".m4a", ".webm", ".mp3", ".opus", ".ogg"):
                                        if os.path.isfile(base + ext):
                                            path = base + ext
                                            break
                            except Exception:
                                path = None
                        return path if path and os.path.isfile(path) else None
            except Exception as exc:
                item["status"] = "error"
                self.frame.after(0, lambda: self.app.log(f"🎵 yt-dlp: {exc}", "danger") if hasattr(self.app, "log") else None)
                return None
        return None

    def _worker(self) -> None:
        while self._running:
            try:
                job = self._jobs.get(timeout=0.5)
            except queue.Empty:
                continue
            kind = job[0]
            try:
                if kind == "play":
                    self._do_play(job[1])
                elif kind == "fetch_meta":
                    self._fetch_meta(job[1])
            except Exception:
                pass

    def _fetch_meta(self, i: int) -> None:
        if i < 0 or i >= len(self.playlist):
            return
        item = self.playlist[i]
        if item.get("path") and os.path.isfile(item["path"]):
            return
        try:
            import yt_dlp
            opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(item["url"], download=False)
                if info:
                    item["title"] = info.get("title") or item["title"]
                    item["id"] = info.get("id") or item["id"]
                    if info.get("duration"):
                        item["duration"] = float(info["duration"])
                    self.frame.after(0, self._refresh_list)
                    self._save_playlist()
        except Exception:
            pass

    def _tick(self) -> None:
        if not self._running:
            return
        if self._state == "playing":
            ended = False
            mode = self._backend.mode_label
            if mode in ("ffplay", "mpv", "pygame"):
                if not self._backend.is_playing():
                    ended = True
            elif mode == "MediaPlayer" and self._play_duration > 5:
                # WPF: ước lượng hết bài theo duration
                if time.monotonic() - self._play_started_at >= self._play_duration + 1.5:
                    ended = True
            if ended:
                if self._auto_next and self.playlist:
                    self.next()
                else:
                    self._state = "stopped"
                    self.status_var.set("⏹ Xong")
                    if hasattr(self.app, "set_music_status"):
                        self.app.set_music_status("")
        self.frame.after(1200, self._tick)

    def _remove_selected(self) -> None:
        sel = list(self.listbox.curselection())
        if not sel:
            return
        for i in sorted(sel, reverse=True):
            if 0 <= i < len(self.playlist):
                if i == self.idx:
                    self.stop()
                del self.playlist[i]
                if self.idx >= len(self.playlist):
                    self.idx = len(self.playlist) - 1
                elif i < self.idx:
                    self.idx -= 1
        self._refresh_list()
        self._save_playlist()

    def _clear_playlist(self) -> None:
        self.stop()
        self.playlist.clear()
        self.idx = -1
        self.now_var.set("— chưa có bài —")
        self._refresh_list()
        self._save_playlist()

    def _open_cache(self) -> None:
        try:
            os.startfile(self.cache_dir)
        except OSError:
            pass

    def _clear_cache(self) -> None:
        if not messagebox.askyesno("Cache nhạc", "Xóa file audio đã tải?", parent=self.frame):
            return
        self.stop()
        n = 0
        try:
            for name in os.listdir(self.cache_dir):
                p = os.path.join(self.cache_dir, name)
                if os.path.isfile(p):
                    try:
                        os.remove(p)
                        n += 1
                    except OSError:
                        pass
        except OSError:
            pass
        for item in self.playlist:
            item["path"] = None
            item["status"] = "queued"
        self._save_playlist()
        self._refresh_list()
        if hasattr(self.app, "log"):
            self.app.log(f"🎵 Đã xóa {n} file cache", "accent")

    def destroy(self) -> None:
        self._running = False
        try:
            self._backend.shutdown()
        except Exception:
            pass
        self._save_playlist()
