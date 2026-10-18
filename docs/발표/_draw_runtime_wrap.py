"""IRIS Runtime이 Ollama와 Hermes를 감싸는 사각형. 흰 종이, 청록 강조."""

from PIL import Image, ImageDraw, ImageFont

OUT = r"c:\Users\kwakm\Desktop\Cusor-Project\Project-IRIS-Light-main\docs\발표\IRIS-RUNTIME.png"
W, H = 1920, 1080
PAPER = (244, 241, 234)
INK = (26, 24, 20)
MUTED = (63, 58, 52)
TEAL = (26, 77, 87)
LINE = (217, 211, 200)
CARD = (255, 252, 247)

FONT = r"C:\Windows\Fonts\malgun.ttf"
FONTB = r"C:\Windows\Fonts\malgunbd.ttf"


def font(path, size):
    return ImageFont.truetype(path, size)


def text_size(draw, text, fnt):
    box = draw.textbbox((0, 0), text, font=fnt)
    return box[2] - box[0], box[3] - box[1]


def center(draw, text, fnt, y, color, x0, x1):
    tw, _ = text_size(draw, text, fnt)
    draw.text(((x0 + x1 - tw) / 2, y), text, font=fnt, fill=color)


def main():
    img = Image.new("RGB", (W, H), PAPER)
    draw = ImageDraw.Draw(img)
    title = font(FONTB, 56)
    sub = font(FONT, 30)
    name = font(FONTB, 48)
    role = font(FONT, 28)
    port = font(FONTB, 32)

    ox, oy, ow, oh = 120, 140, 1680, 800
    draw.rounded_rectangle(
        (ox, oy, ox + ow, oy + oh), radius=28, fill=CARD, outline=TEAL, width=6
    )

    center(draw, "IRIS RUNTIME", title, oy + 48, INK, ox, ox + ow)
    center(
        draw,
        "세션  ·  권한  ·  스트리밍 화면  ·  시작 프로토콜",
        sub,
        oy + 124,
        MUTED,
        ox,
        ox + ow,
    )

    gap = 80
    inner_w, inner_h = 640, 280
    inner_y = oy + 280
    left_x = ox + (ow - inner_w * 2 - gap) // 2
    right_x = left_x + inner_w + gap

    for x, role_text, who, port_text in (
        (left_x, "추론", "Ollama", ":11434"),
        (right_x, "도구  ·  스킬  ·  MCP", "Hermes", ":8642"),
    ):
        draw.rounded_rectangle(
            (x, inner_y, x + inner_w, inner_y + inner_h),
            radius=18,
            fill=PAPER,
            outline=LINE,
            width=3,
        )
        draw.rectangle((x, inner_y, x + inner_w, inner_y + 8), fill=TEAL)
        center(draw, role_text, role, inner_y + 48, TEAL, x, x + inner_w)
        center(draw, who, name, inner_y + 108, INK, x, x + inner_w)
        center(draw, port_text, port, inner_y + 180, MUTED, x, x + inner_w)

    img.save(OUT, "PNG")
    print(OUT)


if __name__ == "__main__":
    main()
