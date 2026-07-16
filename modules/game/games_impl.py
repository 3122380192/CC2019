"""Các game LAN — Tài xỉu, Xóc đĩa, Bầu cua, XO, Bắn thuyền, Cờ tướng mini."""

from __future__ import annotations

import random
import tkinter as tk
from tkinter import messagebox
from typing import Callable

from modules.game.ui_common import BET_PRESETS, BetBar, ConfettiCanvas, DiceCanvas, beep

# ── palette ──
BG, CARD, TEXT, MUTED = "#0c0c14", "#141424", "#ffffff", "#82829c"
ACCENT, SUCCESS, DANGER, GOLD = "#00d2ff", "#00e676", "#ff1744", "#ffd60a"

BAUCUA_FACES = ["🐟", "🦀", "🦐", "🦌", "🐓", "🍐"]  # cá, cua, tôm, nai, gà, bầu
BAUCUA_NAMES = ["Cá", "Cua", "Tôm", "Nai", "Gà", "Bầu"]


def _section(parent, title: str) -> tk.Frame:
    f = tk.Frame(parent, bg=BG)
    f.pack(fill=tk.X, pady=(4, 2))
    tk.Label(f, text=title, font=("Segoe UI", 9, "bold"), fg=ACCENT, bg=BG).pack(anchor="w")
    return f


class BaseGameView(tk.Frame):
    def __init__(self, parent, profile, *, is_host: bool, is_admin: bool,
                 on_points_change: Callable | None = None, **kw):
        super().__init__(parent, bg=BG, **kw)
        self.profile = profile
        self.is_host = is_host
        self.is_admin = is_admin
        self.on_points_change = on_points_change
        self.spectator = False

    def _refresh_points_ui(self) -> None:
        if self.on_points_change:
            self.on_points_change()

    def _apply_delta(self, game: str, result: str, bet: int, delta: int, detail: str = "") -> None:
        if delta:
            self.profile.add_points(delta)
        self.profile.record_game(game, result, bet, delta, detail)
        self._refresh_points_ui()
        if delta > 0:
            beep("win")
        elif delta < 0:
            beep("lose")


# ═══════════════════════════════════════════════════════════════════════
# TÀI XỈU
# ═══════════════════════════════════════════════════════════════════════

class TaiXiuView(BaseGameView):
    def __init__(self, parent, profile, **kw):
        super().__init__(parent, profile, **kw)
        self.choice = tk.StringVar(value="tai")
        self._build()

    def _build(self) -> None:
        _section(self, "🎲 TÀI XỈU")
        self.dice = DiceCanvas(self, width=220, height=72, bg="#0a0a12")
        self.dice.pack(pady=6)
        self.dice.show([1, 1, 1])
        self.confetti = ConfettiCanvas(self, width=280, height=40, bg=BG)
        self.confetti.pack(fill=tk.X)

        row = tk.Frame(self, bg=BG)
        row.pack(pady=4)
        for text, val, col in (("TÀI (11–17)", "tai", SUCCESS), ("XỈU (4–10)", "xiu", DANGER)):
            tk.Radiobutton(
                row, text=text, variable=self.choice, value=val,
                font=("Segoe UI", 9, "bold"), fg=col, bg=BG, selectcolor=CARD,
                activebackground=BG, activeforeground=col,
            ).pack(side=tk.LEFT, padx=8)

        self.bet = BetBar(self, lambda: self.profile.points, bg=BG, card=CARD, accent=ACCENT, danger=DANGER)
        self.bet.pack(fill=tk.X, pady=4)

        self.btn = tk.Button(
            self, text="🎲  LẮC XÚC XẮC", font=("Segoe UI", 10, "bold"),
            bg=ACCENT, fg="#000", bd=0, padx=12, pady=6, cursor="hand2",
            command=self._play,
        )
        self.btn.pack(pady=6)
        self.lbl = tk.Label(self, text="Chọn Tài/Xỉu · đặt cược · Lắc!", font=("Segoe UI", 8), fg=MUTED, bg=BG)
        self.lbl.pack()
        self.hist = tk.Label(self, text="", font=("Consolas", 7), fg=MUTED, bg=BG)
        self.hist.pack()
        self._hist: list[str] = []

        if self.is_admin:
            ar = tk.Frame(self, bg=CARD)
            ar.pack(fill=tk.X, pady=4)
            tk.Label(ar, text="Admin ép kết quả:", font=("Segoe UI", 7), fg=GOLD, bg=CARD).pack(side=tk.LEFT, padx=4)
            self.admin_force = tk.StringVar(value="")
            for t, v in (("Random", ""), ("Ép TÀI", "tai"), ("Ép XỈU", "xiu")):
                tk.Radiobutton(ar, text=t, variable=self.admin_force, value=v, font=("Segoe UI", 7),
                               fg=TEXT, bg=CARD, selectcolor=BG).pack(side=tk.LEFT)

    def _play(self) -> None:
        if self.spectator:
            return
        bet = self.bet.value()
        if bet <= 0:
            messagebox.showinfo("Cược", "Không đủ điểm hoặc chưa chọn mức cược", parent=self)
            return
        self.btn.config(state=tk.DISABLED)
        force = getattr(self, "admin_force", None)
        force_v = force.get() if force else ""

        def finish(vals):
            total = sum(vals)
            is_tai = total >= 11
            # admin force: re-roll until match (visual already done — adjust display)
            if force_v in ("tai", "xiu"):
                want_tai = force_v == "tai"
                while (total >= 11) != want_tai:
                    vals = [random.randint(1, 6) for _ in range(3)]
                    total = sum(vals)
                is_tai = total >= 11
                self.dice.show(vals)
            win_choice = "tai" if is_tai else "xiu"
            won = self.choice.get() == win_choice
            # Hoa 3 đồng nhất: hoàn cược
            if len(set(vals)) == 1:
                delta = 0
                res = "Hòa (bão)"
            elif won:
                delta = bet
                res = "THẮNG"
                self.confetti.burst()
            else:
                delta = -bet
                res = "THUA"
            if delta:
                self.profile.add_points(delta)
            self.profile.record_game("taixiu", res, bet, delta, f"{vals}={total}")
            self._refresh_points_ui()
            tag = f"{'TÀI' if is_tai else 'XỈU'} {total} · {res} {delta:+d}"
            self.lbl.config(text=tag, fg=SUCCESS if delta > 0 else (MUTED if delta == 0 else DANGER))
            self._hist.insert(0, f"{'T' if is_tai else 'X'}{total}")
            self.hist.config(text=" ".join(self._hist[:12]))
            if delta > 0:
                beep("win")
            elif delta < 0:
                beep("lose")
            self.btn.config(state=tk.NORMAL)

        self.dice.animate([random.randint(1, 6) for _ in range(3)], 1100, on_done=finish)


# ═══════════════════════════════════════════════════════════════════════
# XÓC ĐĨA
# ═══════════════════════════════════════════════════════════════════════

class XocDiaView(BaseGameView):
    """4 đồng — chẵn/lẻ hoặc số đỏ."""

    def __init__(self, parent, profile, **kw):
        super().__init__(parent, profile, **kw)
        self.choice = tk.StringVar(value="chan")
        self._build()

    def _build(self) -> None:
        _section(self, "🪙 XÓC ĐĨA")
        self.cv = tk.Canvas(self, width=200, height=90, bg="#0a0a12", highlightthickness=0)
        self.cv.pack(pady=4)
        self._draw_coins([0, 0, 0, 0])
        row = tk.Frame(self, bg=BG)
        row.pack()
        for t, v, c in (("CHẴN", "chan", SUCCESS), ("LẺ", "le", DANGER),
                        ("4 ĐỎ", "4do", GOLD), ("4 TRẮNG", "4trang", MUTED)):
            tk.Radiobutton(row, text=t, variable=self.choice, value=v, font=("Segoe UI", 8, "bold"),
                           fg=c, bg=BG, selectcolor=CARD).pack(side=tk.LEFT, padx=4)
        self.bet = BetBar(self, lambda: self.profile.points)
        self.bet.pack(fill=tk.X, pady=4)
        self.btn = tk.Button(self, text="🪙  XÓC!", font=("Segoe UI", 10, "bold"),
                             bg=GOLD, fg="#000", bd=0, padx=12, pady=6, cursor="hand2", command=self._play)
        self.btn.pack(pady=4)
        self.lbl = tk.Label(self, text="Chẵn/Lẻ hoặc 4 đỏ/trắng (x10)", font=("Segoe UI", 8), fg=MUTED, bg=BG)
        self.lbl.pack()
        self.confetti = ConfettiCanvas(self, width=240, height=36, bg=BG)
        self.confetti.pack()

    def _draw_coins(self, bits: list[int], shake=False) -> None:
        self.cv.delete("all")
        for i, b in enumerate(bits):
            x = 20 + i * 45 + (random.randint(-3, 3) if shake else 0)
            y = 25 + (random.randint(-3, 3) if shake else 0)
            fill = "#e63946" if b else "#f1faee"
            self.cv.create_oval(x, y, x + 36, y + 36, fill=fill, outline="#333", width=2)

    def _play(self) -> None:
        bet = self.bet.value()
        if bet <= 0:
            return
        self.btn.config(state=tk.DISABLED)
        frames = 18

        def tick(i=0):
            if i < frames:
                self._draw_coins([random.randint(0, 1) for _ in range(4)], shake=True)
                beep("roll")
                self.after(45, lambda: tick(i + 1))
                return
            bits = [random.randint(0, 1) for _ in range(4)]
            if self.is_admin and hasattr(self, "_force"):
                pass
            self._draw_coins(bits)
            red = sum(bits)
            ch = self.choice.get()
            mult = 1
            won = False
            if ch == "chan" and red % 2 == 0:
                won = True
            elif ch == "le" and red % 2 == 1:
                won = True
            elif ch == "4do" and red == 4:
                won, mult = True, 10
            elif ch == "4trang" and red == 0:
                won, mult = True, 10
            delta = bet * mult if won else -bet
            self._apply_delta("xocdia", "win" if won else "lose", bet, delta, f"đỏ={red}")
            self.lbl.config(
                text=f"Đỏ: {red} · {'THẮNG' if won else 'THUA'} {delta:+d}",
                fg=SUCCESS if won else DANGER,
            )
            if won:
                self.confetti.burst()
            self.btn.config(state=tk.NORMAL)

        tick()


# ═══════════════════════════════════════════════════════════════════════
# BẦU CUA
# ═══════════════════════════════════════════════════════════════════════

class BauCuaView(BaseGameView):
    def __init__(self, parent, profile, **kw):
        super().__init__(parent, profile, **kw)
        self.picks: dict[int, tk.IntVar] = {i: tk.IntVar(value=0) for i in range(6)}
        self._build()

    def _build(self) -> None:
        _section(self, "🦀 BẦU CUA TÔM CÁ")
        grid = tk.Frame(self, bg=BG)
        grid.pack(pady=4)
        for i, (emoji, name) in enumerate(zip(BAUCUA_FACES, BAUCUA_NAMES)):
            r, c = divmod(i, 3)
            cell = tk.Frame(grid, bg=CARD, padx=4, pady=4)
            cell.grid(row=r, column=c, padx=3, pady=3)
            tk.Label(cell, text=emoji, font=("Segoe UI", 18), bg=CARD).pack()
            tk.Label(cell, text=name, font=("Segoe UI", 7), fg=MUTED, bg=CARD).pack()
            tk.Spinbox(cell, from_=0, to=20, width=4, textvariable=self.picks[i],
                       font=("Consolas", 8), bg=BG, fg=ACCENT, buttonbackground=CARD).pack()

        self.unit = BetBar(self, lambda: self.profile.points)
        self.unit.pack(fill=tk.X, pady=2)
        tk.Label(self, text="Spin = số unit × mức cược mỗi mặt trúng", font=("Segoe UI", 7), fg=MUTED, bg=BG).pack()

        self.res_lbl = tk.Label(self, text="🎲 🎲 🎲", font=("Segoe UI", 16), bg=BG, fg=TEXT)
        self.res_lbl.pack(pady=4)
        self.btn = tk.Button(self, text="🎲  LẮC BẦU CUA", font=("Segoe UI", 10, "bold"),
                             bg="#e76f51", fg="#fff", bd=0, padx=12, pady=6, cursor="hand2", command=self._play)
        self.btn.pack(pady=4)
        self.lbl = tk.Label(self, text="", font=("Segoe UI", 8), fg=MUTED, bg=BG)
        self.lbl.pack()
        self.confetti = ConfettiCanvas(self, width=240, height=36, bg=BG)
        self.confetti.pack()

    def _play(self) -> None:
        unit = self.unit.value()
        if unit <= 0:
            return
        total_units = sum(v.get() for v in self.picks.values())
        if total_units <= 0:
            messagebox.showinfo("Bầu cua", "Chọn ít nhất 1 unit trên một mặt", parent=self)
            return
        cost = unit * total_units
        if cost > self.profile.points:
            messagebox.showinfo("Bầu cua", f"Cần {cost} điểm (unit×số cược)", parent=self)
            return
        self.btn.config(state=tk.DISABLED)

        def tick(i=0):
            if i < 16:
                self.res_lbl.config(text=" ".join(random.choice(BAUCUA_FACES) for _ in range(3)))
                beep("roll")
                self.after(50, lambda: tick(i + 1))
                return
            faces = [random.randint(0, 5) for _ in range(3)]
            self.res_lbl.config(text=" ".join(BAUCUA_FACES[f] for f in faces))
            # payout: each matching die pays unit * pick
            win = 0
            for f in faces:
                win += unit * self.picks[f].get()
            delta = win - cost
            self._apply_delta("baucua", "win" if delta >= 0 else "lose", cost, delta,
                              ",".join(BAUCUA_NAMES[f] for f in faces))
            self.lbl.config(
                text=f"Cược {cost} · Về {win} · {delta:+d}",
                fg=SUCCESS if delta > 0 else (MUTED if delta == 0 else DANGER),
            )
            if delta > 0:
                self.confetti.burst()
            self.btn.config(state=tk.NORMAL)

        tick()


# ═══════════════════════════════════════════════════════════════════════
# XO
# ═══════════════════════════════════════════════════════════════════════

class XOView(BaseGameView):
    def __init__(self, parent, profile, **kw):
        super().__init__(parent, profile, **kw)
        self.board = [""] * 9
        self.turn = "X"
        self.vs_ai = tk.BooleanVar(value=True)
        self._locked = False
        self._build()

    def _build(self) -> None:
        _section(self, "⭕ XO · CỜ CARO 3×3")
        tk.Checkbutton(self, text="Đấu máy (AI)", variable=self.vs_ai, font=("Segoe UI", 8),
                       fg=TEXT, bg=BG, selectcolor=CARD).pack(anchor="w")
        self.bet = BetBar(self, lambda: self.profile.points)
        self.bet.pack(fill=tk.X, pady=2)
        self.grid = tk.Frame(self, bg=BG)
        self.grid.pack(pady=6)
        self.cells = []
        for i in range(9):
            b = tk.Button(
                self.grid, text="", font=("Segoe UI", 16, "bold"), width=3, height=1,
                bg=CARD, fg=ACCENT, bd=0, cursor="hand2",
                command=lambda idx=i: self._click(idx),
            )
            b.grid(row=i // 3, column=i % 3, padx=2, pady=2)
            self.cells.append(b)
        self.lbl = tk.Label(self, text="Bạn = X · Đặt cược trước khi đánh", font=("Segoe UI", 8), fg=MUTED, bg=BG)
        self.lbl.pack()
        tk.Button(self, text="Ván mới", font=("Segoe UI", 8), bg=CARD, fg=TEXT, bd=0, padx=8, pady=3,
                  cursor="hand2", command=self._reset).pack(pady=4)
        self.confetti = ConfettiCanvas(self, width=200, height=32, bg=BG)
        self.confetti.pack()
        self._round_bet = 0

    def _reset(self) -> None:
        self.board = [""] * 9
        self.turn = "X"
        self._locked = False
        self._round_bet = 0
        for b in self.cells:
            b.config(text="", state=tk.NORMAL, fg=ACCENT)
        self.lbl.config(text="Ván mới — chọn cược rồi đánh", fg=MUTED)

    def _click(self, i: int) -> None:
        if self._locked or self.board[i]:
            return
        if self._round_bet <= 0:
            bet = self.bet.value()
            if bet <= 0:
                messagebox.showinfo("XO", "Chọn mức cược trước", parent=self)
                return
            self._round_bet = bet
        self.board[i] = "X"
        self.cells[i].config(text="X", fg=SUCCESS)
        beep("click")
        if self._check_end():
            return
        if self.vs_ai.get():
            self.after(200, self._ai_move)

    def _ai_move(self) -> None:
        empties = [i for i, v in enumerate(self.board) if not v]
        if not empties:
            return
        # win/block simple
        move = self._smart(empties) if random.random() < 0.85 else random.choice(empties)
        self.board[move] = "O"
        self.cells[move].config(text="O", fg=DANGER)
        self._check_end()

    def _smart(self, empties: list[int]) -> int:
        for who in ("O", "X"):
            for i in empties:
                self.board[i] = who
                if self._winner() == who:
                    self.board[i] = ""
                    return i
                self.board[i] = ""
        for pref in (4, 0, 2, 6, 8, 1, 3, 5, 7):
            if pref in empties:
                return pref
        return empties[0]

    def _winner(self) -> str | None:
        lines = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]
        for a, b, c in lines:
            if self.board[a] and self.board[a] == self.board[b] == self.board[c]:
                return self.board[a]
        if all(self.board):
            return "draw"
        return None

    def _check_end(self) -> bool:
        w = self._winner()
        if not w:
            return False
        self._locked = True
        bet = self._round_bet
        if w == "X":
            self._apply_delta("xo", "win", bet, bet, "X thắng")
            self.lbl.config(text=f"Bạn thắng! +{bet}", fg=SUCCESS)
            self.confetti.burst()
        elif w == "O":
            self._apply_delta("xo", "lose", bet, -bet, "O thắng")
            self.lbl.config(text=f"Thua máy · { -bet}", fg=DANGER)
        else:
            self.lbl.config(text="Hòa — hoàn cược", fg=MUTED)
        return True


# ═══════════════════════════════════════════════════════════════════════
# BẮN THUYỀN (mini 6x6)
# ═══════════════════════════════════════════════════════════════════════

class BattleshipView(BaseGameView):
    def __init__(self, parent, profile, **kw):
        super().__init__(parent, profile, **kw)
        self.size = 6
        self._build()
        self._new_round()

    def _build(self) -> None:
        _section(self, "🚢 BẮN THUYỀN 6×6")
        self.bet = BetBar(self, lambda: self.profile.points)
        self.bet.pack(fill=tk.X, pady=2)
        self.info = tk.Label(self, text="Tìm 3 thuyền (2,3,3 ô). Click ô để bắn!", font=("Segoe UI", 8), fg=MUTED, bg=BG)
        self.info.pack()
        self.grid = tk.Frame(self, bg=BG)
        self.grid.pack(pady=4)
        self.cells = []
        for r in range(self.size):
            row = []
            for c in range(self.size):
                b = tk.Button(
                    self.grid, text="~", width=2, height=1, font=("Consolas", 9),
                    bg="#0a3040", fg=ACCENT, bd=0, cursor="hand2",
                    command=lambda rr=r, cc=c: self._fire(rr, cc),
                )
                b.grid(row=r, column=c, padx=1, pady=1)
                row.append(b)
            self.cells.append(row)
        self.lbl = tk.Label(self, text="", font=("Segoe UI", 8), fg=TEXT, bg=BG)
        self.lbl.pack()
        tk.Button(self, text="Ván mới", font=("Segoe UI", 8), bg=CARD, fg=TEXT, bd=0,
                  command=self._new_round, cursor="hand2").pack(pady=3)
        self.confetti = ConfettiCanvas(self, width=200, height=30, bg=BG)
        self.confetti.pack()

    def _new_round(self) -> None:
        self.ships = set()
        self.hits = set()
        self.misses = set()
        self.shots = 0
        self.alive = True
        self._round_bet = 0
        # place ships: lengths 2,3,3
        for length in (2, 3, 3):
            self._place(length)
        for r in range(self.size):
            for c in range(self.size):
                self.cells[r][c].config(text="~", bg="#0a3040", fg=ACCENT, state=tk.NORMAL)
        self.lbl.config(text="Đặt cược rồi bắn!", fg=MUTED)

    def _place(self, length: int) -> None:
        for _ in range(80):
            horiz = random.choice([True, False])
            if horiz:
                r = random.randint(0, self.size - 1)
                c = random.randint(0, self.size - length)
                cells = {(r, c + i) for i in range(length)}
            else:
                r = random.randint(0, self.size - length)
                c = random.randint(0, self.size - 1)
                cells = {(r + i, c) for i in range(length)}
            if cells & self.ships:
                continue
            self.ships |= cells
            return

    def _fire(self, r: int, c: int) -> None:
        if not self.alive or (r, c) in self.hits or (r, c) in self.misses:
            return
        if self._round_bet <= 0:
            bet = self.bet.value()
            if bet <= 0:
                messagebox.showinfo("Thuyền", "Chọn cược trước", parent=self)
                return
            self._round_bet = bet
        self.shots += 1
        if (r, c) in self.ships:
            self.hits.add((r, c))
            self.cells[r][c].config(text="💥", bg=DANGER, fg="#fff")
            beep("click")
            if self.hits >= self.ships:
                self.alive = False
                # fewer shots = better
                bonus = self._round_bet if self.shots <= 14 else self._round_bet // 2
                self._apply_delta("battleship", "win", self._round_bet, bonus, f"shots={self.shots}")
                self.lbl.config(text=f"Chìm hết! +{bonus} ({self.shots} phát)", fg=SUCCESS)
                self.confetti.burst()
        else:
            self.misses.add((r, c))
            self.cells[r][c].config(text="○", bg="#1a2030", fg=MUTED)
            if self.shots >= 22:
                self.alive = False
                self._apply_delta("battleship", "lose", self._round_bet, -self._round_bet, "hết đạn")
                self.lbl.config(text=f"Hết đạn — thua {-self._round_bet}", fg=DANGER)
                for rr, cc in self.ships - self.hits:
                    self.cells[rr][cc].config(text="▓", bg="#333", fg=GOLD)


# ═══════════════════════════════════════════════════════════════════════
# CỜ TƯỚNG MINI (tướng + 2 tốt mỗi bên, bàn 5x5)
# ═══════════════════════════════════════════════════════════════════════

class CoTuongMiniView(BaseGameView):
    """Mini: Tướng (将/帅) + 2 Tốt. Ăn tướng = thắng. Cược 1 ván."""

    def __init__(self, parent, profile, **kw):
        super().__init__(parent, profile, **kw)
        self.n = 5
        self._build()
        self._reset()

    def _build(self) -> None:
        _section(self, "♟️ CỜ TƯỚNG MINI 5×5")
        tk.Label(self, text="Bạn = Đỏ (帅). Ăn 将 đối phương để thắng.", font=("Segoe UI", 7), fg=MUTED, bg=BG).pack()
        self.bet = BetBar(self, lambda: self.profile.points)
        self.bet.pack(fill=tk.X, pady=2)
        self.board_f = tk.Frame(self, bg="#5c4033")
        self.board_f.pack(pady=6)
        self.btns = []
        for r in range(self.n):
            row = []
            for c in range(self.n):
                b = tk.Button(
                    self.board_f, text="", width=3, height=1, font=("Segoe UI", 12, "bold"),
                    bg="#deb887" if (r + c) % 2 == 0 else "#c4a574",
                    bd=0, cursor="hand2", command=lambda rr=r, cc=c: self._click(rr, cc),
                )
                b.grid(row=r, column=c, padx=1, pady=1)
                row.append(b)
            self.btns.append(row)
        self.lbl = tk.Label(self, text="", font=("Segoe UI", 8), fg=TEXT, bg=BG)
        self.lbl.pack()
        tk.Button(self, text="Ván mới", font=("Segoe UI", 8), bg=CARD, fg=TEXT, bd=0,
                  command=self._reset, cursor="hand2").pack(pady=3)
        self.confetti = ConfettiCanvas(self, width=200, height=30, bg=BG)
        self.confetti.pack()
        self.sel = None
        self._round_bet = 0

    def _reset(self) -> None:
        # board[r][c] = None or (side, kind) side R/B kind G/P
        self.board = [[None] * self.n for _ in range(self.n)]
        self.board[4][2] = ("R", "G")  # red general
        self.board[4][1] = ("R", "P")
        self.board[4][3] = ("R", "P")
        self.board[0][2] = ("B", "G")
        self.board[0][1] = ("B", "P")
        self.board[0][3] = ("B", "P")
        self.turn = "R"
        self.sel = None
        self.alive = True
        self._round_bet = 0
        self._paint()
        self.lbl.config(text="Đặt cược · chọn quân đỏ rồi ô đích", fg=MUTED)

    def _sym(self, p) -> str:
        if not p:
            return ""
        side, kind = p
        if kind == "G":
            return "帅" if side == "R" else "将"
        return "兵" if side == "R" else "卒"

    def _paint(self) -> None:
        for r in range(self.n):
            for c in range(self.n):
                p = self.board[r][c]
                bg = "#deb887" if (r + c) % 2 == 0 else "#c4a574"
                if self.sel == (r, c):
                    bg = "#90ee90"
                fg = DANGER if p and p[0] == "R" else "#1a1a2e"
                self.btns[r][c].config(text=self._sym(p), bg=bg, fg=fg)

    def _click(self, r: int, c: int) -> None:
        if not self.alive:
            return
        if self._round_bet <= 0:
            bet = self.bet.value()
            if bet <= 0:
                messagebox.showinfo("Cờ", "Chọn cược trước", parent=self)
                return
            self._round_bet = bet
        p = self.board[r][c]
        if self.sel is None:
            if p and p[0] == "R":
                self.sel = (r, c)
                self._paint()
            return
        sr, sc = self.sel
        if (sr, sc) == (r, c):
            self.sel = None
            self._paint()
            return
        if self._can_move(sr, sc, r, c):
            captured = self.board[r][c]
            self.board[r][c] = self.board[sr][sc]
            self.board[sr][sc] = None
            self.sel = None
            self._paint()
            beep("click")
            if captured and captured[1] == "G":
                self._end(True)
                return
            self.after(250, self._ai)
        else:
            if p and p[0] == "R":
                self.sel = (r, c)
            else:
                self.sel = None
            self._paint()

    def _can_move(self, r0, c0, r1, c1) -> bool:
        p = self.board[r0][c0]
        if not p:
            return False
        t = self.board[r1][c1]
        if t and t[0] == p[0]:
            return False
        dr, dc = abs(r1 - r0), abs(c1 - c0)
        if p[1] == "G":
            return (dr + dc == 1) and dr <= 1 and dc <= 1
        # pawn: red goes up (decrease r)
        if p[0] == "R":
            return (r1 == r0 - 1 and c1 == c0) or (r1 == r0 and abs(c1 - c0) == 1 and r0 <= 2)
        return (r1 == r0 + 1 and c1 == c0) or (r1 == r0 and abs(c1 - c0) == 1 and r0 >= 2)

    def _ai(self) -> None:
        if not self.alive:
            return
        moves = []
        for r in range(self.n):
            for c in range(self.n):
                p = self.board[r][c]
                if not p or p[0] != "B":
                    continue
                for r2 in range(self.n):
                    for c2 in range(self.n):
                        if self._can_move(r, c, r2, c2):
                            score = 10 if self.board[r2][c2] and self.board[r2][c2][1] == "G" else (
                                5 if self.board[r2][c2] else 0)
                            moves.append((score, r, c, r2, c2))
        if not moves:
            return
        moves.sort(reverse=True)
        # pick best or random among top
        best = [m for m in moves if m[0] == moves[0][0]]
        _, r, c, r2, c2 = random.choice(best)
        captured = self.board[r2][c2]
        self.board[r2][c2] = self.board[r][c]
        self.board[r][c] = None
        self._paint()
        if captured and captured[1] == "G":
            self._end(False)

    def _end(self, red_win: bool) -> None:
        self.alive = False
        bet = self._round_bet
        if red_win:
            self._apply_delta("cotuong", "win", bet, bet, "ăn tướng")
            self.lbl.config(text=f"Thắng! +{bet}", fg=SUCCESS)
            self.confetti.burst()
        else:
            self._apply_delta("cotuong", "lose", bet, -bet, "mất tướng")
            self.lbl.config(text=f"Thua · {-bet}", fg=DANGER)


# ═══════════════════════════════════════════════════════════════════════
# VÒNG QUAY MAY MẮN
# ═══════════════════════════════════════════════════════════════════════

class LuckyWheelView(BaseGameView):
    """Vòng quay: x0 / x1.5 / x2 / x3 / x5 / x10."""

    SEGMENTS = [
        ("x0", 0.0, "#555"),
        ("x1.5", 1.5, "#00d2ff"),
        ("x2", 2.0, "#00e676"),
        ("x0", 0.0, "#333"),
        ("x3", 3.0, "#ffd60a"),
        ("x1.5", 1.5, "#00d2ff"),
        ("x5", 5.0, "#ff6bcb"),
        ("x0", 0.0, "#444"),
        ("x2", 2.0, "#00e676"),
        ("x10", 10.0, "#ff1744"),
        ("x1.5", 1.5, "#00d2ff"),
        ("x0", 0.0, "#222"),
    ]

    def __init__(self, parent, profile, **kw):
        super().__init__(parent, profile, **kw)
        self._angle = 0.0
        self._spinning = False
        self._build()

    def _build(self) -> None:
        _section(self, "🎡 VÒNG QUAY MAY MẮN")
        self.cv = tk.Canvas(self, width=220, height=220, bg="#0a0a12", highlightthickness=0)
        self.cv.pack(pady=4)
        self._draw_wheel(0)
        self.bet = BetBar(self, lambda: self.profile.points)
        self.bet.pack(fill=tk.X, pady=4)
        self.btn = tk.Button(
            self, text="🎡  QUAY!", font=("Segoe UI", 11, "bold"),
            bg="#9b5de5", fg="#fff", bd=0, padx=14, pady=6, cursor="hand2", command=self._spin,
        )
        self.btn.pack(pady=4)
        self.lbl = tk.Label(self, text="Đặt cược · Quay — hệ số nhân điểm", font=("Segoe UI", 8), fg=MUTED, bg=BG)
        self.lbl.pack()
        if self.is_admin:
            fr = tk.Frame(self, bg=CARD)
            fr.pack(fill=tk.X, pady=2)
            tk.Label(fr, text="Admin ép:", font=("Segoe UI", 7), fg=GOLD, bg=CARD).pack(side=tk.LEFT, padx=4)
            self.force_mult = tk.StringVar(value="")
            for t in ("", "x0", "x1.5", "x2", "x3", "x5", "x10"):
                tk.Radiobutton(
                    fr, text=t or "RND", variable=self.force_mult, value=t,
                    font=("Segoe UI", 7), fg=TEXT, bg=CARD, selectcolor=BG,
                ).pack(side=tk.LEFT)
        self.confetti = ConfettiCanvas(self, width=240, height=36, bg=BG)
        self.confetti.pack()

    def _draw_wheel(self, angle_deg: float) -> None:
        self.cv.delete("all")
        import math
        cx, cy, r = 110, 110, 95
        n = len(self.SEGMENTS)
        step = 360 / n
        for i, (lab, _m, col) in enumerate(self.SEGMENTS):
            a0 = math.radians(angle_deg + i * step)
            a1 = math.radians(angle_deg + (i + 1) * step)
            # approximate pie with polygon
            pts = [cx, cy]
            for k in range(12):
                t = a0 + (a1 - a0) * k / 11
                pts.extend([cx + r * math.cos(t), cy + r * math.sin(t)])
            self.cv.create_polygon(pts, fill=col, outline="#111")
            mid = (a0 + a1) / 2
            tx = cx + (r * 0.62) * math.cos(mid)
            ty = cy + (r * 0.62) * math.sin(mid)
            self.cv.create_text(tx, ty, text=lab, fill="#fff", font=("Segoe UI", 7, "bold"))
        # pointer top
        self.cv.create_polygon(cx - 8, 8, cx + 8, 8, cx, 28, fill="#fff", outline="#000")
        self.cv.create_oval(cx - 12, cy - 12, cx + 12, cy + 12, fill="#222", outline=GOLD, width=2)

    def _spin(self) -> None:
        if self._spinning:
            return
        bet = self.bet.value()
        if bet <= 0:
            return
        self._spinning = True
        self.btn.config(state=tk.DISABLED)
        # choose result
        force = getattr(self, "force_mult", None)
        fv = force.get() if force else ""
        if fv:
            idx = next((i for i, s in enumerate(self.SEGMENTS) if s[0] == fv), random.randrange(len(self.SEGMENTS)))
        else:
            # weighted: more x0
            weights = [3 if s[1] == 0 else (2 if s[1] <= 2 else 1) for s in self.SEGMENTS]
            idx = random.choices(range(len(self.SEGMENTS)), weights=weights, k=1)[0]
        n = len(self.SEGMENTS)
        step = 360 / n
        # land pointer at segment center (pointer at top = -90deg in our cos/sin which is right-based)
        # segments drawn from angle_deg; pointer fixed at top (-90°)
        target_center = -90 - (idx + 0.5) * step
        spins = random.randint(4, 7) * 360
        final_angle = spins + target_center
        frames = 55
        start = self._angle

        def tick(i=0):
            if i >= frames:
                self._angle = final_angle % 360
                self._draw_wheel(self._angle)
                lab, mult, _ = self.SEGMENTS[idx]
                if mult <= 0:
                    delta = -bet
                    res = "x0"
                else:
                    win = int(bet * mult)
                    delta = win - bet
                    res = lab
                self._apply_delta("wheel", res, bet, delta, lab)
                self.lbl.config(
                    text=f"Kết quả {lab} · {delta:+d}",
                    fg=SUCCESS if delta > 0 else DANGER,
                )
                if delta > 0:
                    self.confetti.burst()
                self._spinning = False
                self.btn.config(state=tk.NORMAL)
                return
            # ease-out
            t = i / frames
            ease = 1 - (1 - t) ** 3
            ang = start + (final_angle - start) * ease
            self._draw_wheel(ang)
            if i % 3 == 0:
                beep("roll")
            self.after(28, lambda: tick(i + 1))

        tick()


# ═══════════════════════════════════════════════════════════════════════
# SLOT 777
# ═══════════════════════════════════════════════════════════════════════

class Slot777View(BaseGameView):
    SYMBOLS = ["🍒", "🍋", "🔔", "⭐", "7️⃣", "💎"]

    def __init__(self, parent, profile, **kw):
        super().__init__(parent, profile, **kw)
        self._build()

    def _build(self) -> None:
        _section(self, "🎰 SLOT 777")
        self.reels = tk.Label(self, text="❓  ❓  ❓", font=("Segoe UI", 28), bg="#0a0a12", fg=TEXT, width=12)
        self.reels.pack(pady=10, ipady=8)
        self.bet = BetBar(self, lambda: self.profile.points)
        self.bet.pack(fill=tk.X, pady=4)
        self.btn = tk.Button(
            self, text="🎰  QUAY SLOT", font=("Segoe UI", 11, "bold"),
            bg="#f72585", fg="#fff", bd=0, padx=14, pady=6, cursor="hand2", command=self._spin,
        )
        self.btn.pack(pady=4)
        self.lbl = tk.Label(
            self, text="3×7️⃣ = x20 · 3 giống = x5 · 2×7️⃣ = x2",
            font=("Segoe UI", 7), fg=MUTED, bg=BG,
        )
        self.lbl.pack()
        if self.is_admin:
            fr = tk.Frame(self, bg=CARD)
            fr.pack(fill=tk.X, pady=2)
            self.force_jackpot = tk.BooleanVar(value=False)
            tk.Checkbutton(
                fr, text="Admin ép JACKPOT 777", variable=self.force_jackpot,
                font=("Segoe UI", 7), fg=GOLD, bg=CARD, selectcolor=BG,
            ).pack(side=tk.LEFT, padx=4)
        self.confetti = ConfettiCanvas(self, width=240, height=36, bg=BG)
        self.confetti.pack()

    def _spin(self) -> None:
        bet = self.bet.value()
        if bet <= 0:
            return
        self.btn.config(state=tk.DISABLED)
        frames = 20

        def tick(i=0):
            if i < frames:
                s = [random.choice(self.SYMBOLS) for _ in range(3)]
                self.reels.config(text="  ".join(s))
                beep("roll")
                self.after(50, lambda: tick(i + 1))
                return
            if self.is_admin and getattr(self, "force_jackpot", None) and self.force_jackpot.get():
                s = ["7️⃣", "7️⃣", "7️⃣"]
            else:
                # weight 7️⃣ rarer
                pool = self.SYMBOLS[:-1] * 3 + ["7️⃣"]
                s = [random.choice(pool) for _ in range(3)]
            self.reels.config(text="  ".join(s))
            mult = 0
            if s[0] == s[1] == s[2] == "7️⃣":
                mult = 20
            elif s[0] == s[1] == s[2]:
                mult = 5
            elif s.count("7️⃣") >= 2:
                mult = 2
            if mult:
                win = bet * mult
                delta = win - bet
                res = f"x{mult}"
            else:
                delta = -bet
                res = "miss"
            self._apply_delta("slot777", res, bet, delta, "".join(s))
            self.lbl.config(
                text=f"{''.join(s)} · {res} · {delta:+d}",
                fg=SUCCESS if delta > 0 else DANGER,
            )
            if delta > 0:
                self.confetti.burst()
            self.btn.config(state=tk.NORMAL)

        tick()


# ── registry ──
from modules.game.board_games import ChessView, XiangqiView, XOView as XOBoardView

GAME_CATALOG = [
    ("taixiu", "🎲 Tài Xỉu", "Lắc 3 xúc xắc — Tài/Xỉu · live 20s", TaiXiuView),
    ("xocdia", "🪙 Xóc Đĩa", "4 đồng — Chẵn/Lẻ · live 20s", XocDiaView),
    ("baucua", "🦀 Bầu Cua", "6 mặt may rủi · live 20s", BauCuaView),
    ("wheel", "🎡 Vòng Quay", "May mắn nhân điểm", LuckyWheelView),
    ("slot777", "🎰 Slot 777", "3 cuộn · jackpot x20", Slot777View),
    ("xo", "⭕ XO / Caro", "Bàn 3–64 · gợi ý Admin", XOBoardView),
    ("cotuong", "♟️ Cờ Tướng", "Đủ quân 9×10", XiangqiView),
    ("chess", "♛ Cờ Vua", "Đủ quân 8×8", ChessView),
    ("battleship", "🚢 Bắn Thuyền", "Tìm thuyền 6×6", BattleshipView),
]

# Games that run on 20s live cycle when host
LIVE_CYCLE_GAMES = ("taixiu", "xocdia", "baucua")
