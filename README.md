# CARO ONLINE

Game **caro (gomoku) 15×15** chơi online 1 vs 1 giữa hai điện thoại — chạy được trên
cả **iOS** và **Android** chỉ qua trình duyệt, không cần cài app từ store.

Bàn cờ được thiết kế theo phong cách trang [easycaro.github.io](https://easycaro.github.io/):
nền gỗ kem `#f4f0dc`, lưới đen, quân cờ tròn có bóng đổ và ánh sáng (SVG),
điểm sao trên bàn, chấm đỏ đánh dấu nước đi cuối, đường thắng phát sáng.

```
┌─────────────────────────────────────┐
│  Điện thoại A (iOS/Android)         │
│    Tạo phòng ──────►  Mã: K7QM      │
│                       │             │
│                    Server           │
│      WebSocket + file tĩnh          │
│        (một cổng, Python)           │
│                       │             │
│    Vào phòng ◄────────┘  Mã: K7QM   │
│  Điện thoại B (Android/iOS)         │
└─────────────────────────────────────┘
```

---

## 1. Chạy thử trên máy tính

Yêu cầu: **Python 3.10+** (không cần Node.js).

```bash
cd caro-online
pip install -r requirements.txt
python server.py
```

Mở <http://localhost:8000> — để thử cả hai người, mở **hai cửa sổ ẩn danh** khác nhau.

### Chạy bộ kiểm thử tự động

```bash
python tools/test_game.py     # server phải đang chạy ở cổng 8000
```

34 kiểm tra: tạo/vào phòng, relay nước đi, chặn đánh sai lượt, phát hiện thắng 5 quân,
hòa, bỏ cuộc, mất mạng rồi kết nối lại, chat.

---

## 2. Chơi trên điện thoại (trong cùng mạng Wi-Fi)

1. Cho cả hai máy vào **cùng một Wi-Fi**.
2. Xem IP của máy tính: `ipconfig` → dòng *IPv4 Address* (VD `192.168.1.20`).
3. Chạy server với `HOST` nghe ngoài:

```bash
$env:HOST="0.0.0.0"; $env:PORT="8000"; python server.py
```

4. Trên điện thoại, mở `http://192.168.1.20:8000`.

> **iOS Safari:** nếu không vào được, vào *Cài đặt → Safari → Nâng cao →*
> *Thử nghiệm JavaScript* và bật lại, hoặc dùng Chrome.

---

## 3. Chơi từ xa qua Internet (khuyến nghị)

Cách đơn giản nhất là deploy lên **Render** (có gói miễn phí):

1. Đẩy thư mục `caro-online` lên GitHub.
2. Vào <https://render.com> → **New → Web Service** → chọn repo.
3. Cấu hình:

| Trường | Giá trị |
|---|---|
| Runtime | `Python 3` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `python server.py` |
| Port | Render tự đặt biến `PORT` — server đã đọc sẵn |

4. Deploy xong, chia sẻ `https://<ten-app>.onrender.com` cho bạn chơi.
   Người tạo phòng gửi **mã 4 ký tự**, người kia nhập mã là vào được.

Các lựa chọn thay thế: **Railway**, **Fly.io**, **PythonAnywhere**, hoặc một VPS
mình `python server.py` sau đó trỏ tên miền bằng **Caddy/Nginx + HTTPS**
(bắt buộc HTTPS/WSS nếu muốn cài PWA trên iOS).

> Server giữ phòng **10 phút** nếu không ai ở trong, và chờ người chơi mất mạng
> **90 giây** trước khi xử thua. Nâng các con số này trong `server.py`.

---

## 4. Cài thành app trên điện thoại

Game là **PWA**, có `manifest.json` + `service worker` nên cài được như app thật:

- **Android (Chrome):** vào trang → menu ⋮ → *Thêm vào màn hình chính*.
- **iOS (Safari):** vào trang → nút *Chia sẻ* → *Thêm vào Màn hình chính*.

Sau khi cài, game chạy toàn màn hình, có icon riêng, và chơi lại được khi yếu mạng.

> iOS chỉ cho cài PWA khi trang chạy qua **HTTPS** — vì vậy bắt buộc deploy
> lên internet chứ không thể dùng địa chỉ IP nội bộ.

---

## 5. Cách chơi và tính năng

- Bàn **15×15**, ai tạo được **5 quân liền** theo hàng, cột hoặc đường chéo thì thắng.
- Người tạo phòng đi trước bằng quân **Đen**; ván sau người đi trước luân phiên.
- Có **chấm đỏ** đánh dấu nước đi cuối, **đường thắng phát sáng**.
- **Bỏ cuộc**, **xin hòa**, **đấu lại**.
- **Chat** nhanh với đối phương.
- **Tự kết nối lại** khi sóng yếu — ván đấu và các quân cờ được giữ nguyên.
- **Điểm số** cộng dồn qua các ván.
- Chạm vào ô cờ để đánh (khoảng cách chạm được nới lỏng cho dễ bấm trên điện thoại).

---

## 6. Cấu trúc thư mục

```
caro-online/
├── server.py              # Server: file tĩnh + WebSocket, CÙNG MỘT CỔNG
├── requirements.txt       # Chỉ cần websockets
├── web/
│   ├── index.html         # 2 màn hình: menu + bàn cờ
│   ├── styles.css         # Giao diện mobile-first, hỗ trợ safe-area của iPhone
│   ├── game.js            # Vẽ bàn SVG, kết nối WS, logic ván đấu
│   ├── sw.js              # Service worker (PWA)
│   ├── manifest.json      # Manifest PWA
│   └── icons/             # Icon 192/512 + bản maskable
└── tools/
    ├── make_icons.py      # Tạo lại icon bằng Pillow
    └── test_game.py       # Bộ kiểm thử tự động
```

### Giao thức JSON qua WebSocket

| Client → Server | Server → Client |
|---|---|
| `create`, `join`, `move`, `resign` | `created`, `start`, `reconnected`, `move` |
| `draw_offer`, `draw_response`, `restart` | `resign`, `forfeit`, `draw`, `restart` |
| `chat`, `leave` | `chat`, `opp_disconnected`, `error` |

**Server là nơi quyết định kết quả ván đấu** (nước đi hợp lệ, lượt đi, thắng/bài),
nên client không thể gian lận bằng cách sửa code phía máy.

---

## 7. Muốn mở rộng

- **Chế độ đánh máy (PvE):** thêm AI trong `web/game.js`, không cần đụng server.
- **Xin hòa /_undo:** server đã có sẵn `draw_offer`; muốn thêm `undo` chỉ cần
  bổ sung 1 handler và pop nước đi cuối trong `Room`.
- **Nhiều hơn 2 người / xếp hạng:** chuyển sang lưu phòng trong Redis.
- **Bàn 19×19 hoặc luật "đúng 5 mới thắng":** đổi hằng `SIZE`, `WIN_LEN`
  và logic `find_win` trong `server.py`.
