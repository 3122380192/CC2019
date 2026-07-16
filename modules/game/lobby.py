"""Tab Game LAN — lobby, phòng, admin, lịch sử."""

from __future__ import annotations

import socket
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import TYPE_CHECKING

from modules.game.games_impl import GAME_CATALOG
from modules.game.lan_net import RoomClient, RoomHost, discover_rooms, local_ip
from modules.game.live_table import LiveCasinoEngine, ROUND_SEC
from modules.game.profile import ADMIN_PASS, DAILY_BONUS, PlayerProfile
from modules.game.ui_common import BetBar, beep

if TYPE_CHECKING:
    pass

BG, CARD, TEXT, MUTED = "#0c0c14", "#141424", "#e8e8f0", "#82829c"
ACCENT, SUCCESS, DANGER, GOLD, PINK = "#00d2ff", "#00e676", "#ff1744", "#ffd60a", "#ff6bcb"


class GameLobbyPanel:
    def __init__(self, parent: tk.Misc, app) -> None:
        self.parent = parent
        self.app = app
        self.base_dir = getattr(app, "base_dir", ".")
        self.profile = PlayerProfile(self.base_dir)
        self.is_admin = False
        self.host: RoomHost | None = None
        self.client: RoomClient | None = None
        self.live: LiveCasinoEngine | None = None
        self._game_frame: tk.Frame | None = None
        self._current_game_id = ""
        self._rooms: list[dict] = []
        self._live_choice = tk.StringVar(value="tai")
        self._last_live_result = ""
        self._pending_live_bet: dict | None = None

        self.frame = tk.Frame(parent, bg=BG)
        self.frame.pack(fill=tk.BOTH, expand=True)
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(1, weight=1)
        self._build()
        self._tick_daily()
        # Tự chạy sòng live 20s khi mở tool
        self.frame.after(600, self._auto_start_live)

    def _build(self) -> None:
        # ── top bar ──
        top = tk.Frame(self.frame, bg=CARD)
        top.grid(row=0, column=0, sticky="ew")
        tk.Label(top, text="🎮 GAME LAN", font=("Segoe UI", 9, "bold"), fg=PINK, bg=CARD).pack(
            side=tk.LEFT, padx=6, pady=3,
        )
        self.lbl_name = tk.Label(top, text=f"👤 {self.profile.name}", font=("Segoe UI", 8), fg=ACCENT, bg=CARD)
        self.lbl_name.pack(side=tk.LEFT, padx=4)
        self.lbl_pts = tk.Label(top, text="", font=("Consolas", 9, "bold"), fg=GOLD, bg=CARD)
        self.lbl_pts.pack(side=tk.LEFT, padx=6)
        self.lbl_daily = tk.Label(top, text="", font=("Segoe UI", 7), fg=MUTED, bg=CARD)
        self.lbl_daily.pack(side=tk.LEFT)

        tk.Button(
            top, text="✎ Tên", font=("Segoe UI", 7), bg=BG, fg=TEXT, bd=0, padx=4, cursor="hand2",
            command=self._rename,
        ).pack(side=tk.RIGHT, padx=2, pady=2)
        self.btn_admin = tk.Button(
            top, text="🔒", font=("Segoe UI", 8), bg=BG, fg=MUTED, bd=0, padx=5, cursor="hand2",
            command=self._admin_unlock,
        )
        self.btn_admin.pack(side=tk.RIGHT, padx=2)
        tk.Button(
            top, text="📜 LS", font=("Segoe UI", 7), bg=BG, fg=ACCENT, bd=0, padx=4, cursor="hand2",
            command=self._show_history,
        ).pack(side=tk.RIGHT, padx=2)

        self._refresh_header()

        # ── body: left games | right room/play ──
        body = tk.Frame(self.frame, bg=BG)
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        left = tk.Frame(body, bg=CARD, width=150)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 3))
        left.grid_propagate(False)
        tk.Label(left, text="Trò chơi", font=("Segoe UI", 8, "bold"), fg=GOLD, bg=CARD).pack(anchor="w", padx=4, pady=2)
        for gid, title, desc, _cls in GAME_CATALOG:
            b = tk.Button(
                left, text=title, font=("Segoe UI", 8, "bold"), anchor="w",
                bg=BG, fg=TEXT, bd=0, padx=6, pady=4, cursor="hand2",
                command=lambda g=gid: self._open_local_game(g),
            )
            b.pack(fill=tk.X, padx=3, pady=1)
            tk.Label(left, text=desc, font=("Segoe UI", 6), fg=MUTED, bg=CARD, anchor="w").pack(fill=tk.X, padx=8)

        tk.Frame(left, bg="#2a2a3a", height=1).pack(fill=tk.X, pady=6, padx=4)
        tk.Label(left, text="Phòng LAN", font=("Segoe UI", 8, "bold"), fg=ACCENT, bg=CARD).pack(anchor="w", padx=4)
        tk.Button(left, text="📡 Tạo phòng", font=("Segoe UI", 8, "bold"), bg=SUCCESS, fg="#000",
                  bd=0, pady=4, cursor="hand2", command=self._create_room).pack(fill=tk.X, padx=4, pady=2)
        tk.Button(left, text="🔍 Tìm phòng", font=("Segoe UI", 8), bg=BG, fg=ACCENT,
                  bd=0, pady=3, cursor="hand2", command=self._scan_rooms).pack(fill=tk.X, padx=4, pady=1)
        tk.Button(left, text="👁 Vào khán giả", font=("Segoe UI", 7), bg=BG, fg=MUTED,
                  bd=0, pady=2, cursor="hand2", command=lambda: self._join_selected(True)).pack(fill=tk.X, padx=4)
        tk.Button(left, text="🚪 Rời phòng", font=("Segoe UI", 7), bg=BG, fg=DANGER,
                  bd=0, pady=2, cursor="hand2", command=self._leave_room).pack(fill=tk.X, padx=4, pady=2)

        self.room_list = tk.Listbox(
            left, height=5, font=("Consolas", 7), bg=BG, fg=TEXT,
            selectbackground="#1a3a2a", bd=0, highlightthickness=0,
        )
        self.room_list.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)
        self.room_list.bind("<Double-1>", lambda e: self._join_selected(False))

        # right play area
        self.right = tk.Frame(body, bg=BG)
        self.right.grid(row=0, column=1, sticky="nsew")
        self.right.columnconfigure(0, weight=1)
        self.right.rowconfigure(0, weight=1)

        # Live casino panel (default view)
        self.live_panel = tk.Frame(self.right, bg=BG)
        self.live_panel.pack(fill=tk.BOTH, expand=True)
        tk.Label(
            self.live_panel, text="🔴 SÒNG LIVE LAN · chu kỳ 20s",
            font=("Segoe UI", 10, "bold"), fg=PINK, bg=BG,
        ).pack(anchor="w", padx=6, pady=(6, 2))
        self.lbl_live = tk.Label(
            self.live_panel, text="Đang khởi động sòng…",
            font=("Segoe UI", 9), fg=ACCENT, bg=CARD, padx=8, pady=6, anchor="w",
        )
        self.lbl_live.pack(fill=tk.X, padx=6, pady=2)
        self.lbl_live_result = tk.Label(
            self.live_panel, text="—", font=("Consolas", 11, "bold"), fg=GOLD, bg=BG,
        )
        self.lbl_live_result.pack(pady=4)

        ch = tk.Frame(self.live_panel, bg=BG)
        ch.pack(fill=tk.X, padx=6)
        tk.Label(ch, text="Cửa cược live:", font=("Segoe UI", 8), fg=MUTED, bg=BG).pack(side=tk.LEFT)
        for t, v in (("Tài", "tai"), ("Xỉu", "xiu"), ("Chẵn", "chan"), ("Lẻ", "le")):
            tk.Radiobutton(
                ch, text=t, variable=self._live_choice, value=v,
                font=("Segoe UI", 8, "bold"), fg=TEXT, bg=BG, selectcolor=CARD,
            ).pack(side=tk.LEFT, padx=3)
        self.live_bet = BetBar(self.live_panel, lambda: self.profile.points)
        self.live_bet.pack(fill=tk.X, padx=6, pady=4)
        tk.Button(
            self.live_panel, text=f"✔ ĐẶT CƯỢC LIVE ({ROUND_SEC}s/ván)",
            font=("Segoe UI", 9, "bold"), bg=SUCCESS, fg="#000", bd=0, padx=10, pady=5,
            cursor="hand2", command=self._place_live_bet,
        ).pack(pady=4)
        self.lbl_live_hist = tk.Label(
            self.live_panel, text="Lịch sử sòng: …", font=("Consolas", 7),
            fg=MUTED, bg=BG, justify="left", wraplength=400, anchor="w",
        )
        self.lbl_live_hist.pack(fill=tk.X, padx=6, pady=4)
        tk.Label(
            self.live_panel,
            text=f"Solo: chọn game trái · LAN IP {local_ip()} · Daily +{DAILY_BONUS:,}/24h",
            font=("Segoe UI", 7), fg=MUTED, bg=BG,
        ).pack(pady=2)

        # admin strip (hidden)
        self.admin_bar = tk.Frame(self.frame, bg="#1a1020")
        tk.Label(self.admin_bar, text="ADMIN", font=("Segoe UI", 7, "bold"), fg=GOLD, bg="#1a1020").pack(
            side=tk.LEFT, padx=4,
        )
        tk.Button(self.admin_bar, text="+10k mình", font=("Segoe UI", 7), bg=CARD, fg=SUCCESS, bd=0,
                  command=lambda: self._admin_add(10_000), cursor="hand2").pack(side=tk.LEFT, padx=2)
        tk.Button(self.admin_bar, text="+100k mình", font=("Segoe UI", 7), bg=CARD, fg=SUCCESS, bd=0,
                  command=lambda: self._admin_add(100_000), cursor="hand2").pack(side=tk.LEFT, padx=2)
        tk.Button(self.admin_bar, text="Cộng cho người khác…", font=("Segoe UI", 7), bg=CARD, fg=ACCENT, bd=0,
                  command=self._admin_add_other, cursor="hand2").pack(side=tk.LEFT, padx=2)
        tk.Button(self.admin_bar, text="Ép KQ live…", font=("Segoe UI", 7), bg=CARD, fg=DANGER, bd=0,
                  command=self._admin_force_live, cursor="hand2").pack(side=tk.LEFT, padx=2)
        tk.Button(self.admin_bar, text="Set điểm…", font=("Segoe UI", 7), bg=CARD, fg=MUTED, bd=0,
                  command=self._admin_set_pts, cursor="hand2").pack(side=tk.LEFT, padx=2)
        tk.Button(self.admin_bar, text="Reset daily", font=("Segoe UI", 7), bg=CARD, fg=MUTED, bd=0,
                  command=self._admin_reset_daily, cursor="hand2").pack(side=tk.LEFT, padx=2)

    def _refresh_header(self) -> None:
        self.lbl_name.config(text=f"👤 {self.profile.name}")
        self.lbl_pts.config(text=f"💰 {self.profile.points:,}")
        sec = self.profile.seconds_to_daily()
        if sec <= 0:
            self.lbl_daily.config(text="· Daily sẵn sàng — mở lại app để nhận")
        else:
            h, m = sec // 3600, (sec % 3600) // 60
            self.lbl_daily.config(text=f"· Daily sau {h}h{m:02d}m")

    def _tick_daily(self) -> None:
        got = self.profile.claim_daily_if_due()
        if got:
            try:
                self.app.log(f"🎮 Daily +{got:,} điểm!", "success")
            except Exception:
                pass
            messagebox.showinfo("Daily", f"Nhận {got:,} điểm mỗi 24h!", parent=self.frame)
        self._refresh_header()
        self.frame.after(60_000, self._tick_daily)

    def _rename(self) -> None:
        n = simpledialog.askstring("Tên hiển thị", "Tên trong game (mặc định = tên máy):",
                                   initialvalue=self.profile.name, parent=self.frame)
        if n:
            self.profile.name = n
            self._refresh_header()
            beep("click")

    def _admin_unlock(self) -> None:
        if self.is_admin:
            self.is_admin = False
            self.btn_admin.config(text="🔒", fg=MUTED)
            self.admin_bar.grid_forget()
            try:
                self.app.log("Admin đã khóa", "accent")
            except Exception:
                pass
            return
        pw = simpledialog.askstring("Admin", "Nhập mật khẩu:", show="*", parent=self.frame)
        if pw == ADMIN_PASS:
            self.is_admin = True
            self.btn_admin.config(text="🔓 ADMIN", fg=GOLD)
            self.admin_bar.grid(row=2, column=0, sticky="ew")
            beep("win")
            try:
                self.app.log("🔓 Admin mở khóa", "success")
            except Exception:
                pass
        elif pw is not None:
            messagebox.showerror("Admin", "Sai mật khẩu", parent=self.frame)
            beep("lose")

    def _admin_add(self, n: int) -> None:
        if not self.is_admin:
            return
        self.profile.add_points(n, reason="admin")
        self._refresh_header()
        beep("win")

    def _admin_add_other(self) -> None:
        """Cộng điểm cho người chơi khác (broadcast LAN + lịch sử)."""
        if not self.is_admin:
            return
        players = []
        if self.live and self.live.host:
            players = list(self.live.host.state.get("players") or [])
        name = simpledialog.askstring(
            "Cộng điểm người khác",
            "Tên người chơi (đúng tên hiển thị):\n" + (", ".join(players) if players else "(chưa có trong phòng)"),
            parent=self.frame,
        )
        if not name:
            return
        amt = simpledialog.askinteger("Số điểm", f"Cộng bao nhiêu cho {name}?", initialvalue=10000, parent=self.frame)
        if amt is None:
            return
        # nếu là chính mình
        if name.strip().lower() == self.profile.name.lower():
            self.profile.add_points(amt, reason="admin")
            self._refresh_header()
        if self.live:
            self.live.add_points_broadcast(name.strip(), amt)
        # lưu admin log
        self.profile.record_game("admin", "gift", 0, 0, f"+{amt}→{name}")
        beep("win")
        messagebox.showinfo("Admin", f"Đã gửi +{amt:,} cho {name}", parent=self.frame)

    def _admin_force_live(self) -> None:
        if not self.is_admin or not self.live:
            messagebox.showinfo("Admin", "Cần mở khóa admin & sòng live đang chạy", parent=self.frame)
            return
        r = simpledialog.askstring(
            "Ép kết quả live",
            "Nhập KQ:\n  taixiu: tai / xiu\n  xocdia: chan / le\n  baucua: bc:Cá,Cua,Tôm:0,1,2\n"
            "Hoặc để trống = random",
            parent=self.frame,
        )
        self.live.set_force(r.strip() if r else None)
        messagebox.showinfo("Admin", f"Force = {r or 'random (vòng sau)'}", parent=self.frame)

    def _admin_set_pts(self) -> None:
        if not self.is_admin:
            return
        v = simpledialog.askinteger("Set điểm", "Điểm mới:", initialvalue=self.profile.points, parent=self.frame)
        if v is not None:
            self.profile.set_points(v)
            self._refresh_header()

    def _admin_reset_daily(self) -> None:
        if not self.is_admin:
            return
        self.profile.data["last_daily_ts"] = 0
        self.profile.save()
        got = self.profile.claim_daily_if_due()
        self._refresh_header()
        messagebox.showinfo("Daily", f"Reset & nhận +{got:,}", parent=self.frame)

    def _auto_start_live(self) -> None:
        try:
            self.live = LiveCasinoEngine(
                self.profile.name, self.base_dir,
                on_tick=lambda st: self.frame.after(0, lambda: self._on_live_tick(st)),
            )
            rid = self.live.start()
            self.lbl_live.config(
                text=f"Sòng LIVE host · room {rid} · IP {local_ip()} · {ROUND_SEC}s/ván",
            )
            try:
                self.app.log(f"🎮 Sòng live LAN auto · {rid} · {local_ip()}", "success")
            except Exception:
                pass
        except Exception as exc:
            self.lbl_live.config(text=f"Live lỗi: {exc}", fg=DANGER)

    def _on_live_tick(self, state: dict) -> None:
        if state.get("__client_msg__"):
            return
        phase = state.get("phase", "")
        game = state.get("live_game") or state.get("game", "")
        left = state.get("time_left", 0)
        res = state.get("result") or ""
        if phase == "betting":
            self.lbl_live.config(
                text=f"⏳ {game.upper()} · ĐẶT CƯỢC · còn {left}s · players={len(state.get('players') or [])}",
                fg=ACCENT,
            )
        elif phase == "rolling":
            self.lbl_live.config(text=f"🎲 {game} đang lắc…", fg=GOLD)
        elif phase == "result":
            self.lbl_live.config(text=f"✅ KQ {game}: {res}", fg=SUCCESS)
            self.lbl_live_result.config(text=str(res))
            if res and res != self._last_live_result:
                self._last_live_result = res
                self._settle_live_bet(game, res)
            hist = state.get("history") or []
            self.lbl_live_hist.config(text="Lịch sử sòng: " + " · ".join(hist[:12]))
        # apply admin points gift if this client receives
        # (handled via client MSG path when joining)

    def _place_live_bet(self) -> None:
        bet = self.live_bet.value()
        if bet <= 0:
            messagebox.showinfo("Live", "Chọn mức cược / không đủ điểm", parent=self.frame)
            return
        choice = self._live_choice.get()
        self._pending_live_bet = {
            "choice": choice,
            "amount": bet,
            "game": self.live.current_game if self.live else "taixiu",
        }
        # host self-bet
        if self.live and self.live.host:
            def mut(st):
                if st.get("phase") != "betting":
                    return
                st.setdefault("bets", {})[self.profile.name] = {
                    "choice": choice, "amount": bet,
                }
            self.live.host.mutate(mut)
            self.lbl_live.config(text=f"Đã cược {choice} · {bet:,} (live)", fg=GOLD)
            beep("click")
            return
        if self.client:
            self.client.send({
                "type": "LIVE_BET",
                "action": "LIVE_BET",
                "amount": bet,
                "choice": choice,
            })
            self.lbl_live.config(text=f"Đã gửi cược {choice} · {bet:,}", fg=GOLD)
            beep("click")

    def _settle_live_bet(self, game: str, result: str) -> None:
        """Đối chiếu cược pending với KQ sòng."""
        pb = self._pending_live_bet
        if not pb:
            return
        self._pending_live_bet = None
        bet = int(pb.get("amount") or 0)
        choice = str(pb.get("choice") or "")
        if bet <= 0:
            return
        won = False
        r = result.lower()
        if game == "taixiu":
            if r.startswith("bao"):
                delta = 0
                self.profile.record_game("live_taixiu", "hoa", bet, 0, result)
                self._refresh_header()
                return
            won = (choice == "tai" and r.startswith("tai")) or (choice == "xiu" and r.startswith("xiu"))
        elif game == "xocdia":
            won = (choice == "chan" and r.startswith("chan")) or (choice == "le" and r.startswith("le"))
        else:
            # baucua: simple skip detailed unless choice in result
            won = choice.lower() in r
        delta = bet if won else -bet
        self.profile.add_points(delta)
        self.profile.record_game(f"live_{game}", "win" if won else "lose", bet, delta, result[:60])
        self._refresh_header()
        if won:
            beep("win")
        else:
            beep("lose")

    def _show_history(self) -> None:
        win = tk.Toplevel(self.frame)
        win.title("Lịch sử ván chơi")
        win.configure(bg=BG)
        win.geometry("420x360")
        win.attributes("-topmost", True)
        tk.Label(win, text="📜 Lịch sử cược", font=("Segoe UI", 10, "bold"), fg=GOLD, bg=CARD).pack(fill=tk.X)
        cols = ("ts", "game", "result", "bet", "delta", "pts")
        tree = ttk.Treeview(win, columns=cols, show="headings", height=14)
        for c, t, w in (
            ("ts", "Thời gian", 120), ("game", "Game", 70), ("result", "KQ", 50),
            ("bet", "Cược", 50), ("delta", "±", 50), ("pts", "Sau", 60),
        ):
            tree.heading(c, text=t)
            tree.column(c, width=w, anchor="w")
        tree.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        for h in self.profile.history(80):
            tree.insert("", "end", values=(
                h.get("ts", ""), h.get("game", ""), h.get("result", ""),
                h.get("bet", 0), h.get("delta", 0), h.get("points_after", ""),
            ))
        st = self.profile.data.get("stats") or {}
        summary = " | ".join(f"{g}: {v.get('wins',0)}W/{v.get('losses',0)}L" for g, v in st.items()) or "Chưa có"
        tk.Label(win, text=summary, font=("Segoe UI", 7), fg=MUTED, bg=BG).pack(pady=2)

    def _clear_right(self) -> None:
        if self._game_frame:
            self._game_frame.destroy()
            self._game_frame = None
        for w in self.right.winfo_children():
            w.destroy()

    def _open_local_game(self, game_id: str) -> None:
        cls = None
        title = game_id
        for gid, t, _d, c in GAME_CATALOG:
            if gid == game_id:
                cls, title = c, t
                break
        if not cls:
            return
        self._clear_right()
        self._current_game_id = game_id
        wrap = tk.Frame(self.right, bg=BG)
        wrap.pack(fill=tk.BOTH, expand=True)
        self._game_frame = wrap
        # scroll
        canvas = tk.Canvas(wrap, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=canvas.yview)
        inner = tk.Frame(canvas, bg=BG)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        view = cls(
            inner, self.profile,
            is_host=True, is_admin=self.is_admin,
            on_points_change=self._refresh_header,
        )
        view.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)
        beep("click")
        try:
            self.app.log(f"🎮 Mở {title}", "accent")
        except Exception:
            pass

    def _create_room(self) -> None:
        # pick game for room
        names = [f"{t} — {d}" for _g, t, d, _c in GAME_CATALOG]
        # simple chooser
        top = tk.Toplevel(self.frame)
        top.title("Tạo phòng LAN")
        top.configure(bg=BG)
        top.geometry("280x260")
        top.attributes("-topmost", True)
        tk.Label(top, text="Chọn game cho phòng", font=("Segoe UI", 9, "bold"), fg=ACCENT, bg=BG).pack(pady=6)
        lb = tk.Listbox(top, font=("Segoe UI", 9), bg=CARD, fg=TEXT, height=8, bd=0)
        for n in names:
            lb.insert(tk.END, n)
        lb.pack(fill=tk.BOTH, expand=True, padx=8)
        lb.selection_set(0)

        def ok():
            sel = lb.curselection()
            if not sel:
                return
            gid, title, _d, _c = GAME_CATALOG[sel[0]]
            top.destroy()
            self._start_host(gid, title)

        tk.Button(top, text="Tạo phòng", font=("Segoe UI", 9, "bold"), bg=SUCCESS, fg="#000",
                  bd=0, padx=10, pady=4, command=ok, cursor="hand2").pack(pady=6)

    def _start_host(self, game_id: str, title: str) -> None:
        self._leave_room()
        self.host = RoomHost(self.profile.name, game_id, title=f"{title} · {self.profile.name}")
        self.host.start()
        self._open_local_game(game_id)
        try:
            self.app.log(f"📡 Host phòng {self.host.room_id} · {local_ip()}:{54330}", "success")
        except Exception:
            pass
        messagebox.showinfo(
            "Phòng LAN",
            f"Đã tạo phòng!\nID: {self.host.room_id}\nIP: {local_ip()}\nGame: {title}\n\n"
            "Máy khác bấm Tìm phòng → double-click để vào.",
            parent=self.frame,
        )

    def _scan_rooms(self) -> None:
        self.room_list.delete(0, tk.END)
        self.room_list.insert(tk.END, "Đang quét LAN…")
        beep("click")

        def work():
            rooms = discover_rooms(1.8)
            def ui():
                self._rooms = rooms
                self.room_list.delete(0, tk.END)
                if not rooms:
                    self.room_list.insert(tk.END, "(không thấy phòng)")
                    return
                for r in rooms:
                    self.room_list.insert(
                        tk.END,
                        f"{r.get('title','?')[:18]} · {r.get('host_name')} · {r.get('host_ip')} ({r.get('players',0)})",
                    )
            try:
                self.frame.after(0, ui)
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _join_selected(self, spectator: bool) -> None:
        sel = self.room_list.curselection()
        if not sel or not self._rooms:
            messagebox.showinfo("LAN", "Chọn phòng trong danh sách (Tìm phòng trước)", parent=self.frame)
            return
        idx = sel[0]
        if idx >= len(self._rooms):
            return
        room = self._rooms[idx]
        self._leave_room()

        def on_msg(msg):
            if msg.get("type") == "ADMIN_POINTS":
                if str(msg.get("player", "")).lower() == self.profile.name.lower():
                    amt = int(msg.get("amount") or 0)
                    self.profile.add_points(amt)
                    self.frame.after(0, self._refresh_header)
                    try:
                        self.frame.after(0, lambda a=amt: self.app.log(f"🎁 Admin +{a:,}", "success"))
                    except Exception:
                        pass

        self.client = RoomClient(
            room["host_ip"], self.profile.name, spectator=spectator,
            on_state=lambda s: self.frame.after(0, lambda: self._on_room_state(s)),
            on_msg=on_msg,
        )
        if not self.client.connect():
            messagebox.showerror("LAN", "Không kết nối được host", parent=self.frame)
            self.client = None
            return
        gid = room.get("game") or "taixiu"
        if gid == "live_casino":
            # stay on live panel
            self._clear_right()
            self.live_panel = tk.Frame(self.right, bg=BG)
            self.live_panel.pack(fill=tk.BOTH, expand=True)
            self.lbl_live = tk.Label(self.live_panel, text=f"Đã vào sòng @ {room['host_ip']}", fg=ACCENT, bg=CARD)
            self.lbl_live.pack(fill=tk.X, padx=6, pady=6)
            return
        self._open_local_game(gid)
        # mark spectator on game view if possible
        if self._game_frame and spectator:
            for child in self._game_frame.winfo_children():
                # walk to find BaseGameView
                pass
        try:
            self.app.log(f"{'👁' if spectator else '🎮'} Vào phòng {room.get('host_name')} @ {room['host_ip']}", "accent")
        except Exception:
            pass

    def _on_room_state(self, state: dict) -> None:
        # could sync multiplayer later; show chat/players in header
        if state.get("__client_msg__"):
            return
        players = ", ".join(state.get("players") or [])
        self.lbl_daily.config(text=f"· Phòng: {players[:40]}")

    def _leave_room(self) -> None:
        if self.client:
            self.client.close()
            self.client = None
        # không stop live auto-host (sòng luôn chạy); chỉ stop host tay nếu khác live
        if self.host and (not self.live or self.host is not getattr(self.live, "host", None)):
            self.host.stop()
            self.host = None

    def destroy(self) -> None:
        self._leave_room()
        if self.live:
            try:
                self.live.stop()
            except Exception:
                pass
            self.live = None
