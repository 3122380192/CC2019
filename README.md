# CC2019

Hub desktop **Adobe CC 2019 + sản xuất emb/patch/DXF** (tkinter).

Tên repo: **CC2019** · App: ACC2019 v3.6.1

## Tính năng chính

- Tab **Sản xuất**: Patch crop · DXF · Spot W1 · panel EMB (portal)
- Nhận đơn từ portal qua **Tampermonkey** (Clipboard / WebSocket / HTTP)
- Tab **CSV Loki**, **Đóng gói**, **Tiện ích**, Adobe install/open, Game LAN, Chat LAN, Nhạc…
- Theme, snap multi-monitor, backup, thống kê đơn theo ngày

## Chạy nhanh (Python)

Yêu cầu: **Python 3.10+** (Windows), quyền Admin (cài Adobe / system).

```bat
run.bat
```

hoặc:

```bat
pip install -r requirements.txt
python acc2019.py
```

## Build EXE

```bat
build_exe.bat
```

Kết quả: `dist\ACC2019\ACC2019.exe` (copy cả folder `_internal`).

## Userscript Tampermonkey (portal → tool)

File: [`userscripts/emb-vua-li-don.user.js`](userscripts/emb-vua-li-don.user.js)

1. Cài [Tampermonkey](https://www.tampermonkey.net/)
2. Tạo script mới → dán nội dung file trên (hoặc import file)
3. Mở `https://portal.godgroup.com/design/*`
4. Bật app CC2019 (tab Sản xuất) → receiver HTTP **:5000** · WS **:5001** · clipboard marker `TX_EMB::`
5. Chọn chế độ trên panel script: 📋 Clipboard · ⚡ WS · 🌐 HTTP
6. Bấm nút **TX** trên từng dòng đơn

Chi tiết: [`userscripts/README.md`](userscripts/README.md)

## Cấu trúc

```
acc2019.py              # entry + UI shell
acc2019_core.py         # Adobe / patch / DXF / drag-drop
modules/                # tabs, emb, pack, game, …
modules/tabs/           # đăng ký tab (lazy-load)
csv_reader/             # CSV Loki products
userscripts/            # Tampermonkey bridge
patch_crop.py / dxf_convert.py / spot_color_tif.py
build_exe.bat / ACC2019.spec
```

## Lưu ý

- **Không** commit installer Adobe / zip lớn (đã `.gitignore`)
- Config runtime (`acc2019_window.json`, history…) lưu local, không đẩy lên git
- `telegram_config.json` bị ignore (token) — tự tạo local nếu dùng notify

## License

Private / use at your own risk.
