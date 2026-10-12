"""Tạo icon cho PWA Caro Online.

Chạy:  python tools/make_icons.py
Kết quả: web/icons/icon-192.png, icon-512.png, icon-512-maskable.png, apple-touch-icon.png
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parent.parent / "web" / "icons"

CREAM = (241, 234, 209)
CREAM_DARK = (228, 218, 190)
INK = (43, 36, 24)
BG = (20, 22, 31)


def stone(draw, cx, cy, r, white):
    """Vẽ 1 quân cờ có bóng đổ và ánh sáng."""
    # bóng đổ
    sh = Image.new("RGBA", draw._image.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse(
        (cx - r + 3, cy - r + 6, cx + r + 3, cy + r + 6), fill=(0, 0, 0, 110)
    )
    sh = sh.filter(ImageFilter.GaussianBlur(r * 0.28))
    draw._image.alpha_composite(sh)

    base = (246, 244, 236) if white else (30, 30, 36)
    edge = (190, 185, 168) if white else (5, 5, 7)
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=base, outline=edge, width=2)

    # vùng sáng
    hl = Image.new("RGBA", draw._image.size, (0, 0, 0, 0))
    hd = ImageDraw.Draw(hl)
    hr = int(r * 0.62)
    hx, hy = int(cx - r * 0.28), int(cy - r * 0.30)
    light = (255, 255, 255, 210) if white else (175, 175, 185, 190)
    hd.ellipse((hx - hr, hy - hr, hx + hr, hy + hr), fill=light)
    hl = hl.filter(ImageFilter.GaussianBlur(r * 0.30))
    draw._image.alpha_composite(hl)


def draw_board(img, board_rect, pad):
    """Vẽ nền gỗ + lưới + 3 quân cờ lên img."""
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(board_rect, radius=36, fill=CREAM, outline=CREAM_DARK, width=4)

    x0, y0, x1, y1 = board_rect
    inner = (
        x0 + pad,
        y0 + pad,
        x1 - pad,
        y1 - pad,
    )
    w = inner[2] - inner[0]
    step = w / 4.0

    # lưới 5x5 ô -> 5 đường ngang, 5 đường dọc
    for i in range(5):
        p = inner[0] + i * step
        d.line((p, inner[1], p, inner[3]), fill=INK, width=max(2, w // 110))
        p = inner[1] + i * step
        d.line((inner[0], p, inner[2], p), fill=INK, width=max(2, w // 110))

    # 3 quân cờ theo đường chéo
    r = int(step * 0.40)
    stone(d, int(inner[0] + step), int(inner[1] + step), r, white=False)
    stone(d, int(inner[0] + 2 * step), int(inner[1] + 2 * step), r, white=True)
    stone(d, int(inner[0] + 3 * step), int(inner[1] + 3 * step), r, white=False)


def make_icon(size, maskable=False):
    """Tạo icon vuông.

    maskable: tràn viền, vùng an toàn 80% ở giữa (yêu cầu của Android).
    """
    img = Image.new("RGBA", (size, size), BG + (255,))

    if maskable:
        margin = int(size * 0.08)
        board = (margin, margin, size - margin, size - margin)
        pad = int((size - 2 * margin) * 0.13)
    else:
        margin = int(size * 0.10)
        board = (margin, margin, size - margin, size - margin)
        pad = int((size - 2 * margin) * 0.14)

    draw_board(img, board, pad)
    return img.convert("RGB")


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    make_icon(512).save(OUT / "icon-512.png", "PNG")
    make_icon(192).save(OUT / "icon-192.png", "PNG")
    make_icon(512, maskable=True).save(OUT / "icon-512-maskable.png", "PNG")

    # iOS yêu cầu icon bo tròn góc 22.37% (hình vuông bình thường, không bo sẵn)
    apple = make_icon(180)
    apple.save(OUT / "apple-touch-icon.png", "PNG")

    for f in sorted(OUT.glob("*.png")):
        print(f"{f.name:28} {f.stat().st_size:>8,} bytes")


if __name__ == "__main__":
    main()
