"""
CARO ONLINE - Server
--------------------
Game caro (gomoku 15x15) online cho 2 người chơi, chạy trên cả iOS và Android
qua trình duyệt. Server vừa phát file tĩnh (web/), vừa xử lý WebSocket trên
CÙNG MỘT CỔNG nên rất dễ deploy (Render / Railway / Fly.io / VPS).

Chạy:
    pip install -r requirements.txt
    python server.py

Biến môi trường:
    PORT   cổng lắng nghe (mặc định 8000)
    HOST   địa chỉ lắng nghe (mặc định 0.0.0.0)
"""

import asyncio
import json
import mimetypes
import os
import random
import sys
import traceback
import uuid
from pathlib import Path
from urllib.parse import unquote, urlparse

import websockets
from websockets.asyncio.server import serve
from websockets.datastructures import Headers
from websockets.http11 import Response

# Console Windows (cp1252) không in được tiếng Việt -> ép UTF-8
for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream and _stream.encoding and _stream.encoding.lower() != "utf-8":
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))

SIZE = 15          # bàn cờ 15x15
WIN_LEN = 5        # thắng khi có 5 quân liền
GRACE_SECONDS = 90  # thời gian chờ đối phương kết nối lại
EMPTY_ROOM_TTL = 600  # dọn phòng trống sau 10 phút

# Bỏ chữ I, O, 0, 1 để tránh nhập nhầm khi gõ mã phòng
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

DIRS = ((1, 0), (0, 1), (1, 1), (1, -1))

# --------------------------------------------------------------------------- #
#  Mô hình dữ liệu
# --------------------------------------------------------------------------- #


class Player:
    def __init__(self, ws, name, token=None):
        self.ws = ws
        self.name = name
        self.token = token or uuid.uuid4().hex
        self.room = None          # Room
        self.color = None         # "black" | "white"

    def send(self, payload):
        """Gửi JSON cho client.

        ws.send() là coroutine nên phải đưa vào vòng lặp sự kiện; hàm này được
        gọi từ nhiều chỗ không phải async nên không thể await trực tiếp.
        """
        ws = self.ws
        if ws is None:
            return
        try:
            task = asyncio.ensure_future(
                ws.send(json.dumps(payload, ensure_ascii=False))
            )
        except Exception:
            return
        # nuốt lỗi khi socket vừa đóng, tránh log "Task exception was never retrieved"
        task.add_done_callback(_ignore_send_error)


def _ignore_send_error(task):
    if not task.cancelled():
        try:
            task.exception()
        except Exception:
            pass


class Room:
    def __init__(self, code):
        self.code = code
        self.players = []         # tối đa 2, players[0] luôn là quân ĐEN
        self.board = [[None] * SIZE for _ in range(SIZE)]
        self.turn = "black"
        self.status = "waiting"   # waiting | playing | over
        self.winner = None        # "black" | "white" | "draw"
        self.win_cells = []
        self.last_move = None     # [x, y]
        self.scores = {"black": 0, "white": 0}
        self.moves = 0
        self.reconnect_task = None
        self.destroyed = False
        self.chat = []            # giữ 20 tin gần nhất

    # ---------- tiện ích ----------

    def opponent_of(self, player):
        for p in self.players:
            if p is not player:
                return p
        return None

    def by_color(self, color):
        for p in self.players:
            if p.color == color:
                return p
        return None

    def broadcast(self, payload, exclude=None):
        for p in list(self.players):
            if p is exclude or p.ws is None:
                continue
            try:
                p.send(payload)
            except Exception:
                pass

    def online_players(self):
        return [p for p in self.players if p.ws is not None]

    def disconnected_players(self):
        return [p for p in self.players if p.ws is None]

    def public_state(self):
        """Trạng thái bàn cờ gửi cho client để đồng bộ."""
        return {
            "board": self.board,
            "turn": self.turn,
            "status": self.status,
            "winner": self.winner,
            "winCells": self.win_cells,
            "lastMove": self.last_move,
            "scores": self.scores,
            "moves": self.moves,
            "players": [
                {"name": p.name, "color": p.color, "online": p.ws is not None}
                for p in self.players
            ],
        }

    # ---------- logic ván đấu ----------

    def place(self, player, x, y):
        """Đánh 1 nước. Trả về dict kết quả để gửi lại client."""
        if self.status != "playing":
            return {"type": "error", "msg": "Ván đấu chưa bắt đầu."}
        if player.color != self.turn:
            return {"type": "error", "msg": "Chưa tới lượt của bạn."}
        if not (0 <= x < SIZE and 0 <= y < SIZE):
            return {"type": "error", "msg": "Nước đi không hợp lệ."}
        if self.board[y][x] is not None:
            return {"type": "error", "msg": "Ô này đã có quân cờ."}

        color = player.color
        self.board[y][x] = color
        self.last_move = [x, y]
        self.moves += 1

        cells = find_win(self.board, x, y, color)
        if cells:
            self.status = "over"
            self.winner = color
            self.win_cells = cells
            self.scores[color] += 1
            return {
                "type": "move",
                "x": x,
                "y": y,
                "color": color,
                "state": self.public_state(),
                "result": {"winner": color, "cells": cells},
            }

        if self.moves >= SIZE * SIZE:
            self.status = "over"
            self.winner = "draw"
            return {
                "type": "move",
                "x": x,
                "y": y,
                "color": color,
                "state": self.public_state(),
                "result": {"winner": "draw"},
            }

        # bàn cờ chưa đủ nên lượt chuyển sang người kia
        self.turn = "white" if color == "black" else "black"
        return {
            "type": "move",
            "x": x,
            "y": y,
            "color": color,
            "state": self.public_state(),
        }

    def reset(self, first_color=None):
        """Ván mới: xoá bàn cờ, đổi người đánh trước (luân phiên)."""
        if first_color is None:
            # người thua / người vừa đánh quân trắng được đánh trước ván sau
            first_color = "white" if self.turn == "black" else "black"
        self.board = [[None] * SIZE for _ in range(SIZE)]
        self.turn = first_color
        self.status = "playing" if len(self.players) == 2 else "waiting"
        self.winner = None
        self.win_cells = []
        self.last_move = None
        self.moves = 0
        return first_color


def find_win(board, x, y, color):
    """Kiểm tra quân vừa đánh có tạo thành 5 liền không.

    Trả về toạ độ 5 quân thắng (hoặc nhiều hơn nếu overline) hoặc None.
    """
    for dx, dy in DIRS:
        cells = [[x, y]]
        for sign in (1, -1):
            nx, ny = x, y
            while True:
                nx += dx * sign
                ny += dy * sign
                if 0 <= nx < SIZE and 0 <= ny < SIZE and board[ny][nx] == color:
                    cells.append([nx, ny])
                else:
                    break
        if len(cells) >= WIN_LEN:
            cells.sort(key=lambda c: (c[1], c[0]))
            return cells
    return None


# --------------------------------------------------------------------------- #
#  Quản lý phòng
# --------------------------------------------------------------------------- #

rooms: dict[str, Room] = {}


def new_room_code():
    for _ in range(500):
        code = "".join(random.choice(CODE_ALPHABET) for _ in range(4))
        if code not in rooms:
            return code
    raise RuntimeError("Hết mã phòng.")


def find_player_by_token(room, token):
    if not token:
        return None
    for p in room.players:
        if p.token == token:
            return p
    return None


def destroy_room(room):
    if room.destroyed:
        return
    room.destroyed = True
    if room.reconnect_task and not room.reconnect_task.done():
        room.reconnect_task.cancel()
    rooms.pop(room.code, None)


async def schedule_removal(room):
    """Hủy phòng sau khi không còn ai trong đó."""
    await asyncio.sleep(EMPTY_ROOM_TTL)
    if room.status == "waiting" and len(room.players) == 0:
        destroy_room(room)


async def handle_player_left(player, voluntary=False):
    room = player.room
    if room is None:
        return
    player.ws = None

    if room.status == "waiting":
        # phòng chờ mà người ta rời đi thì hủy luôn
        room.players = [p for p in room.players if p is not player]
        if room.players:
            room.players[0].send({"type": "waiting", "room": room.code})
            room.players[0].room = room
            asyncio.create_task(schedule_removal(room))
        else:
            destroy_room(room)
        return

    if room.status == "over":
        room.players = [p for p in room.players if p is not player]
        if not room.players:
            destroy_room(room)
        else:
            other = room.players[0]
            other.room = room
            other.send({"type": "opp_left"})
        return

    # --- đang playing ---
    if voluntary:
        # người chơi chủ động bỏ cuộc -> đối phương thắng ngay
        forfeit(room, player)
        return

    # giữ chỗ trong phòng, chờ kết nối lại trong GRACE_SECONDS
    if room.reconnect_task and not room.reconnect_task.done():
        room.reconnect_task.cancel()
    room.reconnect_task = asyncio.create_task(reconnect_timeout(room, player))
    opp = room.opponent_of(player)
    if opp and opp.ws is not None:
        opp.send({"type": "opp_disconnected", "grace": GRACE_SECONDS})


def forfeit(room, loser):
    winner = "white" if loser.color == "black" else "black"
    room.status = "over"
    room.winner = winner
    room.scores[winner] += 1
    if loser in room.players:
        room.players.remove(loser)
    loser.room = None
    room.broadcast({
        "type": "forfeit",
        "winner": winner,
        "loser": loser.color,
        "reason": "Đối phương đã bỏ cuộc.",
        "state": room.public_state(),
    })


async def reconnect_timeout(room, missing):
    """Hết thời gian chờ thì coi như người đó thua."""
    try:
        await asyncio.sleep(GRACE_SECONDS)
    except asyncio.CancelledError:
        return
    if room.destroyed or room.status != "playing":
        return
    if missing.ws is not None:
        return  # đã kết nối lại rồi
    if missing not in room.players:
        return
    forfeit(room, missing)


# --------------------------------------------------------------------------- #
#  Xử lý tin nhắn từ client
# --------------------------------------------------------------------------- #


async def handle_create(player, data):
    name = clean_name(data.get("name"))
    if player.room is not None:
        player.send({"type": "error", "msg": "Bạn đang ở trong một phòng."})
        return
    code = new_room_code()
    room = Room(code)
    player.name = name
    player.color = "black"
    player.room = room
    room.players.append(player)
    rooms[code] = room
    player.send({
        "type": "created",
        "room": code,
        "color": "black",
        "token": player.token,
        "state": room.public_state(),
    })


async def handle_join(player, data):
    code = str(data.get("room", "")).strip().upper()
    token = data.get("token")
    name = clean_name(data.get("name"))

    room = rooms.get(code)
    if room is None:
        player.send({"type": "error", "msg": f"Không tìm thấy phòng {code}."})
        return

    # --- trường hợp kết nối lại (mạng chập chờn, app mở lại...) ---
    existing = find_player_by_token(room, token)
    if existing is not None:
        idx = room.players.index(existing)
        old_ws = existing.ws
        # vô hiệu hóa đối tượng cũ để socket cũ tự đóng không phá ván đấu
        existing.room = None
        existing.ws = None

        player.name = name or existing.name
        player.color = existing.color
        player.token = existing.token
        player.room = room
        room.players[idx] = player

        if old_ws is not None and old_ws is not player.ws:
            try:
                await old_ws.close(4000, "replaced")
            except Exception:
                pass
        if room.reconnect_task and not room.reconnect_task.done():
            room.reconnect_task.cancel()
            room.reconnect_task = None

        opp = room.opponent_of(player)
        if opp is not None and opp.ws is not None:
            opp.send({"type": "opp_reconnected"})
        player.send({
            "type": "reconnected",
            "room": room.code,
            "color": player.color,
            "token": player.token,
            "state": room.public_state(),
        })
        return

    # --- vào phòng lần đầu ---
    if len(room.players) >= 2:
        player.send({"type": "error", "msg": "Phòng đã đủ 2 người."})
        return

    player.name = name
    player.color = "white"
    player.room = room
    room.players.append(player)

    first = room.reset(first_color="black")
    room.status = "playing"

    host = room.players[0]
    payload = {
        "type": "start",
        "room": room.code,
        "first": first,
        "state": room.public_state(),
    }
    host.send(dict(payload, token=host.token, color="black"))
    player.send(dict(payload, token=player.token, color="white"))


async def handle_move(player, data):
    room = player.room
    if room is None:
        return
    try:
        x = int(data["x"])
        y = int(data["y"])
    except (KeyError, TypeError, ValueError):
        return
    result = room.place(player, x, y)
    if result.get("type") == "error":
        player.send(result)
        return
    room.broadcast(result)


async def handle_resign(player, data=None):
    room = player.room
    if room is None or room.status != "playing":
        return
    winner = "white" if player.color == "black" else "black"
    room.status = "over"
    room.winner = winner
    room.scores[winner] += 1
    room.broadcast({
        "type": "resign",
        "by": player.color,
        "winner": winner,
        "state": room.public_state(),
    })


async def handle_draw_offer(player, data=None):
    room = player.room
    if room is None or room.status != "playing":
        return
    opp = room.opponent_of(player)
    if opp is None or opp.ws is None:
        return
    opp.send({"type": "draw_offer", "from": player.color})


async def handle_draw_response(player, accepted):
    room = player.room
    if room is None or room.status != "playing":
        return
    if accepted:
        room.status = "over"
        room.winner = "draw"
        room.broadcast({"type": "draw", "state": room.public_state()})
    else:
        opp = room.opponent_of(player)
        if opp and opp.ws:
            opp.send({"type": "draw_declined"})


async def handle_restart(player, data=None):
    room = player.room
    if room is None:
        return
    # chỉ cho chơi lại khi ván đã kết thúc (hoặc bàn cờ còn trống)
    if room.status == "playing" and room.moves > 0:
        player.send({"type": "error", "msg": "Ván đấu đang diễn ra."})
        return
    opp = room.opponent_of(player)
    if opp is None or opp.ws is None:
        player.send({"type": "error", "msg": "Đối phương chưa ở trong phòng."})
        return
    first = room.reset()
    room.broadcast({
        "type": "restart",
        "first": first,
        "state": room.public_state(),
    })


async def handle_chat(player, data):
    room = player.room
    if room is None:
        return
    text = str(data.get("text", "")).strip()[:200]
    if not text:
        return
    entry = {"name": player.name, "color": player.color, "text": text}
    room.chat.append(entry)
    room.chat = room.chat[-20:]
    room.broadcast({"type": "chat", **entry})


async def handle_leave(player, data=None):
    if player.room is None:
        return
    ws = player.ws
    await handle_player_left(player, voluntary=True)
    player.ws = ws          # socket vẫn sống, cho phép thao tác tiếp
    player.room = None
    player.color = None


def clean_name(raw):
    name = str(raw or "").strip()[:16]
    return name or "Người chơi"


# --------------------------------------------------------------------------- #
#  WebSocket handler
# --------------------------------------------------------------------------- #

HANDLERS = {
    "create": handle_create,
    "join": handle_join,
    "move": handle_move,
    "resign": handle_resign,
    "draw_offer": handle_draw_offer,
    "draw_response": lambda p, d: handle_draw_response(p, bool(d.get("accepted"))),
    "restart": handle_restart,
    "chat": handle_chat,
    "leave": handle_leave,
}


async def ws_handler(ws):
    player = Player(ws, "Người chơi")
    try:
        async for raw in ws:
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(data, dict):
                continue
            handler = HANDLERS.get(data.get("type"))
            if handler is None:
                continue
            try:
                await handler(player, data)
            except Exception:
                traceback.print_exc()
                player.send({"type": "error", "msg": "Có lỗi xảy ra phía server."})
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        await handle_player_left(player, voluntary=False)


# --------------------------------------------------------------------------- #
#  Phân phát file tĩnh (chạy chung cổng với WebSocket)
# --------------------------------------------------------------------------- #

MIME_OVERRIDES = {
    ".webmanifest": "application/manifest+json",
    ".svg": "image/svg+xml",
    ".js": "text/javascript",
    ".json": "application/json",
}


def serve_static(request):
    path = urlparse(request.path).path
    if path in ("", "/"):
        path = "/index.html"

    # chặn directory traversal
    rel = unquote(path).lstrip("/").replace("\\", "/")
    target = (WEB_DIR / rel).resolve()
    if not target.is_file() or not str(target).startswith(str(WEB_DIR.resolve())):
        body = b"404 Not Found"
        return Response(
            404, "Not Found",
            Headers([("Content-Type", "text/plain; charset=utf-8"),
                     ("Content-Length", str(len(body)))]),
            body,
        )

    try:
        body = target.read_bytes()
    except OSError:
        return Response(500, "Internal Server Error", Headers(), b"")

    ext = target.suffix.lower()
    ctype = MIME_OVERRIDES.get(ext) or mimetypes.guess_type(str(target))[0]
    ctype = ctype or "application/octet-stream"
    if ctype.startswith("text/") or ctype in ("application/json", "text/javascript"):
        ctype += "; charset=utf-8"

    cache = "no-cache" if target.name in ("sw.js", "index.html") else "public, max-age=300"
    headers = Headers([
        ("Content-Type", ctype),
        ("Content-Length", str(len(body))),
        ("Cache-Control", cache),
        ("Access-Control-Allow-Origin", "*"),
    ])
    return Response(200, "OK", headers, body)


async def process_request(connection, request):
    # Yêu cầu WebSocket thì trả None để thư viện xử lý handshake
    if "websocket" in request.headers.get("Upgrade", "").lower():
        return None
    return serve_static(request)


# --------------------------------------------------------------------------- #
#  Main
# --------------------------------------------------------------------------- #


async def main():
    if not WEB_DIR.is_dir():
        raise SystemExit(f"Thiếu thư mục web: {WEB_DIR}")

    async with serve(
        ws_handler,
        HOST,
        PORT,
        process_request=process_request,
        ping_interval=20,
        ping_timeout=20,
        max_size=64 * 1024,
    ):
        print(f"CARO ONLINE đang chạy tại http://{HOST}:{PORT}", flush=True)
        print(
            "Mở trên điện thoại (cùng mạng) bằng địa chỉ IP máy tính, "
            "hoặc deploy lên Render/Railway để chơi từ xa.",
            flush=True,
        )
        await asyncio.Future()  # chạy mãi mãi


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nĐã tắt server.")
