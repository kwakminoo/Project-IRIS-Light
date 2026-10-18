"""IRIS 4장용 구조도. 흰 종이, 청록 강조."""

from PIL import Image, ImageDraw, ImageFont

OUT = r"c:\Users\kwakm\Desktop\Cusor-Project\Project-IRIS-Light-main\docs\발표\IRIS-구조도.png"
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


def center(draw, text, fnt, y, color, x0=0, x1=W):
    tw, _ = text_size(draw, text, fnt)
    draw.text(((x0 + x1 - tw) / 2, y), text, font=fnt, fill=color)


def card(draw, x, y, w, h):
    draw.rounded_rectangle((x, y, x + w, y + h), radius=18, fill=CARD, outline=LINE, width=3)
    draw.rectangle((x, y, x + w, y + 8), fill=TEAL)


def main():
    img = Image.new("RGB", (W, H), PAPER)
    draw = ImageDraw.Draw(img)
    kicker = font(FONTB, 28)
    title = font(FONTB, 54)
    name = font(FONTB, 48)
    body = font(FONT, 32)
    small = font(FONT, 26)
    port = font(FONTB, 30)

    draw.text((96, 56), "구조", font=kicker, fill=TEAL)
    draw.text((96, 100), "IRIS가 고정하는 자리", font=title, fill=INK)

    card(draw, 360, 210, 1200, 150)
    center(draw, "IRIS", name, 236, INK, 360, 1560)
    center(draw, "세션  ·  권한  ·  스트리밍 화면  ·  시작 프로토콜", body, 300, MUTED, 360, 1560)

    draw.rectangle((958, 360, 962, 410), fill=TEAL)

    card(draw, 510, 410, 900, 130)
    center(draw, "Runtime Gateway", name, 432, INK, 510, 1410)
    center(draw, "어댑터.  세션을 모델과 도구에 잇습니다.", small, 492, MUTED, 510, 1410)

    draw.rectangle((958, 540, 962, 590), fill=TEAL)
    draw.rectangle((620, 588, 1300, 592), fill=TEAL)
    draw.rectangle((618, 588, 622, 630), fill=TEAL)
    draw.rectangle((1298, 588, 1302, 630), fill=TEAL)

    card(draw, 160, 630, 700, 220)
    center(draw, "추론", small, 660, TEAL, 160, 860)
    center(draw, "Ollama", name, 708, INK, 160, 860)
    center(draw, ":11434", port, 778, MUTED, 160, 860)

    card(draw, 1060, 630, 700, 220)
    center(draw, "도구  ·  스킬  ·  MCP", small, 660, TEAL, 1060, 1760)
    center(draw, "Hermes", name, 708, INK, 1060, 1760)
    center(draw, ":8642", port, 778, MUTED, 1060, 1760)

    center(draw, "웹검색, 셸, 파일 입출력은 다시 만들지 않습니다.", body, 900, MUTED)
    img.save(OUT, "PNG")
    print(OUT)


if __name__ == "__main__":
    main()
