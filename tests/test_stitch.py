# -*- coding: utf-8 -*-
import os

import pytest
from PIL import Image

from app.core import image_ops as io_
from app.core.image_ops import StitchOptions as S
from app.core import convert_ops as cv
from app.core.utils import fitz


def solid(w, h, color):
    return Image.new("RGB", (w, h), color)


def test_vertical_fit_min_width():
    ims = [solid(400, 200, (255, 0, 0)), solid(200, 100, (0, 255, 0))]
    out = io_.stitch_images(ims, S(io_.VERTICAL, fit=io_.FIT_MIN))
    assert out.size == (200, 200)                     # 400x200 → 200x100, 200x100 그대로
    assert out.getpixel((100, 50)) == (255, 0, 0) and out.getpixel((100, 150)) == (0, 255, 0)


def test_horizontal_fit_max_height_gap_margin_bg():
    ims = [solid(100, 100, (255, 0, 0)), solid(100, 50, (0, 0, 255))]
    out = io_.stitch_images(ims, S(io_.HORIZONTAL, fit=io_.FIT_MAX, gap=10, margin=5, bg=(0, 0, 0)))
    assert out.size == (5 + 100 + 10 + 200 + 5, 5 + 100 + 5)    # 두 번째는 200x100 으로 커짐
    assert out.getpixel((110, 50)) == (0, 0, 0)                  # 간격 = 배경색
    assert out.getpixel((200, 50)) == (0, 0, 255)


def test_original_size_centered():
    ims = [solid(300, 100, (255, 0, 0)), solid(100, 100, (0, 255, 0))]
    out = io_.stitch_images(ims, S(io_.VERTICAL, fit=io_.FIT_NONE, bg=(255, 255, 255)))
    assert out.size == (300, 200)
    assert out.getpixel((10, 150)) == (255, 255, 255) and out.getpixel((150, 150)) == (0, 255, 0)  # 가운데 정렬


def test_grid():
    ims = [solid(100, 100, (i * 40, 0, 0)) for i in range(5)]
    (W, H), boxes = io_.stitch_layout([im.size for im in ims], S(io_.GRID, cols=3, gap=4))
    assert (W, H) == (3 * 100 + 2 * 4, 2 * 100 + 4)
    assert boxes[3][:2] == (0, 104) and boxes[2][:2] == (208, 0)
    out = io_.stitch_images(ims, S(io_.GRID, cols=3, gap=4))
    assert out.size == (W, H)


def test_transparent_background():
    ims = [solid(50, 50, (255, 0, 0)), solid(100, 50, (0, 0, 255))]
    out = io_.stitch_images(ims, S(io_.VERTICAL, fit=io_.FIT_NONE, bg=None))
    assert out.mode == "RGBA" and out.getpixel((5, 25))[3] == 0


def test_max_side_scales_down():
    ims = [solid(1000, 3000, (255, 0, 0)) for _ in range(4)]
    out = io_.stitch_images(ims, S(io_.VERTICAL, gap=100, max_side=6000))
    assert max(out.size) <= 6000 and out.size[0] == pytest.approx(1000 * 6000 / 12300, abs=2)  # 간격 포함 비율


def test_stitch_files_respects_format_limit(tmp_path):
    paths = []
    for i in range(3):
        p = tmp_path / f"{i}.png"
        solid(300, 7000, (0, 100 + i * 50, 0)).save(p)
        paths.append(str(p))
    dst = tmp_path / "out.webp"
    size, (w, h) = io_.stitch_files(paths, str(dst), "WEBP", S(io_.VERTICAL))
    assert h <= 16383 and os.path.getsize(dst) == size     # WEBP 최대 16383px
    dst2 = tmp_path / "out.jpg"
    _s, (w2, h2) = io_.stitch_files(paths, str(dst2), "JPG", S(io_.VERTICAL), target_kb=50)
    assert h2 <= 20000 and os.path.getsize(dst2) <= 50 * 1024          # 기본 최대 20000px


def test_errors():
    with pytest.raises(ValueError):
        io_.stitch_images([], S())


def make_pdf(path, n):
    d = fitz.open()
    for i in range(n):
        p = d.new_page(width=595, height=842)
        p.draw_rect(fitz.Rect(0, 0, 595, 842), color=None, fill=((i % 3) / 2, 0.3, 0.6))
    d.save(str(path))
    return fitz.open(str(path))


def test_pdf_to_single_image(tmp_path):
    doc = make_pdf(tmp_path / "a.pdf", 3)
    job = cv.PdfImageJob(doc, "a.pdf", [0, 1, 2], str(tmp_path / "o"), "a", 3)
    n, errs, notes = cv.pdf_to_single_images([job], "PNG", 72, 90, gap=20)
    assert n == 1 and not errs and not notes
    files = os.listdir(tmp_path / "o")
    assert files == ["a_전체.png"]
    im = Image.open(tmp_path / "o" / files[0])
    assert im.size == (595, 842 * 3 + 40)
    assert im.getpixel((300, 842 + 10)) == (229, 231, 235)       # 페이지 사이 구분 간격


def test_pdf_to_single_image_too_tall_lowers_dpi(tmp_path):
    doc = make_pdf(tmp_path / "b.pdf", 30)
    job = cv.PdfImageJob(doc, "b.pdf", list(range(30)), str(tmp_path / "o"), "b", 3)
    n, errs, notes = cv.pdf_to_single_images([job], "WEBP", 150, 80)
    assert n == 1 and notes and "DPI" in notes[0]
    im = Image.open(tmp_path / "o" / "b_전체.webp")
    assert im.size[1] <= 16383
