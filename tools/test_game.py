"""Kiểm thử tự động server Caro Online.

Chạy:  python tools/test_game.py   (server phải đang chạy ở cổng 8000)

Kiểm tra: tạo phòng, vào phòng, relay nước đi, chặn đánh sai lượt,
thắng 5 quân liền, hòa, bỏ cuộc, kết nối lại.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import websockets

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server import SIZE, find_win

# Console Windows (cp1252) không in được tiếng Việt -> ép UTF-8
for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream and _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

URL = os.environ.get("TEST_URL", "ws://127.0.0.1:8000/ws")

PASS = []
FAIL = []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  -> {extra}" if extra else ""))


class Client:
    """Bọc 1 kết nối WebSocket + hàng đợi tin nhắn."""

    def __init__(self, ws, label):
        self.ws = ws
        self.label = label
        self.inbox = []

    async def send(self, payload):
        await self.ws.send(json.dumps(payload))

    async def recv(self, want=None, timeout=5):
        """Đợi tin nhắn kế tiếp, lọc theo type nếu muốn."""
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout
        while True:
            if self.inbox:
                msg = self.inbox.pop(0)
                if want is None or msg.get("type") == want:
                    return msg
                continue  # không đúng type -> bỏ qua, đợi tin tiếp theo
            left = deadline - loop.time()
            if left <= 0:
                return {"type": "timeout"}
            try:
                raw = await asyncio.wait_for(self.ws.recv(), left)
            except asyncio.TimeoutError:
                return {"type": "timeout"}
            try:
                self.inbox.append(json.loads(raw))
            except json.JSONDecodeError:
                continue

    async def drain(self):
        """Đọc hết tin nhắn đang ùn trong socket."""
        try:
            while True:
                raw = await asyncio.wait_for(self.ws.recv(), 0.3)
                self.inbox.append(json.loads(raw))
        except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
            pass


async def connect(label):
    ws = await websockets.connect(URL, open_timeout=6)
    return Client(ws, label)


async def test_full_game():
    print("\n--- Ván đấu bình thường: 5 quân liền theo hàng ---")
    a = await connect("A")
    b = await connect("B")

    await a.send({"type": "create", "name": "An"})
    created = await a.recv("created")
    check("Tạo phòng nhận được mã", created.get("type") == "created" and len(created.get("room", "")) == 4,
          created.get("room", ""))
    code = created["room"]
    check("Người tạo là quân Đen", created.get("color") == "black")

    await b.send({"type": "join", "room": code, "name": "Binh"})
    start_b = await b.recv("start")
    start_a = await a.recv("start")
    check("Ván đấu bắt đầu khi đủ 2 người", start_b.get("type") == "start")
    check("Người vào sau là quân Trắng", start_b.get("color") == "white")
    check("Cả hai cùng nhận 'start'", start_a.get("type") == "start")

    # --- đánh sai lượt bị chặn ---
    await b.send({"type": "move", "x": 7, "y": 7})
    err = await b.recv("error")
    check("Chặn đánh sai lượt", err.get("type") == "error", err.get("msg", ""))

    # --- đánh trúng ô đã có quân bị chặn ---
    await a.send({"type": "move", "x": 7, "y": 7})
    await a.recv("move")   # broadcast nước của A
    await b.recv("move")   # B thấy nước (7,7)
    await b.send({"type": "move", "x": 9, "y": 9})
    await b.recv("move")
    await a.recv("move")
    await a.send({"type": "move", "x": 7, "y": 7})
    err2 = await a.recv("error")
    check("Chặn đánh vào ô đã có quân", err2.get("type") == "error", err2.get("msg", ""))

    # --- Đen (A) đánh 5 ô liền hàng 0: x = 0,1,2,3,4 ---
    await a.send({"type": "move", "x": 0, "y": 0})
    await a.recv("move")   # broadcast nước của chính A
    await b.recv("move")   # B thấy nước (0,0)

    # (nước của B, nước của A) - B đánh ở hàng 5 nên không cản
    pairs = [((0, 5), (1, 0)), ((2, 5), (2, 0)), ((4, 5), (3, 0))]
    for (bx, by), (ax, ay) in pairs:
        await b.send({"type": "move", "x": bx, "y": by})
        got_b = await b.recv("move")
        got_a = await a.recv("move")
        check(f"Nước của B ({bx},{by}) được relay", got_b.get("x") == bx and got_a.get("x") == bx,
              f"B:{got_b.get('type')} A:{got_a.get('type')}")

        await a.send({"type": "move", "x": ax, "y": ay})
        got_a = await a.recv("move")
        got_b = await b.recv("move")
        check(f"Nước của A ({ax},{ay}) được relay", got_a.get("x") == ax and got_b.get("x") == ax,
              f"A:{got_a.get('type')} B:{got_b.get('type')}")

    # A đánh nốt (4,0) -> đủ 5 quân liền. Nhớ cho B đánh nước lót trước
    # vì vòng lặp trên kết thúc bằng lượt của A.
    await b.send({"type": "move", "x": 6, "y": 5})
    await b.recv("move")
    await a.recv("move")

    await a.send({"type": "move", "x": 4, "y": 0})
    final = await a.recv("move")
    check("Nước cuối báo có kết quả thắng", final.get("result", {}).get("winner") == "black",
          str(final.get("result", {})))
    cells = final.get("result", {}).get("cells", [])
    check("Trả về đúng 5 ô thắng", len(cells) >= 5, str(cells))

    state = final.get("state", {})
    check("Trạng thái chuyển sang 'over'", state.get("status") == "over")
    check("Điểm Đen được cộng", state.get("scores", {}).get("black") == 1)

    # --- chơi lại ---
    await a.send({"type": "restart"})
    rs = await a.recv("restart")
    check("Chơi lại được", rs.get("type") == "restart")
    check("Bàn cờ đã xoá", all(c is None for row in rs["state"]["board"] for c in row))
    check("Lượt chơi luân phiên", rs["state"]["turn"] == "white", rs["state"]["turn"])

    # --- bỏ cuộc ---
    await b.send({"type": "resign"})
    rf = await a.recv("resign")
    check("Bỏ cuộc -> đối phương thắng", rf.get("winner") == "black")

    await a.ws.close()
    await b.ws.close()


async def test_draw():
    print("\n--- Ván đấu hòa ---")
    a = await connect("A")
    b = await connect("B")

    await a.send({"type": "create", "name": "A"})
    code = (await a.recv("created"))["room"]
    await b.send({"type": "join", "room": code, "name": "B"})
    await b.recv("start")
    await a.recv("start")

    await a.send({"type": "draw_offer"})
    offer = await b.recv("draw_offer")
    check("Gửi lời mời hòa", offer.get("type") == "draw_offer")

    await b.send({"type": "draw_response", "accepted": True})
    dr = await a.recv("draw")
    check("Đồng ý hòa", dr.get("type") == "draw" and dr["state"]["winner"] == "draw")

    await a.ws.close()
    await b.ws.close()


async def test_room_errors():
    print("\n--- Lỗi phòng ---")
    a = await connect("A")

    await a.send({"type": "join", "room": "ZZZZ"})
    err = await a.recv("error")
    check("Vào phòng không tồn tại -> báo lỗi", err.get("type") == "error", err.get("msg", ""))

    await a.send({"type": "create", "name": "A"})
    code = (await a.recv("created"))["room"]

    c = await connect("C")
    d = await connect("D")
    await c.send({"type": "join", "room": code, "name": "C"})
    await c.recv("start")
    await d.send({"type": "join", "room": code, "name": "D"})
    err2 = await d.recv("error")
    check("Phòng đủ 2 người -> từ chối người thứ ba", err2.get("type") == "error", err2.get("msg", ""))

    for cl in (a, c, d):
        await cl.ws.close()


async def test_reconnect():
    print("\n--- Mất mạng rồi kết nối lại ---")
    a = await connect("A")
    b = await connect("B")

    await a.send({"type": "create", "name": "A"})
    created = await a.recv("created")
    code, token_a = created["room"], created["token"]

    await b.send({"type": "join", "room": code, "name": "B"})
    await b.recv("start")
    st = await a.recv("start")
    token_a = st.get("token", token_a)

    # A đánh 1 nước rồi "mất mạng"
    await a.send({"type": "move", "x": 7, "y": 7})
    await b.recv("move")
    await a.ws.close()

    disc = await b.recv("opp_disconnected")
    check("Thông báo đối phương mất kết nối", disc.get("type") == "opp_disconnected")
    check("Còn thời gian chờ nối lại", disc.get("grace", 0) > 0)

    # A quay lại bằng token cũ
    a2 = await connect("A2")
    await a2.send({"type": "join", "room": code, "token": token_a, "name": "A"})
    rc = await a2.recv("reconnected")
    check("Kết nối lại thành công", rc.get("type") == "reconnected")
    check("Giữ nguyên màu quân Đen", rc.get("color") == "black")

    state = rc.get("state", {})
    check("Bàn cờ được giữ nguyên", state.get("board", [[None]])[7][7] == "black")
    check("Ván đấu vẫn đang playing", state.get("status") == "playing")
    check("Chưa bị xử thua", state.get("winner") is None)

    await a2.ws.close()
    await b.ws.close()


async def test_chat():
    print("\n--- Chat ---")
    a = await connect("A")
    b = await connect("B")
    await a.send({"type": "create", "name": "An"})
    code = (await a.recv("created"))["room"]
    await b.send({"type": "join", "room": code, "name": "Binh"})
    await b.recv("start")
    await a.recv("start")

    await a.send({"type": "chat", "text": "Chào bạn!"})
    msg = await b.recv("chat")
    check("Nhắn tin qua lại", msg.get("text") == "Chào bạn!" and msg.get("name") == "An")
    check("Tin nhắn bị cắt còn 200 ký tự", len(msg.get("text", "")) <= 200)

    await a.ws.close()
    await b.ws.close()


def test_win_directions():
    """Kiểm tra phát hiện thắng mọi hướng, chạy trực tiếp không cần server."""
    print("\n--- Phát hiện thắng mọi hướng (unit) ---")

    def board_with(cells, color="black"):
        b = [[None] * SIZE for _ in range(SIZE)]
        for x, y in cells:
            b[y][x] = color
        return b

    cases = [
        ("Hàng ngang", [(3, 7), (4, 7), (5, 7), (6, 7), (7, 7)], (5, 7), 5),
        ("Cột dọc", [(2, 0), (2, 1), (2, 2), (2, 3), (2, 4)], (2, 2), 5),
        ("Đường chéo chính", [(1, 1), (2, 2), (3, 3), (4, 4), (5, 5)], (3, 3), 5),
        ("Đường chéo phụ", [(5, 1), (4, 2), (3, 3), (2, 4), (1, 5)], (3, 3), 5),
        ("6 quân liền vẫn thắng", [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0), (5, 0)], (5, 0), 6),
        ("Thắng sát biên bàn cờ", [(0, 14), (1, 14), (2, 14), (3, 14), (4, 14)], (0, 14), 5),
    ]
    for name, cells, last, expect in cases:
        got = find_win(board_with(cells), last[0], last[1], "black")
        check(name, got is not None and len(got) == expect, str(got))

    got = find_win(board_with([(0, 0), (1, 0), (2, 0), (3, 0)]), 3, 0, "black")
    check("4 quân liền chưa thắng", got is None)

    # quân trắng xen giữa thì không tính
    b = board_with([(0, 5), (1, 5), (2, 5), (4, 5), (5, 5)])
    b[5][3] = "white"
    check("Bị chặn giữa thì không thắng", find_win(b, 4, 5, "black") is None)


async def main():
    for attempt in range(3):
        try:
            await websockets.connect(URL, open_timeout=3)
            break
        except Exception:
            if attempt == 2:
                print(f"Không kết nối được server tại {URL}.")
                print("Hãy chạy 'python server.py' ở cửa sổ khác trước.")
                sys.exit(1)
            await asyncio.sleep(1)

    test_win_directions()
    await test_full_game()
    await test_draw()
    await test_room_errors()
    await test_reconnect()
    await test_chat()

    print(f"\n{'=' * 50}")
    print(f"PASS: {len(PASS)}   FAIL: {len(FAIL)}")
    if FAIL:
        print("Các kiểm tra FAIL:")
        for name in FAIL:
            print("  -", name)
        sys.exit(1)
    print("Tất cả kiểm tra đều đạt ✔")


if __name__ == "__main__":
    asyncio.run(main())
