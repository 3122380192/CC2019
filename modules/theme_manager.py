"""Theme manager — nhiều theme (hero/anime/game) + hiệu ứng nền động."""

from __future__ import annotations

import json
import math
import os
import random
import time
import tkinter as tk
from typing import Callable


def _T(
    name, bg, card, text, muted, accent, success, danger, emb, csv,
    console_bg, console_fg, table_bg, table_sel, hover, effect, particle,
    *, category="classic",
):
    return {
        "name": name, "bg": bg, "card": card, "text": text, "muted": muted,
        "accent": accent, "success": success, "danger": danger, "emb": emb,
        "csv": csv, "console_bg": console_bg, "console_fg": console_fg,
        "table_bg": table_bg, "table_sel": table_sel, "hover": hover,
        "effect": effect, "particle": particle, "category": category,
    }


# ── Theme palettes ──────────────────────────────────────────────────────────

THEMES: dict[str, dict] = {
    # ── Classic ──
    "midnight": _T(
        "Midnight", "#0c0c14", "#141424", "#ffffff", "#82829c",
        "#00d2ff", "#00e676", "#ff1744", "#ff003c", "#a78bfa",
        "#07070a", "#a9b7c6", "#0a0a12", "#1a3a2a", "#23233c",
        "particles", "#00d2ff", category="classic",
    ),
    "neon_cyan": _T(
        "Neon Cyan", "#050d12", "#0a1a22", "#e8ffff", "#5a9aaa",
        "#00fff0", "#39ff14", "#ff2a6d", "#ff2a6d", "#7b61ff",
        "#030a0e", "#7ec8d4", "#061018", "#0a3040", "#123040",
        "grid", "#00fff0", category="classic",
    ),
    "ember": _T(
        "Ember", "#120808", "#1e1010", "#fff5f0", "#a08070",
        "#ff6b35", "#ffd166", "#ef476f", "#ff3c00", "#e0aaff",
        "#0a0505", "#d4a090", "#100808", "#3a2010", "#2a1818",
        "embers", "#ff6b35", category="classic",
    ),
    "forest": _T(
        "Forest", "#08120c", "#0e1c14", "#e8fff0", "#6a9a7a",
        "#3dd68c", "#5efc8d", "#ff5c5c", "#ff6b6b", "#9b8cff",
        "#050a08", "#90c8a8", "#06100a", "#143828", "#183020",
        "aurora", "#3dd68c", category="classic",
    ),
    "lavender": _T(
        "Lavender", "#100e18", "#1a1628", "#f0e8ff", "#9080b0",
        "#c77dff", "#80ffdb", "#ff6b9d", "#ff5d8f", "#b8a0ff",
        "#0a0810", "#c0b0e0", "#0e0c16", "#2a2040", "#282040",
        "orbs", "#c77dff", category="classic",
    ),
    "ocean": _T(
        "Ocean", "#060e18", "#0c1828", "#e0f0ff", "#6080a0",
        "#4cc9f0", "#57cc99", "#f72585", "#f72585", "#7209b7",
        "#040a12", "#90b8d0", "#081220", "#103048", "#183040",
        "waves", "#4cc9f0", category="classic",
    ),
    "mono": _T(
        "Mono", "#0e0e0e", "#1a1a1a", "#f0f0f0", "#888888",
        "#ffffff", "#cccccc", "#ff4444", "#ff4444", "#aaaaaa",
        "#080808", "#bbbbbb", "#101010", "#2a2a2a", "#2a2a2a",
        "scanlines", "#ffffff", category="classic",
    ),
    "sunset": _T(
        "Sunset", "#140c10", "#221018", "#fff0f5", "#a08090",
        "#ff8fab", "#ffb703", "#e63946", "#fb5607", "#c77dff",
        "#0c080a", "#d0a0b0", "#120a0e", "#3a1828", "#301820",
        "embers", "#ff8fab", category="classic",
    ),
    # ── Superhero ──
    "ironman": _T(
        "Iron Man", "#0a0604", "#1a1008", "#fff4e8", "#b09070",
        "#ff6a00", "#ffd700", "#c41e3a", "#e63900", "#ffaa33",
        "#080402", "#e0b080", "#120a04", "#3a2008", "#2a1808",
        "embers", "#ff6a00", category="hero",
    ),
    "batman": _T(
        "Batman", "#080808", "#12120a", "#f5f0c8", "#8a8860",
        "#f0d060", "#c0b050", "#888888", "#d4af37", "#a0a080",
        "#050505", "#c0b880", "#0c0c08", "#2a2810", "#1e1e14",
        "scanlines", "#f0d060", category="hero",
    ),
    "superman": _T(
        "Superman", "#060a18", "#0c1430", "#e8f0ff", "#7090c0",
        "#3a7bfd", "#e8e8e8", "#d90429", "#c1121f", "#ffd60a",
        "#040810", "#90b0e0", "#081020", "#142850", "#182848",
        "particles", "#3a7bfd", category="hero",
    ),
    "spiderman": _T(
        "Spider-Man", "#120408", "#220810", "#ffe8ec", "#c07080",
        "#e63946", "#ffffff", "#1d3557", "#e63946", "#457b9d",
        "#0a0204", "#e0a0a8", "#140608", "#3a1018", "#2a0c14",
        "particles", "#e63946", category="hero",
    ),
    "hulk": _T(
        "Hulk", "#040c04", "#0a180a", "#e0ffe0", "#60a060",
        "#5cdb5c", "#b8f0b8", "#8b0000", "#4caf50", "#a5d6a7",
        "#020802", "#80c080", "#061006", "#143014", "#102810",
        "aurora", "#5cdb5c", category="hero",
    ),
    "wonder": _T(
        "Wonder Woman", "#100808", "#1c1010", "#fff0e8", "#c09070",
        "#c9a227", "#f4e4bc", "#9b1b30", "#b22222", "#d4af37",
        "#0a0404", "#d0b090", "#120808", "#3a2010", "#281818",
        "orbs", "#c9a227", category="hero",
    ),
    "blackpanther": _T(
        "Black Panther", "#08060e", "#14101c", "#e8e0ff", "#8070a0",
        "#9b5de5", "#c77dff", "#f15bb5", "#7b2cbf", "#00bbf9",
        "#06040a", "#b0a0d0", "#0c0a12", "#241838", "#1c1428",
        "orbs", "#9b5de5", category="hero",
    ),
    # ── Anime ──
    "anime_sakura": _T(
        "Anime Sakura", "#140c12", "#22141c", "#fff0f5", "#c090a8",
        "#ff8fab", "#ffc2d1", "#e85d75", "#ff5d8f", "#c77dff",
        "#0c080a", "#e0b0c0", "#120a0e", "#3a1828", "#2a1420",
        "orbs", "#ff8fab", category="anime",
    ),
    "anime_neon": _T(
        "Anime Neon", "#0a0612", "#140c22", "#f0e8ff", "#9070c0",
        "#ff00aa", "#00f5d4", "#7b2cbf", "#ff006e", "#8338ec",
        "#06040c", "#c0a0e0", "#0c0818", "#281848", "#1c1030",
        "grid", "#ff00aa", category="anime",
    ),
    "naruto": _T(
        "Naruto", "#100c06", "#1c160a", "#fff8e8", "#b0a070",
        "#ff6b00", "#ffd60a", "#c1121f", "#e85d04", "#48cae4",
        "#0a0804", "#e0c890", "#14100a", "#3a2808", "#282010",
        "embers", "#ff6b00", category="anime",
    ),
    "onepiece": _T(
        "One Piece", "#061018", "#0c1c28", "#e8f8ff", "#70a0b0",
        "#00b4d8", "#90e0ef", "#ef476f", "#0077b6", "#ffd60a",
        "#040c12", "#90c0d0", "#081420", "#103040", "#142830",
        "waves", "#00b4d8", category="anime",
    ),
    "demon_slayer": _T(
        "Demon Slayer", "#0c0610", "#180c1c", "#f8e8ff", "#a080b0",
        "#e0aaff", "#ff6b6b", "#7b2cbf", "#c77dff", "#ff9e00",
        "#08040c", "#d0b0e0", "#100818", "#2a1438", "#201028",
        "orbs", "#e0aaff", category="anime",
    ),
    "ghibli": _T(
        "Ghibli", "#0a120e", "#122018", "#e8fff0", "#80a890",
        "#52b788", "#95d5b2", "#d4a373", "#40916c", "#74c69d",
        "#06100c", "#a0c8b0", "#0a1610", "#183828", "#142820",
        "aurora", "#52b788", category="anime",
    ),
    "cyberpunk": _T(
        "Cyberpunk 2077", "#0a0408", "#160810", "#ffe8f0", "#b07090",
        "#fcee0a", "#00f0ff", "#ff003c", "#ff2a6d", "#d600ff",
        "#060204", "#e0a0b8", "#100408", "#301018", "#200c14",
        "grid", "#fcee0a", category="anime",
    ),
    # ── Game ──
    "lol": _T(
        "Liên Minh (LoL)", "#060810", "#0e1420", "#e0e8f8", "#7080a0",
        "#c89b3c", "#0ac8b9", "#0bc6e3", "#c8aa6e", "#0397ab",
        "#04060c", "#a0b0c8", "#0a0e18", "#1c2838", "#141c28",
        "particles", "#c89b3c", category="game",
    ),
    "valorant": _T(
        "Valorant", "#0c0808", "#1a1010", "#ffe8e8", "#b08080",
        "#ff4655", "#ece8e1", "#0f1923", "#ff4655", "#7a7a7a",
        "#080404", "#d0a0a0", "#100808", "#301418", "#241010",
        "scanlines", "#ff4655", category="game",
    ),
    "genshin": _T(
        "Genshin", "#081018", "#101c2c", "#e8f4ff", "#80a0c0",
        "#4cc9f0", "#f9c74f", "#f72585", "#4361ee", "#b5179e",
        "#040c14", "#a0c0e0", "#0a1420", "#142848", "#182430",
        "orbs", "#4cc9f0", category="game",
    ),
    "minecraft": _T(
        "Minecraft", "#0a1408", "#142010", "#e8ffe0", "#80a070",
        "#5b8c3e", "#8bc34a", "#6d4c41", "#7cb342", "#aed581",
        "#061008", "#a0c890", "#0c180a", "#1c3014", "#182810",
        "grid", "#5b8c3e", category="game",
    ),
    "fortnite": _T(
        "Fortnite", "#0a0614", "#140c24", "#f0e8ff", "#9080c0",
        "#9d4edd", "#00f5d4", "#ff006e", "#7b2cbf", "#ff9f1c",
        "#060410", "#c0b0e0", "#0e0a1a", "#241848", "#1c1030",
        "particles", "#9d4edd", category="game",
    ),
    "cs2": _T(
        "CS2", "#0a0c0e", "#14181c", "#e8ece8", "#809088",
        "#de9b35", "#a3cf5a", "#e74c3c", "#c27c0e", "#5d8aa8",
        "#060808", "#b0b8b0", "#0c1012", "#28241a", "#1c1e20",
        "scanlines", "#de9b35", category="game",
    ),
    "zelda": _T(
        "Zelda", "#06140e", "#0e2018", "#e0fff0", "#70a888",
        "#2dc653", "#ffd60a", "#1b4332", "#40916c", "#95d5b2",
        "#040e0a", "#90c8a8", "#0a1810", "#143828", "#10241a",
        "aurora", "#2dc653", category="game",
    ),
    "pokemon": _T(
        "Pokémon", "#0c0a14", "#181428", "#fff8e8", "#a090b0",
        "#ffcb05", "#3d7dca", "#ee1515", "#ffcb05", "#3d7dca",
        "#080610", "#d0c0a0", "#100e1a", "#302010", "#201828",
        "particles", "#ffcb05", category="game",
    ),
    "elden": _T(
        "Elden Ring", "#0c0a06", "#1a160c", "#f5f0d8", "#a09070",
        "#c9a227", "#e8d48b", "#8b0000", "#b8860b", "#daa520",
        "#080604", "#d0c090", "#12100a", "#302810", "#242010",
        "embers", "#c9a227", category="game",
    ),
    "overwatch": _T(
        "Overwatch", "#061018", "#0c1c2c", "#e8f4ff", "#7098b0",
        "#f99e1a", "#ffffff", "#218ffe", "#f99e1a", "#00c3ff",
        "#040c14", "#90b8d0", "#081420", "#183040", "#142838",
        "particles", "#f99e1a", category="game",
    ),
    # ── Weather ──
    "lightning": _T(
        "Sấm sét", "#07060e", "#12101c", "#f0f4ff", "#8890b0",
        "#a8c8ff", "#ffe066", "#7b68ee", "#c0d8ff", "#9b8cff",
        "#04040a", "#b0b8d8", "#0a0a14", "#1a2040", "#1c1830",
        "lightning", "#e8f0ff", category="weather",
    ),
    "storm": _T(
        "Bão tố", "#0a0c12", "#141820", "#e8eef8", "#8090a8",
        "#7eb8d8", "#a0d0f0", "#5c7a9a", "#90c0e0", "#6a90b0",
        "#060810", "#a0b0c8", "#0c1018", "#1a2838", "#182028",
        "storm", "#9ec9e8", category="weather",
    ),
    "wind": _T(
        "Gió lốc", "#0c1014", "#161c22", "#e8f4f0", "#809890",
        "#7dcfb6", "#b0e8d0", "#5a8a7a", "#90e0c0", "#6ab0a0",
        "#080c10", "#a0c8b8", "#0e1418", "#1a3028", "#182420",
        "wind", "#7dcfb6", category="weather",
    ),
    "sunrise": _T(
        "Bình minh", "#1a0e12", "#2a1818", "#fff5e8", "#c0a090",
        "#ff9f1c", "#ffd166", "#e76f51", "#ffb703", "#f4a261",
        "#120a0c", "#e0c0a0", "#180e10", "#3a2018", "#2a1814",
        "sunrise", "#ffb703", category="weather",
    ),
    "sunset_sky": _T(
        "Hoàng hôn", "#140c18", "#241428", "#ffe8f0", "#b090a0",
        "#ff6b6b", "#ffd93d", "#c44569", "#f9a826", "#e056fd",
        "#0c0810", "#d0a0b0", "#120a14", "#3a1828", "#281420",
        "sunrise", "#ff8fab", category="weather",
    ),
    "rain": _T(
        "Mưa rơi", "#080c14", "#101820", "#e0eaf4", "#7090a8",
        "#4cc9f0", "#90e0ef", "#4895ef", "#00b4d8", "#48cae4",
        "#060a10", "#90b0c8", "#0a1018", "#142838", "#122028",
        "rain", "#90e0ef", category="weather",
    ),
    "snow": _T(
        "Tuyết rơi", "#0e1218", "#181e28", "#f0f6ff", "#90a0b8",
        "#c8d8f0", "#ffffff", "#a0b0c8", "#e0e8f8", "#b0c0d8",
        "#0a0e14", "#c0d0e0", "#10141c", "#283040", "#1c2430",
        "snow", "#ffffff", category="weather",
    ),
    "fog": _T(
        "Sương mù", "#121418", "#1c2024", "#e8ece8", "#909890",
        "#b0b8b0", "#d0d8d0", "#707870", "#c0c8c0", "#a0a8a0",
        "#0c0e10", "#b0b8b0", "#141618", "#282c30", "#202428",
        "fog", "#c0c8c0", category="weather",
    ),
    "aurora_night": _T(
        "Cực quang", "#060c10", "#0c1818", "#e0fff4", "#70a090",
        "#00f5d4", "#9b5de5", "#00bbf9", "#80ffdb", "#c77dff",
        "#040a0c", "#90c8b8", "#081210", "#143028", "#102420",
        "aurora", "#00f5d4", category="weather",
    ),
    # Night mode — dịu mắt ca đêm + contrast rõ chữ (18)
    "night_soft": _T(
        "Night Soft", "#08080c", "#12121a", "#eef1f7", "#a0a8b8",
        "#9ab0c8", "#7ab090", "#c08090", "#a898c0", "#90a0b8",
        "#06060a", "#b0b8c4", "#0a0a10", "#1a1a24", "#181820",
        "fog", "#7a8498", category="classic",
    ),
}

# Boost thêm khi user bật "Night contrast" trong Settings
NIGHT_CONTRAST_BOOST = {
    "text": "#f5f7fc",
    "muted": "#b4bcc8",
    "console_fg": "#c8d0dc",
    "accent": "#a8c0e0",
}


CATEGORY_LABELS = {
    "classic": "✦ Classic",
    "hero": "🦸 Superhero",
    "anime": "🌸 Anime",
    "game": "🎮 Game",
    "weather": "🌤 Thời tiết",
}

DEFAULT_THEME_ID = "midnight"


class ThemeManager:
    """Load/save theme preference and broadcast palette changes."""

    def __init__(self, base_dir: str) -> None:
        self.base_dir = base_dir
        self.config_path = os.path.join(base_dir, "acc2019_window.json")
        self.theme_id = DEFAULT_THEME_ID
        self._listeners: list[Callable[[dict], None]] = []
        self._load()

    @property
    def colors(self) -> dict:
        return THEMES.get(self.theme_id, THEMES[DEFAULT_THEME_ID])

    def _load(self) -> None:
        if not os.path.isfile(self.config_path):
            return
        try:
            with open(self.config_path, encoding="utf-8") as f:
                data = json.load(f)
            tid = data.get("theme", DEFAULT_THEME_ID)
            if tid in THEMES:
                self.theme_id = tid
        except (OSError, json.JSONDecodeError):
            pass

    def save(self) -> None:
        data: dict = {}
        if os.path.isfile(self.config_path):
            try:
                with open(self.config_path, encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError):
                data = {}
        data["theme"] = self.theme_id
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError:
            pass

    def set_theme(self, theme_id: str) -> None:
        if theme_id not in THEMES:
            return
        if theme_id == self.theme_id:
            return
        self.theme_id = theme_id
        self.save()
        c = self.colors
        for cb in self._listeners:
            try:
                cb(c)
            except Exception:
                pass

    def on_change(self, callback: Callable[[dict], None]) -> None:
        self._listeners.append(callback)

    def theme_names(self) -> list[tuple[str, str]]:
        return [(tid, t["name"]) for tid, t in THEMES.items()]

    def themes_by_category(self) -> dict[str, list[tuple[str, str]]]:
        out: dict[str, list[tuple[str, str]]] = {}
        for tid, t in THEMES.items():
            cat = t.get("category", "classic")
            out.setdefault(cat, []).append((tid, t["name"]))
        return out


def _thunder_wav_path(base_dir: str | None = None) -> str:
    candidates = []
    if base_dir:
        candidates.append(os.path.join(base_dir, "assets", "thunder.wav"))
    candidates.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "thunder.wav"))
    for p in candidates:
        if os.path.isfile(p):
            return p
    return candidates[0] if candidates else "thunder.wav"


def play_thunder(base_dir: str | None = None) -> None:
    """Phát tiếng sấm (winsound async)."""
    path = _thunder_wav_path(base_dir)
    try:
        import winsound
        if os.path.isfile(path):
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        else:
            # fallback beeps
            winsound.Beep(80, 80)
            winsound.Beep(60, 200)
    except Exception:
        pass


class AnimatedBackground:
    """Canvas nền động — tối ưu nhẹ (FPS thấp, ít particle, skip khi ẩn)."""

    # FPS & particle counts theo effect (nhẹ → mượt)
    _FX_PROFILE = {
        "particles": (8, 12),
        "grid": (6, 8),
        "embers": (8, 14),
        "aurora": (6, 0),
        "orbs": (8, 6),
        "waves": (6, 0),
        "scanlines": (5, 0),
        "lightning": (10, 8),   # mây ít, sét vẽ khi có
        "storm": (7, 8),
        "wind": (8, 10),
        "sunrise": (5, 0),
        "rain": (10, 16),
        "snow": (8, 14),
        "fog": (5, 5),
    }

    def __init__(
        self,
        parent: tk.Misc,
        root: tk.Tk,
        theme_mgr: ThemeManager,
        *,
        fps: int = 10,
        base_dir: str | None = None,
        flash_targets: list | None = None,
    ) -> None:
        self.root = root
        self.theme_mgr = theme_mgr
        self.base_dir = base_dir
        # chỉ flash canvas + 1-2 frame chính (tránh recolor cả tree)
        self.flash_targets = list(flash_targets or [])[:3]
        self._base_fps = max(5, min(15, fps))
        self._fps_ms = max(66, int(1000 / self._base_fps))
        self._running = True
        self._paused = False
        self._job = None
        self._t0 = time.monotonic()
        self._w = 1
        self._h = 1
        self._lightning: list[dict] = []
        self._next_strike = time.monotonic() + random.uniform(4.0, 10.0)
        self._flash_until = 0.0
        self._sound_enabled = True
        self._frame = 0
        self._dirty = True
        self._resize_job = None

        self.canvas = tk.Canvas(
            parent, bg=theme_mgr.colors["bg"], highlightthickness=0, bd=0,
        )
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)
        try:
            self.canvas.lower()
        except tk.TclError:
            pass

        self._particles: list[dict] = []
        self._apply_profile()
        self.canvas.bind("<Configure>", self._on_resize)
        theme_mgr.on_change(self._on_theme)
        self._tick()

    def _apply_profile(self) -> None:
        eff = self.theme_mgr.colors.get("effect", "particles")
        fps, n_part = self._FX_PROFILE.get(eff, (8, 10))
        self._fps_ms = max(66, int(1000 / max(5, fps)))
        self._init_particles(n_part)

    def _on_theme(self, colors: dict) -> None:
        self.canvas.configure(bg=colors["bg"])
        self._lightning.clear()
        self._apply_profile()
        if colors.get("effect") == "lightning":
            self._next_strike = time.monotonic() + random.uniform(3.0, 7.0)
        self._dirty = True

    def _on_resize(self, event=None) -> None:
        # debounce resize redraw
        if event:
            self._w = max(1, event.width)
            self._h = max(1, event.height)
        else:
            self._w = max(1, self.canvas.winfo_width())
            self._h = max(1, self.canvas.winfo_height())
        self._dirty = True
        if self._resize_job:
            try:
                self.root.after_cancel(self._resize_job)
            except Exception:
                pass
        self._resize_job = self.root.after(80, self._after_resize)

    def _after_resize(self) -> None:
        self._resize_job = None
        self._dirty = True

    def _init_particles(self, n: int) -> None:
        c = self.theme_mgr.colors
        effect = c.get("effect", "particles")
        self._particles = []
        for _ in range(max(0, n)):
            self._particles.append({
                "x": random.random(),
                "y": random.random(),
                "vx": (random.random() - 0.5) * 0.003,
                "vy": (random.random() - 0.5) * 0.003 - (0.001 if effect == "embers" else 0),
                "r": random.uniform(1.0, 2.2),
                "phase": random.random() * math.tau,
                "speed": random.uniform(0.4, 1.2),
                "len": random.uniform(0.08, 0.18),
            })

    def _visible(self) -> bool:
        try:
            if not self.canvas.winfo_ismapped():
                return False
            st = str(self.root.state())
            if st == "iconic":
                return False
            return self._w >= 4 and self._h >= 4
        except tk.TclError:
            return False

    def _tick(self) -> None:
        if not self._running:
            return
        try:
            if self._paused or not self._visible():
                # idle poll chậm khi ẩn
                self._job = self.root.after(400, self._tick)
                return
            eff = self.theme_mgr.colors.get("effect", "")
            # lightning: chỉ vẽ nặng khi có sét / đến giờ sét
            now = time.monotonic()
            if eff == "lightning" and not self._lightning and now < self._next_strike - 0.05:
                # mây update thưa hơn
                if self._frame % 3 == 0 or self._dirty:
                    self._draw()
                    self._dirty = False
            else:
                self._draw()
                self._dirty = False
            self._frame += 1
        except tk.TclError:
            self._running = False
            return
        # boost fps tạm khi sét đang hiện
        ms = 50 if self._lightning else self._fps_ms
        self._job = self.root.after(ms, self._tick)

    def stop(self) -> None:
        self._running = False
        if self._job:
            try:
                self.root.after_cancel(self._job)
            except Exception:
                pass

    def _draw(self) -> None:
        c = self.theme_mgr.colors
        effect = c.get("effect", "particles")
        color = c.get("particle", c["accent"])
        bg = c["bg"]
        t = time.monotonic() - self._t0
        now = time.monotonic()
        w, h = self._w, self._h
        if w < 2 or h < 2:
            return

        # flash recovery
        if self._flash_until and now > self._flash_until:
            self._end_flash(bg)
            self._flash_until = 0.0

        # delete only fx tags (nhanh hơn delete all)
        self.canvas.delete("fx")

        if effect == "particles":
            self._draw_particles(color, w, h, t, drift=True)
        elif effect == "grid":
            self._draw_grid(color, w, h, t)
            self._draw_particles(color, w, h, t, drift=True, alpha_scale=0.5)
        elif effect == "embers":
            self._draw_embers(color, w, h, t)
        elif effect == "aurora":
            self._draw_aurora(color, c.get("success", color), w, h, t)
        elif effect == "orbs":
            self._draw_orbs(color, c.get("csv", color), w, h, t)
        elif effect == "waves":
            self._draw_waves(color, w, h, t)
        elif effect == "scanlines":
            self._draw_scanlines(color, w, h, t)
        elif effect == "lightning":
            self._draw_storm_base(color, w, h, t)
            self._update_lightning(w, h, now)
        elif effect == "storm":
            self._draw_storm_base(color, w, h, t)
            self._draw_wind_streaks(color, w, h, t, strength=1.2)
            # occasional distant flash without full bolt sometimes
            if now >= self._next_strike:
                if random.random() < 0.35:
                    self._spawn_lightning(w, h, now, sound=False)
                self._next_strike = now + random.uniform(5.0, 14.0)
            self._update_lightning(w, h, now, spawn=False)
        elif effect == "wind":
            self._draw_wind_streaks(color, w, h, t, strength=1.6)
            self._draw_particles(color, w, h, t, drift=True, alpha_scale=0.4)
        elif effect == "sunrise":
            self._draw_sunrise(c, w, h, t)
        elif effect == "rain":
            self._draw_rain(color, w, h, t)
        elif effect == "snow":
            self._draw_snow(color, w, h, t)
        elif effect == "fog":
            self._draw_fog(color, w, h, t)
        else:
            self._draw_particles(color, w, h, t, drift=True)

        self.canvas.create_rectangle(0, 0, w, 1, fill=bg, outline="", tags="fx")
        self.canvas.create_rectangle(0, h - 1, w, h, fill=bg, outline="", tags="fx")

    # ── classic drawers ─────────────────────────────────────────────────────

    def _draw_particles(self, color, w, h, t, *, drift=True, alpha_scale=1.0) -> None:
        for p in self._particles:
            if drift:
                p["x"] = (p["x"] + p["vx"] * p["speed"]) % 1.0
                p["y"] = (p["y"] + p["vy"] * p["speed"]) % 1.0
            pulse = 0.4 + 0.6 * (0.5 + 0.5 * math.sin(t * p["speed"] * 2 + p["phase"]))
            r = p["r"] * (0.7 + 0.5 * pulse) * alpha_scale
            x, y = p["x"] * w, p["y"] * h
            self.canvas.create_oval(
                x - r, y - r, x + r, y + r,
                fill=color, outline="", tags="fx",
            )

    def _draw_grid(self, color, w, h, t) -> None:
        step = 24
        offset = int((t * 12) % step)
        for x in range(-step + offset, w + step, step):
            self.canvas.create_line(x, 0, x, h, fill=color, width=1, tags="fx", stipple="gray25")
        for y in range(-step + offset, h + step, step):
            self.canvas.create_line(0, y, w, y, fill=color, width=1, tags="fx", stipple="gray25")

    def _draw_embers(self, color, w, h, t) -> None:
        for p in self._particles:
            p["y"] = (p["y"] + p["vy"] * p["speed"] - 0.003) % 1.0
            p["x"] = (p["x"] + math.sin(t * 2 + p["phase"]) * 0.001) % 1.0
            r = p["r"] * (0.8 + 0.6 * abs(math.sin(t * 3 + p["phase"])))
            x, y = p["x"] * w, p["y"] * h
            self.canvas.create_oval(x - r, y - r, x + r, y + r, fill=color, outline="", tags="fx")

    def _draw_aurora(self, c1, c2, w, h, t) -> None:
        for i in range(4):
            phase = t * 0.5 + i * 1.1
            y0 = h * (0.2 + 0.15 * i) + math.sin(phase) * 6
            pts = []
            for x in range(0, w + 16, 16):
                y = y0 + math.sin(x * 0.03 + phase) * 8
                pts.extend([x, y])
            if len(pts) >= 4:
                self.canvas.create_line(
                    *pts, fill=c1 if i % 2 == 0 else c2,
                    width=2, smooth=True, tags="fx",
                )

    def _draw_orbs(self, c1, c2, w, h, t) -> None:
        for i, p in enumerate(self._particles[:8]):
            cx = (0.5 + 0.35 * math.sin(t * 0.35 * p["speed"] + p["phase"])) * w
            cy = (0.5 + 0.3 * math.cos(t * 0.25 * p["speed"] + p["phase"] * 1.3)) * h
            r = 6 + 10 * p["r"] + 3 * math.sin(t + p["phase"])
            col = c1 if i % 2 == 0 else c2
            self.canvas.create_oval(
                cx - r, cy - r, cx + r, cy + r,
                outline=col, width=1, tags="fx",
            )

    def _draw_waves(self, color, w, h, t) -> None:
        for band in range(3):
            pts = []
            amp = 4 + band * 3
            y_base = h * (0.35 + band * 0.2)
            for x in range(0, w + 12, 12):
                y = y_base + math.sin(x * 0.04 + t * (1.4 + band * 0.3)) * amp
                pts.extend([x, y])
            if len(pts) >= 4:
                self.canvas.create_line(*pts, fill=color, width=1, smooth=True, tags="fx")

    def _draw_scanlines(self, color, w, h, t) -> None:
        step = 3
        offset = int((t * 30) % step)
        for y in range(offset, h, step * 2):
            self.canvas.create_line(0, y, w, y, fill=color, width=1, tags="fx", stipple="gray50")
        by = int((t * 50) % max(h, 1))
        self.canvas.create_rectangle(0, by, w, by + 1, fill=color, outline="", tags="fx")

    # ── weather drawers ─────────────────────────────────────────────────────

    def _draw_storm_base(self, color, w, h, t) -> None:
        """Mây bay chậm — ít oval để nhẹ."""
        for i, p in enumerate(self._particles[:8]):
            p["x"] = (p["x"] + 0.0003 * (0.5 + 0.5 * p["speed"])) % 1.0
            bob = 0.03 * math.sin(t * 0.12 + p["phase"])
            cx = p["x"] * w
            cy = h * (0.25 + 0.1 * ((i % 4) / 4) + bob)
            rw = 20 + 12 * p["r"]
            rh = 6 + 3 * p["r"]
            self.canvas.create_oval(
                cx - rw, cy - rh, cx + rw, cy + rh,
                fill=color, outline="", tags="fx", stipple="gray50",
            )

    def _gen_bolt_paths(self, w: int, h: int, *, size: str = "big") -> list[list[float]]:
        """
        Tạo tia sét thật hơn: thân chính + nhánh rẽ (path riêng).
        size: big | mid | small
        """
        if size == "big":
            segs, jag, branch_p, depth = random.randint(7, 12), 0.16, 0.55, 2
        elif size == "small":
            segs, jag, branch_p, depth = random.randint(3, 5), 0.08, 0.25, 1
            h = max(8, int(h * random.uniform(0.35, 0.55)))
        else:
            segs, jag, branch_p, depth = random.randint(5, 8), 0.12, 0.4, 1

        def branch(x0, y0, length, segs_n, jag_n, depth_left) -> list[list[float]]:
            paths: list[list[float]] = []
            x, y = x0, y0
            main = [x, y]
            for i in range(segs_n):
                # zig-zag tự nhiên: lệch ngang + luôn xuống
                x += random.uniform(-w * jag_n, w * jag_n)
                step = length / segs_n * random.uniform(0.75, 1.2)
                y += step
                x = max(1, min(w - 1, x))
                y = min(h - 1, y)
                main.extend([x, y])
                if depth_left > 0 and i >= 1 and random.random() < branch_p:
                    # nhánh lệch 30–60°
                    ang = random.choice([-1, 1])
                    bx, by = x, y
                    bpts = [bx, by]
                    b_len = length * random.uniform(0.2, 0.45)
                    b_segs = max(2, segs_n // 2)
                    for _ in range(b_segs):
                        bx += ang * random.uniform(w * 0.02, w * jag_n * 1.2)
                        by += b_len / b_segs * random.uniform(0.7, 1.1)
                        bx = max(1, min(w - 1, bx))
                        by = min(h - 1, by)
                        bpts.extend([bx, by])
                    paths.append(bpts)
                    # sub-branch hiếm
                    if depth_left > 1 and random.random() < 0.35:
                        paths.extend(
                            branch(bx, by, b_len * 0.5, max(2, b_segs // 2), jag_n * 0.8, depth_left - 1)
                        )
            paths.insert(0, main)
            return paths

        x0 = random.uniform(0.12, 0.88) * w
        return branch(x0, 0.0, float(h), segs, jag, depth)

    def _spawn_lightning(self, w: int, h: int, now: float, *, sound: bool = True) -> None:
        # ngẫu nhiên to / vừa / nhỏ
        r = random.random()
        if r < 0.28:
            size = "big"
            width = random.uniform(2.8, 4.5)
            life = random.uniform(0.16, 0.32)
            flash = True
            multi = random.random() < 0.4
        elif r < 0.65:
            size = "mid"
            width = random.uniform(1.6, 2.8)
            life = random.uniform(0.12, 0.22)
            flash = random.random() < 0.7
            multi = random.random() < 0.2
        else:
            size = "small"
            width = random.uniform(0.8, 1.5)
            life = random.uniform(0.08, 0.16)
            flash = random.random() < 0.25
            multi = False

        paths = self._gen_bolt_paths(w, h, size=size)
        self._lightning.append({
            "paths": paths,
            "born": now,
            "life": life,
            "width": width,
            "size": size,
            "flicker": random.random() < 0.5,
        })
        if flash:
            intensity = 1.0 if size == "big" else (0.65 if size == "mid" else 0.35)
            self._start_flash(intensity=intensity)
        if sound and self._sound_enabled and size in ("big", "mid") and flash:
            delay = 60 if size == "big" else 100
            self.root.after(delay, lambda: play_thunder(self.base_dir))
        # double / forked strike
        if multi:
            self.root.after(
                random.randint(70, 160),
                lambda: self._spawn_lightning(w, h, time.monotonic(), sound=False),
            )

    def _start_flash(self, *, intensity: float = 1.0) -> None:
        self._flash_until = time.monotonic() + (0.05 + 0.05 * intensity)
        if intensity > 0.8:
            flash_bg = "#d0e0f8"
        elif intensity > 0.5:
            flash_bg = "#8a9cc0"
        else:
            flash_bg = "#2a3050"
        try:
            self.canvas.configure(bg=flash_bg)
        except tk.TclError:
            pass
        # flash tối đa 1 target phụ (nhẹ)
        if intensity >= 0.55 and self.flash_targets:
            try:
                self.flash_targets[0].configure(bg=flash_bg)
            except Exception:
                pass

    def _end_flash(self, bg: str) -> None:
        try:
            self.canvas.configure(bg=bg)
        except tk.TclError:
            pass
        if self.flash_targets:
            try:
                self.flash_targets[0].configure(bg=self.theme_mgr.colors.get("bg", bg))
            except Exception:
                pass

    def _update_lightning(self, w: int, h: int, now: float, *, spawn: bool = True) -> None:
        if spawn and now >= self._next_strike:
            self._spawn_lightning(w, h, now, sound=True)
            self._next_strike = now + random.uniform(5.0, 14.0)

        alive = []
        for bolt in self._lightning:
            age = now - bolt["born"]
            if age > bolt["life"]:
                continue
            if bolt.get("flicker") and 0.04 < age < 0.07:
                alive.append(bolt)
                continue
            alive.append(bolt)
            fade = max(0.0, 1.0 - age / bolt["life"])
            paths = bolt.get("paths") or ([bolt["pts"]] if bolt.get("pts") else [])
            # giới hạn nhánh để nhẹ
            paths = paths[:4]
            bw = bolt["width"]
            if fade > 0.55:
                col_glow, col_core = "#9ec5ff", "#ffffff"
            elif fade > 0.25:
                col_glow, col_core = "#6a90d0", "#e0ecff"
            else:
                col_glow, col_core = "#3a5080", "#a0b8e0"
            for pi, pts in enumerate(paths):
                if len(pts) < 4:
                    continue
                # downsample points if quá dài
                if len(pts) > 40:
                    pts = pts[::2]
                    if len(pts) % 2:
                        pts = pts[:-1]
                scale = 1.0 if pi == 0 else 0.5
                try:
                    # 2 lớp thay vì 3
                    self.canvas.create_line(
                        *pts, fill=col_glow, width=max(1, (bw + 2.5) * scale),
                        smooth=False, tags="fx",
                    )
                    self.canvas.create_line(
                        *pts, fill=col_core, width=max(1, bw * scale),
                        smooth=False, tags="fx",
                    )
                except tk.TclError:
                    pass
        self._lightning = alive

    def _draw_wind_streaks(self, color, w, h, t, *, strength=1.0) -> None:
        for p in self._particles:
            p["x"] = (p["x"] + 0.012 * strength * p["speed"]) % 1.0
            p["y"] = (p["y"] + math.sin(t * 2 + p["phase"]) * 0.001) % 1.0
            x = p["x"] * w
            y = p["y"] * h
            ln = p.get("len", 0.12) * w * 0.5
            self.canvas.create_line(
                x, y, x + ln, y + math.sin(p["phase"]) * 2,
                fill=color, width=1, tags="fx",
            )

    def _draw_sunrise(self, c: dict, w: int, h: int, t: float) -> None:
        # gradient bands (sky)
        colors = [c.get("danger", "#e76f51"), c.get("accent", "#ff9f1c"), c.get("success", "#ffd166"), c.get("particle", "#ffb703")]
        for i, col in enumerate(colors):
            y0 = h * (i / len(colors))
            y1 = h * ((i + 1) / len(colors))
            self.canvas.create_rectangle(0, y0, w, y1, fill=col, outline="", tags="fx", stipple="gray50")
        # sun
        cx = w * (0.5 + 0.05 * math.sin(t * 0.2))
        cy = h * 0.75
        r = min(w, h) * 0.28
        self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=c.get("success", "#ffd166"), outline="", tags="fx")
        self.canvas.create_oval(cx - r * 0.55, cy - r * 0.55, cx + r * 0.55, cy + r * 0.55, fill="#fff3c4", outline="", tags="fx")
        # rays
        for i in range(8):
            ang = t * 0.15 + i * math.pi / 4
            x2 = cx + math.cos(ang) * r * 1.6
            y2 = cy + math.sin(ang) * r * 0.6
            self.canvas.create_line(cx, cy, x2, y2, fill=c.get("particle", "#ffb703"), width=1, tags="fx")

    def _draw_rain(self, color, w, h, t) -> None:
        for p in self._particles:
            p["y"] = (p["y"] + 0.04 * p["speed"]) % 1.0
            p["x"] = (p["x"] + 0.004 * p["speed"]) % 1.0
            x, y = p["x"] * w, p["y"] * h
            ln = 4 + 6 * p["r"]
            self.canvas.create_line(x, y, x - 1.5, y + ln, fill=color, width=1, tags="fx")

    def _draw_snow(self, color, w, h, t) -> None:
        for p in self._particles:
            p["y"] = (p["y"] + 0.008 * p["speed"]) % 1.0
            p["x"] = (p["x"] + math.sin(t + p["phase"]) * 0.002) % 1.0
            x, y = p["x"] * w, p["y"] * h
            r = 1.2 + p["r"] * 0.8
            self.canvas.create_oval(x - r, y - r, x + r, y + r, fill=color, outline="", tags="fx")

    def _draw_fog(self, color, w, h, t) -> None:
        for i, p in enumerate(self._particles[:8]):
            p["x"] = (p["x"] + 0.002 * p["speed"]) % 1.0
            cx = p["x"] * w
            cy = h * (0.3 + 0.4 * ((i % 4) / 4))
            rw = 30 + 20 * p["r"]
            rh = 8 + 4 * p["r"]
            self.canvas.create_oval(
                cx - rw, cy - rh, cx + rw, cy + rh,
                fill=color, outline="", tags="fx", stipple="gray25",
            )


def apply_theme_to_module_colors(colors: dict) -> None:
    """Cập nhật hằng màu trong các module đã import (best-effort)."""
    try:
        import acc2019_core as core

        core.COLOR_BG = colors["bg"]
        core.COLOR_CARD = colors["card"]
        core.COLOR_TEXT = colors["text"]
        core.COLOR_MUTED = colors["muted"]
        core.COLOR_ACCENT_PS = colors["accent"]
        core.COLOR_SUCCESS = colors["success"]
        core.COLOR_DANGER = colors["danger"]
        core.COLOR_BUTTON_HOVER = colors["hover"]
    except Exception:
        pass

    try:
        import modules.window_chrome as chrome

        chrome.COLOR_BG = colors["bg"]
        chrome.COLOR_CARD = colors["card"]
        chrome.COLOR_MUTED = colors["muted"]
        chrome.COLOR_DANGER = colors["danger"]
        chrome.COLOR_ACCENT = colors["accent"]
    except Exception:
        pass

    try:
        import modules.emb_panel as emb

        emb.COLOR_BG = colors["bg"]
        emb.COLOR_CARD = colors["card"]
        emb.COLOR_TEXT = colors["text"]
        emb.COLOR_MUTED = colors["muted"]
        emb.COLOR_ACCENT = colors["accent"]
        emb.COLOR_SUCCESS = colors["success"]
        emb.COLOR_DANGER = colors["danger"]
        emb.COLOR_EMB = colors["emb"]
        emb.COLOR_TABLE_BG = colors["table_bg"]
        emb.COLOR_TABLE_HEAD = colors["card"]
        emb.COLOR_TABLE_SEL = colors["table_sel"]
    except Exception:
        pass

    try:
        import modules.sys_monitor as mon

        mon.COLOR_BG = colors["bg"]
        mon.COLOR_MUTED = colors["muted"]
        mon.COLOR_CSV = colors["csv"]
        mon.COLOR_SUCCESS = colors["success"]
    except Exception:
        pass


def _all_theme_colors() -> set[str]:
    keys = ("bg", "card", "console_bg", "table_bg", "text", "muted", "accent",
            "success", "danger", "emb", "csv", "hover", "particle", "table_sel")
    out: set[str] = set()
    for t in THEMES.values():
        for k in keys:
            v = t.get(k)
            if v:
                out.add(str(v).lower())
    return out


_THEME_COLORS = _all_theme_colors()


def recolor_widget_tree(widget: tk.Misc, colors: dict, *, depth: int = 0) -> None:
    """Đệ quy đổi bg/fg cho widget tree (giới hạn depth — nhẹ)."""
    if depth > 18:
        return
    try:
        cls = widget.winfo_class()
    except tk.TclError:
        return

    bg_keys = ("bg", "background")
    fg_keys = ("fg", "foreground")
    active_bg = ("activebackground",)
    select = ("selectcolor",)
    insert = ("insertbackground",)

    def _cfg(keys, value):
        for k in keys:
            try:
                widget.configure(**{k: value})
                return
            except tk.TclError:
                continue

    try:
        current_bg = str(widget.cget("bg")).lower()
    except tk.TclError:
        current_bg = ""

    if current_bg in _THEME_COLORS or current_bg in ("systembuttonface",):
        # map known role by closeness to new palette roles
        if current_bg in (colors["card"].lower(),) or current_bg in {
            t["card"].lower() for t in THEMES.values()
        }:
            _cfg(bg_keys, colors["card"])
        elif current_bg in {
            t["console_bg"].lower() for t in THEMES.values()
        } | {t["table_bg"].lower() for t in THEMES.values()}:
            if "text" in cls.lower() or cls in ("Text", "ScrolledText"):
                _cfg(bg_keys, colors["console_bg"])
            else:
                _cfg(bg_keys, colors.get("table_bg", colors["bg"]))
        else:
            _cfg(bg_keys, colors["bg"])

    try:
        current_fg = str(widget.cget("fg")).lower()
    except tk.TclError:
        current_fg = ""

    role_sets = {
        "accent": {t["accent"].lower() for t in THEMES.values()},
        "success": {t["success"].lower() for t in THEMES.values()},
        "danger": {t["danger"].lower() for t in THEMES.values()},
        "emb": {t["emb"].lower() for t in THEMES.values()},
        "csv": {t["csv"].lower() for t in THEMES.values()},
        "muted": {t["muted"].lower() for t in THEMES.values()},
        "text": {t["text"].lower() for t in THEMES.values()},
    }
    for role, s in role_sets.items():
        if current_fg in s:
            _cfg(fg_keys, colors.get(role, colors["text"]))
            break

    if cls in ("Button", "TButton", "Checkbutton", "Radiobutton"):
        _cfg(active_bg, colors["card"])
        _cfg(select, colors["card"])
    if cls in ("Text", "ScrolledText"):
        _cfg(bg_keys, colors["console_bg"])
        _cfg(fg_keys, colors["console_fg"])
        _cfg(insert, colors["text"])

    try:
        for child in widget.winfo_children():
            recolor_widget_tree(child, colors, depth=depth + 1)
    except tk.TclError:
        pass
