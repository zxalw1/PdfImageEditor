# -*- coding: utf-8 -*-
"""app/assets/app.ico 생성 (16~256px 멀티사이즈)
디자인: 파란 라운드 사각(#2563EB) + 흰 문서(접힌 모서리) + 산·해(사진)
실행: .venv\\Scripts\\python.exe tools\\make_app_icon.py
"""
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "app", "assets", "app.ico")
BLUE, FOLD = (37, 99, 235, 255), (191, 211, 251, 255)
SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]


def draw(px, simple=False):
    k = px / 256 * 4          # 4배 수퍼샘플
    S = int(px * 4)
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    def r(*v):
        return [round(x * k) for x in v]
    d.rounded_rectangle(r(8, 8, 248, 248), radius=round(56 * k), fill=BLUE)
    if simple:   # 16px 등 아주 작은 크기: 문서 여백을 넓혀 단순화
        d.rounded_rectangle(r(66, 44, 190, 212), radius=round(14 * k), fill="white")
        d.polygon(r(146, 44, 190, 44, 190, 88), fill=BLUE)
        d.polygon(r(146, 44, 146, 88, 190, 88), fill=FOLD)
        d.polygon(r(86, 186, 118, 136, 140, 162, 154, 146, 172, 186), fill=BLUE)
    else:
        d.rounded_rectangle(r(70, 52, 186, 206), radius=round(10 * k), fill="white")
        d.polygon(r(146, 52, 186, 52, 186, 92), fill=BLUE)       # 모서리 잘라내기
        d.polygon(r(146, 52, 146, 92, 186, 92), fill=FOLD)       # 접힌 부분
        d.polygon(r(88, 182, 118, 140, 138, 164, 152, 148, 170, 182), fill=BLUE)  # 산
        d.ellipse(r(140, 112, 158, 130), fill=BLUE)              # 해
    return im.resize((px, px), Image.LANCZOS)


def main():
    imgs = [draw(s, simple=s <= 24) for s in SIZES]
    big = imgs[-1]
    big.save(OUT, format="ICO", sizes=[(s, s) for s in SIZES], append_images=imgs[:-1])
    big.save(os.path.join(ROOT, "app", "assets", "app_256.png"))
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()
