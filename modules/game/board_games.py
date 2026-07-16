"""XO NxN (≤64), Cờ tướng đủ quân, Cờ vua đủ quân + gợi ý admin + theme game."""

from __future__ import annotations

import random
import tkinter as tk
from tkinter import messagebox
from typing import Callable

from modules.game.ui_common import BetBar, ConfettiCanvas, beep

BG, CARD, TEXT, MUTED = "#0c0c14", "#141424", "#ffffff", "#82829c"
ACCENT, SUCCESS, DANGER, GOLD = "#00d2ff", "#00e676", "#ff1744", "#ffd60a"

# Theme presets cho board games
GAME_THEMES = {
    "midnight": {"bg": "#0c0c14", "board_a": "#1a1a2e", "board_b": "#16213e", "line": "#0f3460", "accent": "#00d2ff"},
    "wood": {"bg": "#1a120c", "board_a": "#deb887", "board_b": "#c4a574", "line": "#5c4033", "accent": "#ffb703"},
    "neon": {"bg": "#050510", "board_a": "#120820", "board_b": "#1a0a30", "line": "#ff00aa", "accent": "#00fff0"},
    "classic": {"bg": "#1a1a1a", "board_a": "#eeeed2", "board_b": "#769656", "line": "#333", "accent": "#fff"},
    "ocean": {"bg": "#061018", "board_a": "#0c2840", "board_b": "#0a1c30", "line": "#4cc9f0", "accent": "#90e0ef"},
}


class GameThemeBar(tk.Frame):
    def __init__(self, parent, on_change: Callable[[dict], None], **kw):
        super().__init__(parent, bg=BG, **kw)
        tk.Label(self, text="Theme", font=("Segoe UI", 7), fg=MUTED, bg=BG).pack(side=tk.LEFT)
        self.var = tk.StringVar(value="midnight")
        for name in GAME_THEMES:
            tk.Radiobutton(
                self, text=name[:4], variable=self.var, value=name,
                font=("Segoe UI", 6), fg=TEXT, bg=BG, selectcolor=CARD,
                command=lambda: on_change(GAME_THEMES[self.var.get()]),
            ).pack(side=tk.LEFT)


def _win_len(n: int) -> int:
    if n <= 3:
        return 3
    if n <= 5:
        return n
    if n <= 10:
        return 5
    return 5  # 11–64: 5 in a row


# ═══════════════════════════════════════════════════════════════════════
# XO / CARO N×N (canvas, max 64)
# ═══════════════════════════════════════════════════════════════════════

class XOView(tk.Frame):
    def __init__(self, parent, profile, *, is_host=True, is_admin=False, on_points_change=None, **kw):
        super().__init__(parent, bg=BG, **kw)
        self.profile = profile
        self.is_admin = is_admin
        self.on_points_change = on_points_change
        self.n = 3
        self.win_need = 3
        self.board: list[list[str]] = []
        self.turn = "X"
        self.vs_ai = tk.BooleanVar(value=True)
        self._locked = False
        self._round_bet = 0
        self._hint = None  # (r,c)
        self.theme = dict(GAME_THEMES["midnight"])
        self._build()
        self._new_board(3)

    def _build(self) -> None:
        tk.Label(self, text="⭕ XO / CARO", font=("Segoe UI", 9, "bold"), fg=ACCENT, bg=BG).pack(anchor="w")
        opts = tk.Frame(self, bg=BG)
        opts.pack(fill=tk.X, pady=2)
        tk.Label(opts, text="Cỡ bàn", font=("Segoe UI", 8), fg=MUTED, bg=BG).pack(side=tk.LEFT)
        self.size_var = tk.IntVar(value=3)
        sp = tk.Spinbox(
            opts, from_=3, to=64, width=4, textvariable=self.size_var,
            font=("Consolas", 9), bg=CARD, fg=ACCENT, buttonbackground=CARD,
            command=self._on_size_spin,
        )
        sp.pack(side=tk.LEFT, padx=4)
        sp.bind("<Return>", lambda _e: self._on_size_spin())
        tk.Label(opts, text="(3–64, thắng 3–5 liên)", font=("Segoe UI", 6), fg=MUTED, bg=BG).pack(side=tk.LEFT)
        tk.Checkbutton(
            opts, text="AI", variable=self.vs_ai, font=("Segoe UI", 8),
            fg=TEXT, bg=BG, selectcolor=CARD,
        ).pack(side=tk.LEFT, padx=6)
        GameThemeBar(self, self._apply_theme).pack(fill=tk.X)
        self.bet = BetBar(self, lambda: self.profile.points)
        self.bet.pack(fill=tk.X, pady=2)

        self.cv = tk.Canvas(self, width=360, height=360, bg=self.theme["bg"], highlightthickness=0, cursor="hand2")
        self.cv.pack(pady=4)
        self.cv.bind("<Button-1>", self._on_click)

        bar = tk.Frame(self, bg=BG)
        bar.pack(fill=tk.X)
        tk.Button(bar, text="Ván mới", font=("Segoe UI", 8), bg=CARD, fg=TEXT, bd=0, padx=8,
                  command=self._on_size_spin, cursor="hand2").pack(side=tk.LEFT, padx=2)
        if self.is_admin:
            tk.Button(
                bar, text="💡 Gợi ý nước tốt (Admin)", font=("Segoe UI", 8, "bold"),
                bg="#2a2040", fg=GOLD, bd=0, padx=8, command=self._show_hint, cursor="hand2",
            ).pack(side=tk.LEFT, padx=4)
        self.lbl = tk.Label(self, text="Bạn = X", font=("Segoe UI", 8), fg=MUTED, bg=BG)
        self.lbl.pack()
        self.confetti = ConfettiCanvas(self, width=200, height=28, bg=BG)
        self.confetti.pack()

    def _apply_theme(self, th: dict) -> None:
        self.theme = dict(th)
        self.cv.configure(bg=th["bg"])
        self._draw()

    def _on_size_spin(self) -> None:
        try:
            n = int(self.size_var.get())
        except Exception:
            n = 3
        n = max(3, min(64, n))
        self.size_var.set(n)
        self._new_board(n)

    def _new_board(self, n: int) -> None:
        self.n = n
        self.win_need = _win_len(n)
        self.board = [[""] * n for _ in range(n)]
        self.turn = "X"
        self._locked = False
        self._round_bet = 0
        self._hint = None
        # canvas size
        cell = max(8, min(48, 360 // n))
        side = cell * n
        self._cell = cell
        self.cv.config(width=side, height=side)
        self._draw()
        self.lbl.config(text=f"Bàn {n}×{n} · thắng {self.win_need} liên · cược rồi đánh", fg=MUTED)

    def _draw(self) -> None:
        self.cv.delete("all")
        n, c = self.n, self._cell
        th = self.theme
        for r in range(n):
            for col in range(n):
                x0, y0 = col * c, r * c
                fill = th["board_a"] if (r + col) % 2 == 0 else th["board_b"]
                if self._hint == (r, col):
                    fill = "#3d5a1a"
                self.cv.create_rectangle(x0, y0, x0 + c, y0 + c, fill=fill, outline=th["line"], width=1)
                v = self.board[r][col]
                if v:
                    fs = max(6, min(22, c - 4))
                    color = SUCCESS if v == "X" else DANGER
                    self.cv.create_text(x0 + c / 2, y0 + c / 2, text=v, fill=color, font=("Segoe UI", fs, "bold"))
        if self._hint:
            r, col = self._hint
            x0, y0 = col * c, r * c
            self.cv.create_rectangle(x0 + 1, y0 + 1, x0 + c - 1, y0 + c - 1, outline=GOLD, width=2)

    def _on_click(self, e) -> None:
        if self._locked:
            return
        c = self._cell
        col, r = e.x // c, e.y // c
        if not (0 <= r < self.n and 0 <= col < self.n):
            return
        if self.board[r][col]:
            return
        if self._round_bet <= 0:
            bet = self.bet.value()
            if bet <= 0:
                messagebox.showinfo("XO", "Chọn mức cược trước", parent=self)
                return
            self._round_bet = bet
        self.board[r][col] = "X"
        self._hint = None
        self._draw()
        beep("click")
        if self._check_end():
            return
        if self.vs_ai.get():
            self.after(120, self._ai_move)

    def _check_end(self) -> bool:
        w = self._winner()
        if not w:
            return False
        self._locked = True
        bet = self._round_bet
        if w == "X":
            self.profile.add_points(bet)
            self.profile.record_game("xo", "win", bet, bet, f"{self.n}x{self.n}")
            self.lbl.config(text=f"Thắng! +{bet}", fg=SUCCESS)
            self.confetti.burst()
            beep("win")
        elif w == "O":
            self.profile.add_points(-bet)
            self.profile.record_game("xo", "lose", bet, -bet, f"{self.n}x{self.n}")
            self.lbl.config(text=f"Thua · {-bet}", fg=DANGER)
            beep("lose")
        else:
            self.lbl.config(text="Hòa", fg=MUTED)
        if self.on_points_change:
            self.on_points_change()
        return True

    def _winner(self) -> str | None:
        n, need = self.n, self.win_need
        b = self.board
        dirs = ((0, 1), (1, 0), (1, 1), (1, -1))
        for r in range(n):
            for c in range(n):
                p = b[r][c]
                if not p:
                    continue
                for dr, dc in dirs:
                    ok = True
                    for k in range(need):
                        rr, cc = r + dr * k, c + dc * k
                        if not (0 <= rr < n and 0 <= cc < n) or b[rr][cc] != p:
                            ok = False
                            break
                    if ok:
                        return p
        if all(b[r][c] for r in range(n) for c in range(n)):
            return "draw"
        return None

    def _ai_move(self) -> None:
        if self._locked:
            return
        move = self._best_move("O")
        if move is None:
            return
        r, c = move
        self.board[r][c] = "O"
        self._draw()
        self._check_end()

    def _best_move(self, who: str) -> tuple[int, int] | None:
        """Heuristic: win > block > center-ish > random near stones."""
        n = self.n
        empties = [(r, c) for r in range(n) for c in range(n) if not self.board[r][c]]
        if not empties:
            return None
        opp = "X" if who == "O" else "O"
        # immediate win / block
        for check in (who, opp):
            for r, c in empties:
                self.board[r][c] = check
                if self._winner() == check:
                    self.board[r][c] = ""
                    return (r, c)
                self.board[r][c] = ""
        # score cells near existing
        best_s, best = -1, None
        for r, c in empties:
            s = 0
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < n and 0 <= cc < n and self.board[rr][cc]:
                        s += 3 if self.board[rr][cc] == who else 2
            # prefer center
            s += max(0, 5 - abs(r - n // 2) - abs(c - n // 2))
            if s > best_s:
                best_s, best = s, (r, c)
        return best or random.choice(empties)

    def _show_hint(self) -> None:
        if not self.is_admin or self._locked:
            return
        m = self._best_move("X")
        if m:
            self._hint = m
            self._draw()
            self.lbl.config(text=f"💡 Admin gợi ý: hàng {m[0]+1}, cột {m[1]+1}", fg=GOLD)
            beep("click")


# ═══════════════════════════════════════════════════════════════════════
# CỜ TƯỚNG 9×10 — đủ quân (rules rút gọn hợp lệ cơ bản)
# ═══════════════════════════════════════════════════════════════════════

# piece: (side, type) side R/B
# types: K G M R C N P  (tướng sĩ tượng xe pháo mã tốt)
XIANGQI_START = [
    # rank 0 black back
    [("B", "R"), ("B", "N"), ("B", "M"), ("B", "G"), ("B", "K"), ("B", "G"), ("B", "M"), ("B", "N"), ("B", "R")],
    [None] * 9,
    [None, ("B", "C"), None, None, None, None, None, ("B", "C"), None],
    [("B", "P"), None, ("B", "P"), None, ("B", "P"), None, ("B", "P"), None, ("B", "P")],
    [None] * 9,
    [None] * 9,
    [("R", "P"), None, ("R", "P"), None, ("R", "P"), None, ("R", "P"), None, ("R", "P")],
    [None, ("R", "C"), None, None, None, None, None, ("R", "C"), None],
    [None] * 9,
    [("R", "R"), ("R", "N"), ("R", "M"), ("R", "G"), ("R", "K"), ("R", "G"), ("R", "M"), ("R", "N"), ("R", "R")],
]

XIANGQI_SYM = {
    ("R", "K"): "帅", ("R", "G"): "仕", ("R", "M"): "相", ("R", "R"): "俥",
    ("R", "C"): "炮", ("R", "N"): "傌", ("R", "P"): "兵",
    ("B", "K"): "将", ("B", "G"): "士", ("B", "M"): "象", ("B", "R"): "車",
    ("B", "C"): "砲", ("B", "N"): "馬", ("B", "P"): "卒",
}


class XiangqiView(tk.Frame):
    ROWS, COLS = 10, 9

    def __init__(self, parent, profile, *, is_host=True, is_admin=False, on_points_change=None, **kw):
        super().__init__(parent, bg=BG, **kw)
        self.profile = profile
        self.is_admin = is_admin
        self.on_points_change = on_points_change
        self.theme = dict(GAME_THEMES["wood"])
        self.sel = None
        self.alive = True
        self._round_bet = 0
        self._hint = None
        self._build()
        self._reset()

    def _build(self) -> None:
        tk.Label(self, text="♟️ CỜ TƯỚNG (đủ quân)", font=("Segoe UI", 9, "bold"), fg=GOLD, bg=BG).pack(anchor="w")
        tk.Label(self, text="Bạn = Đỏ. Ăn Tướng đối phương để thắng. Luật rút gọn.", font=("Segoe UI", 7), fg=MUTED, bg=BG).pack(anchor="w")
        GameThemeBar(self, self._apply_theme).pack(fill=tk.X)
        self.bet = BetBar(self, lambda: self.profile.points)
        self.bet.pack(fill=tk.X, pady=2)
        self.cv = tk.Canvas(self, width=360, height=400, bg=self.theme["board_a"], highlightthickness=0)
        self.cv.pack(pady=4)
        self.cv.bind("<Button-1>", self._click)
        bar = tk.Frame(self, bg=BG)
        bar.pack()
        tk.Button(bar, text="Ván mới", font=("Segoe UI", 8), bg=CARD, fg=TEXT, bd=0, command=self._reset, cursor="hand2").pack(side=tk.LEFT, padx=2)
        if self.is_admin:
            tk.Button(bar, text="💡 Gợi ý (Admin)", font=("Segoe UI", 8, "bold"), bg="#2a2040", fg=GOLD, bd=0,
                      command=self._hint_move, cursor="hand2").pack(side=tk.LEFT, padx=4)
        self.lbl = tk.Label(self, text="", font=("Segoe UI", 8), fg=MUTED, bg=BG)
        self.lbl.pack()
        self.confetti = ConfettiCanvas(self, width=200, height=28, bg=BG)
        self.confetti.pack()

    def _apply_theme(self, th: dict) -> None:
        self.theme = dict(th)
        self.cv.configure(bg=th["board_a"])
        self._draw()

    def _reset(self) -> None:
        self.board = [row[:] for row in XIANGQI_START]
        # deep copy None-safe
        self.board = [[p if p is None else (p[0], p[1]) for p in row] for row in XIANGQI_START]
        self.sel = None
        self.alive = True
        self._round_bet = 0
        self._hint = None
        self._draw()
        self.lbl.config(text="Đặt cược · chọn quân đỏ → ô đích", fg=MUTED)

    def _cell(self):
        return 36, 20, 20  # size, ox, oy

    def _draw(self) -> None:
        self.cv.delete("all")
        cs, ox, oy = self._cell()
        th = self.theme
        w, h = cs * 8, cs * 9
        # board
        self.cv.create_rectangle(ox, oy, ox + w, oy + h, fill=th["board_a"], outline=th["line"], width=2)
        for i in range(10):
            y = oy + i * cs
            self.cv.create_line(ox, y, ox + w, y, fill=th["line"])
        for j in range(9):
            x = ox + j * cs
            # river gap on vertical lines
            self.cv.create_line(x, oy, x, oy + 4 * cs, fill=th["line"])
            self.cv.create_line(x, oy + 5 * cs, x, oy + 9 * cs, fill=th["line"])
        # palace X
        for base in (0, 7):
            self.cv.create_line(ox + 3 * cs, oy + base * cs, ox + 5 * cs, oy + (base + 2) * cs, fill=th["line"])
            self.cv.create_line(ox + 5 * cs, oy + base * cs, ox + 3 * cs, oy + (base + 2) * cs, fill=th["line"])
        self.cv.create_text(ox + w / 2, oy + 4.5 * cs, text="楚 河        漢 界", fill=th["line"], font=("Segoe UI", 9))
        for r in range(10):
            for c in range(9):
                p = self.board[r][c]
                if not p:
                    continue
                x, y = ox + c * cs, oy + r * cs
                col = DANGER if p[0] == "R" else "#1a1a2e"
                if self.sel == (r, c) or self._hint == (r, c):
                    self.cv.create_oval(x - 14, y - 14, x + 14, y + 14, outline=GOLD, width=2)
                self.cv.create_oval(x - 13, y - 13, x + 13, y + 13, fill="#f5e6c8", outline=col, width=2)
                self.cv.create_text(x, y, text=XIANGQI_SYM.get(p, "?"), fill=col, font=("Segoe UI", 11, "bold"))

    def _rc(self, e):
        cs, ox, oy = self._cell()
        c = round((e.x - ox) / cs)
        r = round((e.y - oy) / cs)
        if 0 <= r < 10 and 0 <= c < 9:
            return r, c
        return None

    def _click(self, e) -> None:
        if not self.alive:
            return
        pos = self._rc(e)
        if not pos:
            return
        r, c = pos
        if self._round_bet <= 0:
            bet = self.bet.value()
            if bet <= 0:
                messagebox.showinfo("Cờ tướng", "Chọn cược trước", parent=self)
                return
            self._round_bet = bet
        p = self.board[r][c]
        if self.sel is None:
            if p and p[0] == "R":
                self.sel = (r, c)
                self._draw()
            return
        sr, sc = self.sel
        if (sr, sc) == (r, c):
            self.sel = None
            self._draw()
            return
        if self._legal(sr, sc, r, c):
            cap = self.board[r][c]
            self.board[r][c] = self.board[sr][sc]
            self.board[sr][sc] = None
            self.sel = None
            self._hint = None
            self._draw()
            beep("click")
            if cap and cap[1] == "K":
                self._end(True)
                return
            self.after(200, self._ai)
        else:
            if p and p[0] == "R":
                self.sel = (r, c)
            else:
                self.sel = None
            self._draw()

    def _legal(self, r0, c0, r1, c1) -> bool:
        """Luật rút gọn: không đi vào ô quân mình; tốt/tướng/xe/mã/pháo/sĩ/tượng basic."""
        p = self.board[r0][c0]
        if not p:
            return False
        t = self.board[r1][c1]
        if t and t[0] == p[0]:
            return False
        side, kind = p
        dr, dc = r1 - r0, c1 - c0
        adr, adc = abs(dr), abs(dc)

        def clear_line():
            if dr == 0:
                step = 1 if dc > 0 else -1
                return all(self.board[r0][c] is None for c in range(c0 + step, c1, step))
            if dc == 0:
                step = 1 if dr > 0 else -1
                return all(self.board[r][c0] is None for r in range(r0 + step, r1, step))
            return False

        def count_between():
            n = 0
            if dr == 0:
                step = 1 if dc > 0 else -1
                for c in range(c0 + step, c1, step):
                    if self.board[r0][c]:
                        n += 1
            elif dc == 0:
                step = 1 if dr > 0 else -1
                for r in range(r0 + step, r1, step):
                    if self.board[r][c0]:
                        n += 1
            else:
                return -1
            return n

        if kind == "K":
            # palace
            if not (3 <= c1 <= 5 and ((side == "R" and 7 <= r1 <= 9) or (side == "B" and 0 <= r1 <= 2))):
                return False
            return adr + adc == 1
        if kind == "G":
            if not (3 <= c1 <= 5 and ((side == "R" and 7 <= r1 <= 9) or (side == "B" and 0 <= r1 <= 2))):
                return False
            return adr == 1 and adc == 1
        if kind == "M":
            # elephant: 2 diagonal, not blocked, own half
            if adr != 2 or adc != 2:
                return False
            if self.board[r0 + dr // 2][c0 + dc // 2]:
                return False
            if side == "R" and r1 < 5:
                return False
            if side == "B" and r1 > 4:
                return False
            return True
        if kind == "R":
            return (dr == 0 or dc == 0) and clear_line()
        if kind == "C":
            if dr != 0 and dc != 0:
                return False
            mid = count_between()
            if t is None:
                return mid == 0
            return mid == 1
        if kind == "N":
            if not ((adr, adc) in ((2, 1), (1, 2))):
                return False
            # block
            if adr == 2 and self.board[r0 + (1 if dr > 0 else -1)][c0]:
                return False
            if adc == 2 and self.board[r0][c0 + (1 if dc > 0 else -1)]:
                return False
            return True
        if kind == "P":
            if side == "R":
                if r1 > r0:
                    return False
                if r0 >= 5:
                    return (adr == 1 and adc == 0) or (adr == 0 and adc == 1)
                return adr == 1 and adc == 0
            else:
                if r1 < r0:
                    return False
                if r0 <= 4:
                    return (adr == 1 and adc == 0) or (adr == 0 and adc == 1)
                return adr == 1 and adc == 0
        return False

    def _ai(self) -> None:
        if not self.alive:
            return
        moves = []
        for r in range(10):
            for c in range(9):
                p = self.board[r][c]
                if not p or p[0] != "B":
                    continue
                for r2 in range(10):
                    for c2 in range(9):
                        if self._legal(r, c, r2, c2):
                            score = 0
                            cap = self.board[r2][c2]
                            if cap:
                                score = {"K": 1000, "R": 50, "C": 40, "N": 30, "M": 20, "G": 20, "P": 10}.get(cap[1], 5)
                            moves.append((score, r, c, r2, c2))
        if not moves:
            return
        moves.sort(reverse=True)
        top = [m for m in moves if m[0] == moves[0][0]][:5] or moves[:5]
        _, r, c, r2, c2 = random.choice(top)
        cap = self.board[r2][c2]
        self.board[r2][c2] = self.board[r][c]
        self.board[r][c] = None
        self._draw()
        if cap and cap[1] == "K":
            self._end(False)

    def _hint_move(self) -> None:
        if not self.is_admin or not self.alive:
            return
        best = None
        best_s = -1
        for r in range(10):
            for c in range(9):
                p = self.board[r][c]
                if not p or p[0] != "R":
                    continue
                for r2 in range(10):
                    for c2 in range(9):
                        if self._legal(r, c, r2, c2):
                            s = 0
                            cap = self.board[r2][c2]
                            if cap:
                                s = {"K": 1000, "R": 50, "C": 40, "N": 30, "M": 20, "G": 20, "P": 10}.get(cap[1], 5)
                            if s > best_s:
                                best_s = s
                                best = (r2, c2)
        if best:
            self._hint = best
            self._draw()
            self.lbl.config(text=f"💡 Gợi ý tới ô ({best[0]+1},{best[1]+1})", fg=GOLD)

    def _end(self, red_win: bool) -> None:
        self.alive = False
        bet = self._round_bet
        if red_win:
            self.profile.add_points(bet)
            self.profile.record_game("cotuong", "win", bet, bet, "ăn tướng")
            self.lbl.config(text=f"Thắng! +{bet}", fg=SUCCESS)
            self.confetti.burst()
            beep("win")
        else:
            self.profile.add_points(-bet)
            self.profile.record_game("cotuong", "lose", bet, -bet, "mất tướng")
            self.lbl.config(text=f"Thua · {-bet}", fg=DANGER)
            beep("lose")
        if self.on_points_change:
            self.on_points_change()


# ═══════════════════════════════════════════════════════════════════════
# CỜ VUA — đủ quân
# ═══════════════════════════════════════════════════════════════════════

CHESS_START = [
    list("rnbqkbnr"),
    list("pppppppp"),
    list("........"),
    list("........"),
    list("........"),
    list("........"),
    list("PPPPPPPP"),
    list("RNBQKBNR"),
]
# upper = white (player), lower = black (AI)
CHESS_SYM = {
    "K": "♔", "Q": "♕", "R": "♖", "B": "♗", "N": "♘", "P": "♙",
    "k": "♚", "q": "♛", "r": "♜", "b": "♝", "n": "♞", "p": "♟",
}


class ChessView(tk.Frame):
    def __init__(self, parent, profile, *, is_host=True, is_admin=False, on_points_change=None, **kw):
        super().__init__(parent, bg=BG, **kw)
        self.profile = profile
        self.is_admin = is_admin
        self.on_points_change = on_points_change
        self.theme = dict(GAME_THEMES["classic"])
        self.sel = None
        self.alive = True
        self._round_bet = 0
        self._hint = None
        self._build()
        self._reset()

    def _build(self) -> None:
        tk.Label(self, text="♛ CỜ VUA (đủ quân)", font=("Segoe UI", 9, "bold"), fg=ACCENT, bg=BG).pack(anchor="w")
        tk.Label(self, text="Bạn = Trắng. Ăn vua = thắng. Luật rút gọn (không nhập thành/phong cấp phức tạp).", font=("Segoe UI", 6), fg=MUTED, bg=BG).pack(anchor="w")
        GameThemeBar(self, self._apply_theme).pack(fill=tk.X)
        self.bet = BetBar(self, lambda: self.profile.points)
        self.bet.pack(fill=tk.X, pady=2)
        self.cv = tk.Canvas(self, width=360, height=360, bg="#111", highlightthickness=0)
        self.cv.pack(pady=4)
        self.cv.bind("<Button-1>", self._click)
        bar = tk.Frame(self, bg=BG)
        bar.pack()
        tk.Button(bar, text="Ván mới", font=("Segoe UI", 8), bg=CARD, fg=TEXT, bd=0, command=self._reset, cursor="hand2").pack(side=tk.LEFT, padx=2)
        if self.is_admin:
            tk.Button(bar, text="💡 Gợi ý (Admin)", font=("Segoe UI", 8, "bold"), bg="#2a2040", fg=GOLD, bd=0,
                      command=self._hint_move, cursor="hand2").pack(side=tk.LEFT, padx=4)
        self.lbl = tk.Label(self, text="", font=("Segoe UI", 8), fg=MUTED, bg=BG)
        self.lbl.pack()
        self.confetti = ConfettiCanvas(self, width=200, height=28, bg=BG)
        self.confetti.pack()

    def _apply_theme(self, th: dict) -> None:
        self.theme = dict(th)
        self._draw()

    def _reset(self) -> None:
        self.board = [row[:] for row in CHESS_START]
        self.sel = None
        self.alive = True
        self._round_bet = 0
        self._hint = None
        self._draw()
        self.lbl.config(text="Đặt cược · chọn quân trắng", fg=MUTED)

    def _draw(self) -> None:
        self.cv.delete("all")
        th = self.theme
        cs = 45
        for r in range(8):
            for c in range(8):
                x0, y0 = c * cs, r * cs
                fill = th["board_a"] if (r + c) % 2 == 0 else th["board_b"]
                if self.sel == (r, c) or self._hint == (r, c):
                    fill = "#baca44" if self._hint == (r, c) else "#f6f669"
                self.cv.create_rectangle(x0, y0, x0 + cs, y0 + cs, fill=fill, outline="")
                p = self.board[r][c]
                if p != ".":
                    self.cv.create_text(x0 + cs / 2, y0 + cs / 2, text=CHESS_SYM.get(p, p), font=("Segoe UI", 22))

    def _click(self, e) -> None:
        if not self.alive:
            return
        cs = 45
        c, r = e.x // cs, e.y // cs
        if not (0 <= r < 8 and 0 <= c < 8):
            return
        if self._round_bet <= 0:
            bet = self.bet.value()
            if bet <= 0:
                messagebox.showinfo("Cờ vua", "Chọn cược trước", parent=self)
                return
            self._round_bet = bet
        p = self.board[r][c]
        if self.sel is None:
            if p != "." and p.isupper():
                self.sel = (r, c)
                self._draw()
            return
        sr, sc = self.sel
        if (sr, sc) == (r, c):
            self.sel = None
            self._draw()
            return
        if self._legal(sr, sc, r, c):
            cap = self.board[r][c]
            self.board[r][c] = self.board[sr][sc]
            self.board[sr][sc] = "."
            # pawn promote
            if self.board[r][c] == "P" and r == 0:
                self.board[r][c] = "Q"
            self.sel = None
            self._hint = None
            self._draw()
            beep("click")
            if cap == "k":
                self._end(True)
                return
            self.after(200, self._ai)
        else:
            if p != "." and p.isupper():
                self.sel = (r, c)
            else:
                self.sel = None
            self._draw()

    def _legal(self, r0, c0, r1, c1) -> bool:
        p = self.board[r0][c0]
        if p == ".":
            return False
        t = self.board[r1][c1]
        if t != "." and t.isupper() == p.isupper():
            return False
        dr, dc = r1 - r0, c1 - c0
        adr, adc = abs(dr), abs(dc)
        pl = p.lower()

        def clear():
            if dr == 0:
                step = 1 if dc > 0 else -1
                return all(self.board[r0][c] == "." for c in range(c0 + step, c1, step))
            if dc == 0:
                step = 1 if dr > 0 else -1
                return all(self.board[r][c0] == "." for r in range(r0 + step, r1, step))
            if adr == adc:
                rs = 1 if dr > 0 else -1
                cs = 1 if dc > 0 else -1
                r, c = r0 + rs, c0 + cs
                while (r, c) != (r1, c1):
                    if self.board[r][c] != ".":
                        return False
                    r += rs
                    c += cs
                return True
            return False

        if pl == "p":
            fwd = -1 if p.isupper() else 1
            start = 6 if p.isupper() else 1
            if dc == 0 and dr == fwd and t == ".":
                return True
            if dc == 0 and dr == 2 * fwd and r0 == start and t == "." and self.board[r0 + fwd][c0] == ".":
                return True
            if adc == 1 and dr == fwd and t != ".":
                return True
            return False
        if pl == "r":
            return (dr == 0 or dc == 0) and clear()
        if pl == "n":
            return (adr, adc) in ((2, 1), (1, 2))
        if pl == "b":
            return adr == adc and clear()
        if pl == "q":
            return ((dr == 0 or dc == 0) or adr == adc) and clear()
        if pl == "k":
            return max(adr, adc) == 1
        return False

    def _ai(self) -> None:
        if not self.alive:
            return
        moves = []
        for r in range(8):
            for c in range(8):
                p = self.board[r][c]
                if p == "." or p.isupper():
                    continue
                for r2 in range(8):
                    for c2 in range(8):
                        if self._legal(r, c, r2, c2):
                            cap = self.board[r2][c2]
                            sc = {"k": 1000, "q": 90, "r": 50, "b": 30, "n": 30, "p": 10}.get(cap.lower() if cap != "." else "", 0)
                            moves.append((sc, r, c, r2, c2))
        if not moves:
            return
        moves.sort(reverse=True)
        _, r, c, r2, c2 = random.choice(moves[: max(1, len(moves) // 4)])
        cap = self.board[r2][c2]
        self.board[r2][c2] = self.board[r][c]
        self.board[r][c] = "."
        if self.board[r2][c2] == "p" and r2 == 7:
            self.board[r2][c2] = "q"
        self._draw()
        if cap == "K":
            self._end(False)

    def _hint_move(self) -> None:
        if not self.is_admin or not self.alive:
            return
        best, bs = None, -1
        for r in range(8):
            for c in range(8):
                p = self.board[r][c]
                if p == "." or not p.isupper():
                    continue
                for r2 in range(8):
                    for c2 in range(8):
                        if self._legal(r, c, r2, c2):
                            cap = self.board[r2][c2]
                            sc = {"k": 1000, "q": 90, "r": 50, "b": 30, "n": 30, "p": 10}.get(cap.lower() if cap != "." else "", 1)
                            if sc > bs:
                                bs, best = sc, (r2, c2)
        if best:
            self._hint = best
            self._draw()
            self.lbl.config(text=f"💡 Gợi ý ô {chr(97+best[1])}{8-best[0]}", fg=GOLD)

    def _end(self, white_win: bool) -> None:
        self.alive = False
        bet = self._round_bet
        if white_win:
            self.profile.add_points(bet)
            self.profile.record_game("chess", "win", bet, bet, "chiếu hết")
            self.lbl.config(text=f"Thắng! +{bet}", fg=SUCCESS)
            self.confetti.burst()
            beep("win")
        else:
            self.profile.add_points(-bet)
            self.profile.record_game("chess", "lose", bet, -bet, "mất vua")
            self.lbl.config(text=f"Thua · {-bet}", fg=DANGER)
            beep("lose")
        if self.on_points_change:
            self.on_points_change()
