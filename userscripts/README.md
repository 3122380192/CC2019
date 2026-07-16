# Userscript — Ai Là Vua Lì Đòn (EMB V5.7)

Gửi dữ liệu đơn từ **portal.godgroup.com** sang app **CC2019 / ACC2019**.

## Cài đặt

1. Cài extension **Tampermonkey** (Chrome / Edge / Firefox)
2. Dashboard → **+** Create new script
3. Xóa mặc định, dán toàn bộ nội dung [`emb-vua-li-don.user.js`](emb-vua-li-don.user.js)
4. **Ctrl+S** lưu · bật script
5. Mở trang design portal · panel góc phải **▲ Vua Lì Đòn**

## 3 chế độ gửi

| Mode | Khi nào dùng | App cần |
|------|----------------|---------|
| **Clipboard** | Không mở port / firewall chặn | App poll clipboard (`TX_EMB::` + JSON) |
| **WebSocket** (mặc định) | Nhanh, realtime, tải ảnh | App WS `ws://127.0.0.1:5001` |
| **HTTP** | Fallback | App HTTP `http://127.0.0.1:5000/receive` |

Host mặc định khớp `modules/emb_server.py` (`HTTP_PORT=5000`, `WS_PORT=5001`, `CLIP_MARKER=TX_EMB::`).

## Payload gửi mỗi lần bấm TX

```json
{
  "source_url": "...",
  "title": "...",
  "html_fragments": ["<tr>...</tr>"],
  "full_text": "...",
  "image_url": "https://..."
}
```

App parse order id, hiển thị panel EMB, có thể yêu cầu tải ảnh qua WS (`download_image`).

## Gợi ý

- Chạy **CC2019** trước khi gửi đơn (trừ chế độ Clipboard thuần)
- Double-click hàng kết nối trên panel script để sửa host nếu máy khác / port đổi
- Nút **TX** chỉ gắn vào hàng có pattern mã dạng `123-456`
