"""Tab truy cập nhanh — link theo nhóm sản phẩm (gộp / thu gọn / quản lý)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tkinter as tk
from tkinter import messagebox, simpledialog

COLOR_BG = "#0c0c14"
COLOR_CARD = "#141424"
COLOR_TEXT = "#ffffff"
COLOR_MUTED = "#82829c"
COLOR_ACCENT = "#00d2ff"
COLOR_SUCCESS = "#00e676"
COLOR_DANGER = "#ff6b6b"
COLOR_GOLD = "#fbbf24"

GROUP_COLORS = (
    "#00d2ff", "#a78bfa", "#34d399", "#fbbf24", "#ff6bcb",
    "#38bdf8", "#fb923c", "#4ade80", "#f472b6", "#94a3b8",
)

DEFAULT_GROUPS = [
    {
        "id": "chung",
        "name": "Chung / Portal",
        "color": "#00d2ff",
        "collapsed": False,
        "links": [
            {"name": "GodGroup Portal", "url": "https://portal.godgroup.com/"},
            {"name": "Chest EMB", "url": "https://portal.godgroup.com/embroidery"},
            {"name": "Loki CSV", "url": "https://loki.godgroup.com/"},
        ],
    },
    {
        "id": "congcu",
        "name": "Công cụ",
        "color": "#34d399",
        "collapsed": False,
        "links": [
            {"name": "Wilcom", "url": "https://www.wilcom.com/"},
            {"name": "Google Drive", "url": "https://drive.google.com/"},
            {"name": "Gmail", "url": "https://mail.google.com/"},
        ],
    },
]


def _chrome_paths() -> list[str]:
    return [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]


def open_in_chrome(url: str) -> bool:
    if not url:
        return False
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    for exe in _chrome_paths():
        if os.path.isfile(exe):
            subprocess.Popen([exe, "--new-tab", url], close_fds=True)
            return True
    import webbrowser
    webbrowser.open(url, new=2)
    return True


def _slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return s[:32] or "group"


class QuickLinksPanel:
    def __init__(self, parent: tk.Misc, app, config_path: str) -> None:
        self.parent = parent
        self.app = app
        self.config_path = config_path
        self._groups: list[dict] = []
        self._active_gid: str | None = None  # nhóm đang chọn khi thêm link
        self._sel: tuple[str, int] | None = None  # (group_id, link_index)
        self._load()
        self._build_ui()

    # ── load / save ───────────────────────────────────────────
    def _load(self) -> None:
        if os.path.isfile(self.config_path):
            try:
                with open(self.config_path, encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("groups"):
                    self._groups = self._normalize_groups(data["groups"])
                    return
                # migrate flat links → 1 group
                links = data.get("links") or []
                if links:
                    self._groups = [
                        {
                            "id": "chung",
                            "name": "Chung",
                            "color": COLOR_ACCENT,
                            "collapsed": False,
                            "links": [
                                {"name": x.get("name", "Link"), "url": x.get("url", "")}
                                for x in links if isinstance(x, dict)
                            ],
                        }
                    ]
                    self._save()
                    return
            except (OSError, json.JSONDecodeError):
                pass
        self._groups = [self._copy_group(g) for g in DEFAULT_GROUPS]
        self._save()

    def _normalize_groups(self, raw: list) -> list[dict]:
        out = []
        for i, g in enumerate(raw):
            if not isinstance(g, dict):
                continue
            name = (g.get("name") or f"Nhóm {i + 1}").strip()
            gid = (g.get("id") or _slug(name)).strip()
            color = g.get("color") or GROUP_COLORS[i % len(GROUP_COLORS)]
            links = []
            for lk in g.get("links") or []:
                if isinstance(lk, dict) and (lk.get("url") or lk.get("name")):
                    links.append({
                        "name": (lk.get("name") or "Link").strip(),
                        "url": (lk.get("url") or "").strip(),
                    })
            out.append({
                "id": gid,
                "name": name,
                "color": color,
                "collapsed": bool(g.get("collapsed", False)),
                "links": links,
            })
        return out or [self._copy_group(DEFAULT_GROUPS[0])]

    @staticmethod
    def _copy_group(g: dict) -> dict:
        return {
            "id": g.get("id", "g"),
            "name": g.get("name", "Nhóm"),
            "color": g.get("color", COLOR_ACCENT),
            "collapsed": bool(g.get("collapsed", False)),
            "links": [dict(x) for x in (g.get("links") or [])],
        }

    def _save(self) -> None:
        try:
            parent = os.path.dirname(self.config_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump({"groups": self._groups}, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            if hasattr(self.app, "log"):
                self.app.log(f"Lưu links lỗi: {exc}", "danger")

    def _find_group(self, gid: str) -> dict | None:
        for g in self._groups:
            if g.get("id") == gid:
                return g
        return None

    def _unique_gid(self, base: str) -> str:
        gid = _slug(base)
        used = {g["id"] for g in self._groups}
        if gid not in used:
            return gid
        n = 2
        while f"{gid}-{n}" in used:
            n += 1
        return f"{gid}-{n}"

    # ── UI ────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        toolbar = tk.Frame(self.parent, bg=COLOR_BG)
        toolbar.pack(fill=tk.X, pady=(0, 2))

        for text, cmd, fg in (
            ("+ Nhóm", self._add_group, COLOR_SUCCESS),
            ("+ Link", self._add_link, COLOR_ACCENT),
            ("Sửa", self._edit_selected, COLOR_GOLD),
            ("Xóa", self._delete_selected, COLOR_DANGER),
            ("Mở nhóm", self._open_active_group, COLOR_ACCENT),
            ("Mặc định", self._reset_defaults, COLOR_MUTED),
        ):
            tk.Button(
                toolbar, text=text, font=("Segoe UI", 6, "bold"),
                bg=COLOR_CARD, fg=fg, activebackground=COLOR_CARD,
                bd=0, padx=5, pady=2, cursor="hand2", command=cmd,
            ).pack(side=tk.LEFT, padx=(0, 2))

        tk.Label(
            toolbar, text="Click nhóm = chọn · ▶/▼ thu gọn · RMB link = sửa",
            font=("Segoe UI", 6), fg=COLOR_MUTED, bg=COLOR_BG,
        ).pack(side=tk.RIGHT)

        # scrollable body
        wrap = tk.Frame(self.parent, bg=COLOR_BG)
        wrap.pack(fill=tk.BOTH, expand=True)
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(0, weight=1)

        self._canvas = tk.Canvas(wrap, bg=COLOR_BG, highlightthickness=0, bd=0)
        sb = tk.Scrollbar(wrap, orient=tk.VERTICAL, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._body = tk.Frame(self._canvas, bg=COLOR_BG)
        self._win_id = self._canvas.create_window((0, 0), window=self._body, anchor="nw")
        self._body.bind(
            "<Configure>",
            lambda _e: self._canvas.configure(scrollregion=self._canvas.bbox("all")),
        )
        self._canvas.bind(
            "<Configure>",
            lambda e: self._canvas.itemconfig(self._win_id, width=e.width),
        )

        def _wheel(e):
            self._canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

        self._canvas.bind("<Enter>", lambda _e: self._canvas.bind_all("<MouseWheel>", _wheel))
        self._canvas.bind("<Leave>", lambda _e: self._canvas.unbind_all("<MouseWheel>"))

        if self._groups:
            self._active_gid = self._groups[0]["id"]

        self._refresh()

        tips = tk.Frame(self.parent, bg=COLOR_CARD)
        tips.pack(fill=tk.X, pady=(3, 0))
        tk.Label(
            tips,
            text="Gộp link theo sản phẩm: tạo nhóm «PET», «Napkins»… rồi + Link vào nhóm đang chọn (viền sáng).",
            font=("Segoe UI", 6), fg=COLOR_MUTED, bg=COLOR_CARD, padx=4, pady=3,
            wraplength=420, justify="left",
        ).pack(anchor="w")

    def _refresh(self) -> None:
        for w in self._body.winfo_children():
            w.destroy()
        self._sel = None

        if not self._groups:
            tk.Label(
                self._body, text="Chưa có nhóm — bấm «+ Nhóm»",
                font=("Segoe UI", 8), fg=COLOR_MUTED, bg=COLOR_BG,
            ).pack(pady=20)
            return

        for gi, group in enumerate(self._groups):
            self._render_group(group, gi)

        self._body.update_idletasks()
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _render_group(self, group: dict, gi: int) -> None:
        gid = group["id"]
        color = group.get("color") or GROUP_COLORS[gi % len(GROUP_COLORS)]
        active = gid == self._active_gid
        collapsed = bool(group.get("collapsed"))
        n_links = len(group.get("links") or [])

        # card
        border = color if active else COLOR_CARD
        card = tk.Frame(
            self._body, bg=COLOR_CARD,
            highlightthickness=2 if active else 1,
            highlightbackground=border,
        )
        card.pack(fill=tk.X, padx=2, pady=3)

        # header
        hdr = tk.Frame(card, bg=COLOR_CARD)
        hdr.pack(fill=tk.X)
        arrow = "▶" if collapsed else "▼"
        tk.Button(
            hdr, text=arrow, font=("Segoe UI", 8, "bold"),
            bg=COLOR_CARD, fg=color, bd=0, padx=4, cursor="hand2",
            command=lambda g=gid: self._toggle_collapse(g),
        ).pack(side=tk.LEFT)
        title = f"{group.get('name', 'Nhóm')}  ({n_links})"
        lbl = tk.Label(
            hdr, text=title, font=("Segoe UI", 8, "bold"),
            fg=color, bg=COLOR_CARD, cursor="hand2", anchor="w",
        )
        lbl.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2, pady=4)
        lbl.bind("<Button-1>", lambda _e, g=gid: self._select_group(g))
        hdr.bind("<Button-1>", lambda _e, g=gid: self._select_group(g))

        # header actions
        for text, cmd, fg in (
            ("✎", lambda g=gid: self._rename_group(g), COLOR_MUTED),
            ("↗", lambda g=gid: self._open_group_links(g), COLOR_ACCENT),
            ("＋", lambda g=gid: self._add_link_to(g), COLOR_SUCCESS),
        ):
            tk.Button(
                hdr, text=text, font=("Segoe UI", 8), bg=COLOR_CARD, fg=fg,
                bd=0, padx=4, cursor="hand2", command=cmd,
            ).pack(side=tk.RIGHT)

        if collapsed:
            return

        # links grid
        grid = tk.Frame(card, bg=COLOR_CARD)
        grid.pack(fill=tk.X, padx=4, pady=(0, 4))
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        links = group.get("links") or []
        if not links:
            tk.Label(
                grid, text="  (trống — bấm ＋ hoặc «+ Link»)",
                font=("Segoe UI", 7), fg=COLOR_MUTED, bg=COLOR_CARD, anchor="w",
            ).grid(row=0, column=0, columnspan=2, sticky="w", pady=2)
            return

        cols = 2
        for i, link in enumerate(links):
            r, c = divmod(i, cols)
            name = (link.get("name") or "Link")[:28]
            is_sel = self._sel == (gid, i)
            btn = tk.Button(
                grid, text=name, font=("Segoe UI", 7, "bold"),
                bg="#1a1a28" if is_sel else COLOR_BG,
                fg=COLOR_TEXT,
                activebackground="#1a2a3a",
                activeforeground=color,
                bd=0, padx=4, pady=5,
                cursor="hand2", wraplength=160, justify="center",
                command=lambda u=link.get("url", ""), n=link.get("name", ""): self._open(u, n),
            )
            btn.grid(row=r, column=c, sticky="ew", padx=2, pady=2)
            btn.bind("<Button-3>", lambda e, g=gid, idx=i: self._edit_link(g, idx))
            btn.bind("<Button-1>", lambda e, g=gid, idx=i: self._mark_sel(g, idx), add="+")

    def _mark_sel(self, gid: str, idx: int) -> None:
        self._sel = (gid, idx)
        self._active_gid = gid

    def _select_group(self, gid: str) -> None:
        self._active_gid = gid
        self._sel = None
        self._refresh()

    def _toggle_collapse(self, gid: str) -> None:
        g = self._find_group(gid)
        if not g:
            return
        g["collapsed"] = not bool(g.get("collapsed"))
        self._save()
        self._refresh()

    # ── open ──────────────────────────────────────────────────
    def _open(self, url: str, name: str) -> None:
        if open_in_chrome(url):
            if hasattr(self.app, "log"):
                self.app.log(f"Chrome: {name}", "accent")
        else:
            if hasattr(self.app, "log"):
                self.app.log(f"Không mở được: {name}", "danger")

    def _open_group_links(self, gid: str) -> None:
        g = self._find_group(gid)
        if not g:
            return
        links = g.get("links") or []
        if not links:
            messagebox.showinfo("Nhóm", "Nhóm trống", parent=self.app.root)
            return
        for lk in links:
            open_in_chrome(lk.get("url", ""))
        if hasattr(self.app, "log"):
            self.app.log(f"Chrome: mở {len(links)} link «{g.get('name')}»", "accent")

    def _open_active_group(self) -> None:
        gid = self._active_gid or (self._groups[0]["id"] if self._groups else None)
        if gid:
            self._open_group_links(gid)

    # ── group CRUD ────────────────────────────────────────────
    def _add_group(self) -> None:
        name = simpledialog.askstring(
            "Nhóm mới",
            "Tên nhóm sản phẩm:\nVD: PET · Napkins · Glitter · Portal",
            parent=self.app.root,
        )
        if not name or not name.strip():
            return
        name = name.strip()
        gid = self._unique_gid(name)
        color = GROUP_COLORS[len(self._groups) % len(GROUP_COLORS)]
        self._groups.append({
            "id": gid,
            "name": name,
            "color": color,
            "collapsed": False,
            "links": [],
        })
        self._active_gid = gid
        self._save()
        self._refresh()
        if hasattr(self.app, "log"):
            self.app.log(f"Links: nhóm «{name}»", "success")

    def _rename_group(self, gid: str) -> None:
        g = self._find_group(gid)
        if not g:
            return
        name = simpledialog.askstring(
            "Đổi tên nhóm", "Tên nhóm:",
            initialvalue=g.get("name", ""), parent=self.app.root,
        )
        if name is None or not name.strip():
            return
        g["name"] = name.strip()
        self._save()
        self._refresh()

    def _delete_group(self, gid: str) -> None:
        g = self._find_group(gid)
        if not g:
            return
        if len(self._groups) <= 1:
            messagebox.showwarning("Nhóm", "Phải giữ ít nhất 1 nhóm", parent=self.app.root)
            return
        n = len(g.get("links") or [])
        if not messagebox.askyesno(
            "Xóa nhóm",
            f"Xóa nhóm «{g.get('name')}» và {n} link bên trong?",
            parent=self.app.root,
        ):
            return
        self._groups = [x for x in self._groups if x.get("id") != gid]
        if self._active_gid == gid:
            self._active_gid = self._groups[0]["id"] if self._groups else None
        self._save()
        self._refresh()

    # ── link CRUD ─────────────────────────────────────────────
    def _add_link(self) -> None:
        gid = self._active_gid
        if not gid and self._groups:
            gid = self._groups[0]["id"]
        if not gid:
            messagebox.showinfo("Link", "Tạo nhóm trước", parent=self.app.root)
            return
        self._add_link_to(gid)

    def _add_link_to(self, gid: str) -> None:
        g = self._find_group(gid)
        if not g:
            return
        name = simpledialog.askstring(
            f"Thêm link → {g.get('name')}",
            "Tên nút (sản phẩm / trang):",
            parent=self.app.root,
        )
        if not name:
            return
        url = simpledialog.askstring(
            f"Thêm link → {g.get('name')}",
            "URL:",
            parent=self.app.root,
        )
        if not url:
            return
        g.setdefault("links", []).append({"name": name.strip(), "url": url.strip()})
        g["collapsed"] = False
        self._active_gid = gid
        self._save()
        self._refresh()

    def _edit_link(self, gid: str, idx: int) -> None:
        g = self._find_group(gid)
        if not g:
            return
        links = g.get("links") or []
        if idx < 0 or idx >= len(links):
            return
        link = links[idx]
        name = simpledialog.askstring(
            "Sửa tên", "Tên nút:",
            initialvalue=link.get("name", ""), parent=self.app.root,
        )
        if name is None:
            return
        url = simpledialog.askstring(
            "Sửa URL", "URL:",
            initialvalue=link.get("url", ""), parent=self.app.root,
        )
        if url is None:
            return
        links[idx] = {"name": name.strip(), "url": url.strip()}
        self._save()
        self._refresh()

    def _edit_selected(self) -> None:
        if self._sel:
            self._edit_link(self._sel[0], self._sel[1])
            return
        if self._active_gid:
            self._rename_group(self._active_gid)
            return
        messagebox.showinfo(
            "Sửa",
            "Chọn nhóm (click tiêu đề) để đổi tên,\n"
            "hoặc chuột phải link để sửa link.",
            parent=self.app.root,
        )

    def _delete_selected(self) -> None:
        if self._sel:
            gid, idx = self._sel
            g = self._find_group(gid)
            if not g:
                return
            links = g.get("links") or []
            if 0 <= idx < len(links):
                name = links[idx].get("name", "")
                if messagebox.askyesno("Xóa link", f"Xóa «{name}»?", parent=self.app.root):
                    links.pop(idx)
                    self._sel = None
                    self._save()
                    self._refresh()
            return
        if self._active_gid:
            self._delete_group(self._active_gid)
            return
        messagebox.showinfo(
            "Xóa",
            "Click 1 link rồi Xóa, hoặc chọn nhóm rồi Xóa cả nhóm.",
            parent=self.app.root,
        )

    def _reset_defaults(self) -> None:
        if messagebox.askyesno(
            "Khôi phục",
            "Đặt lại nhóm/link mặc định?\n(Mất nhóm sản phẩm đã tạo)",
            parent=self.app.root,
        ):
            self._groups = [self._copy_group(g) for g in DEFAULT_GROUPS]
            self._active_gid = self._groups[0]["id"]
            self._save()
            self._refresh()
