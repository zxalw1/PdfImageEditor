# -*- coding: utf-8 -*-
import io

import pytest
from PIL import Image

from app.core import page_deco as pd
from app.core.utils import fitz


def new_doc(n=4, rotations=()):
    doc = fitz.open()
    for i in range(n):
        p = doc.new_page(width=595, height=842)
        if i < len(rotations):
            p.set_rotation(rotations[i])
    return doc


def lines(page):
    """(텍스트, 화면 기준 bbox)"""
    out = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            t = "".join(s["text"] for s in l["spans"])
            out.append((t, fitz.Rect(l["bbox"]) * page.rotation_matrix, l["dir"]))
    return out


def find(page, text):
    return next(((r, d) for t, r, d in lines(page) if t == text), (None, None))


def test_page_numbers_format_position_start():
    doc = new_doc(3)
    o = pd.DecoOptions(numbers=pd.NumberOpts(True, "1 / 10", "아래 가운데", start=1))
    assert pd.decorate(doc, o) == 3
    r, _ = find(doc[1], "2 / 3")
    assert r is not None and abs((r.x0 + r.x1) / 2 - 297.5) < 2 and r.y1 > 800


def test_numbers_skip_first_and_range_and_corner():
    doc = new_doc(5)
    o = pd.DecoOptions(numbers=pd.NumberOpts(True, "- 1 -", "위 오른쪽", start=1, skip_first=True), pages="2-5")
    pd.decorate(doc, o)
    assert not lines(doc[0]) and not lines(doc[1])         # 범위 밖 / 첫 쪽 건너뜀
    r, _ = find(doc[2], "- 1 -")
    assert r is not None and r.x1 > 540 and r.y0 < 60
    assert find(doc[4], "- 3 -")[0] is not None


def test_header_footer_placeholders():
    doc = new_doc(2)
    o = pd.DecoOptions(hf=pd.HeaderFooterOpts(True, ("{file}", "", "{date}"), ("", "{page}/{total}쪽", "")),
                       filename="보고서")
    pd.decorate(doc, o)
    texts = [t for t, _r, _d in lines(doc[1])]
    assert "보고서" in texts and "2/2쪽" in texts
    assert any(len(t) == 10 and t[4] == "-" for t in texts)     # 날짜 YYYY-MM-DD
    r, _ = find(doc[1], "보고서")
    assert r.x0 < 40 and r.y0 < 60                              # 왼쪽 위


def test_number_and_footer_same_spot_do_not_overlap():
    doc = new_doc(1)
    o = pd.DecoOptions(numbers=pd.NumberOpts(True, "1", "아래 가운데"),
                       hf=pd.HeaderFooterOpts(True, ("", "", ""), ("", "바닥글", "")))
    pd.decorate(doc, o)
    rn, _ = find(doc[0], "1")
    rf, _ = find(doc[0], "바닥글")
    assert not rn.intersects(rf)


@pytest.mark.parametrize("rot", [0, 90, 180, 270])
def test_rotated_pages_upright(rot):
    doc = new_doc(1, [rot])
    o = pd.DecoOptions(numbers=pd.NumberOpts(True, "1페이지", "아래 오른쪽"))
    pd.decorate(doc, o)
    r, d = find(doc[0], "1페이지")
    pr = doc[0].rect
    assert r.x1 > pr.width - 60 and r.y1 > pr.height - 60          # 화면 기준 오른쪽 아래
    v = fitz.Point(d) * fitz.Matrix(rot)                            # 화면 기준 글자 방향 = 가로
    assert v.x == pytest.approx(1, abs=0.01) and v.y == pytest.approx(0, abs=0.01)


@pytest.mark.parametrize("rot", [0, 90])
def test_text_watermark_centered_diagonal(rot):
    doc = new_doc(1, [rot])
    o = pd.DecoOptions(wm=pd.WatermarkOpts(True, "text", "대외비 CONFIDENTIAL", size=40, angle=45))
    pd.decorate(doc, o)
    r, d = find(doc[0], "대외비 CONFIDENTIAL")
    pr = doc[0].rect
    assert abs((r.x0 + r.x1) / 2 - pr.width / 2) < 6 and abs((r.y0 + r.y1) / 2 - pr.height / 2) < 6
    v = fitz.Point(d) * fitz.Matrix(rot)
    assert v.x == pytest.approx(0.707, abs=0.02) and v.y == pytest.approx(-0.707, abs=0.02)   # 왼쪽 아래 → 오른쪽 위


def test_image_watermark_faded_behind():
    im = Image.new("RGB", (200, 100), (255, 0, 0))
    b = io.BytesIO()
    im.save(b, "PNG")
    doc = new_doc(1)
    doc[0].draw_rect(fitz.Rect(0, 0, 595, 842), color=None, fill=(1, 1, 1))
    o = pd.DecoOptions(wm=pd.WatermarkOpts(True, "image", image=b.getvalue(), scale=0.5, opacity=0.3, behind=False))
    pd.decorate(doc, o)
    pix = doc[0].get_pixmap(dpi=72)
    r, g, _b = pix.pixel(297, 421)[:3]
    assert r > 240 and 150 < g < 210                 # 흐린 빨강 (30%)
    assert pix.pixel(50, 50)[:3] == (255, 255, 255)
    assert len(doc[0].get_images()) == 1


def test_preview_does_not_change_doc():
    doc = new_doc(2)
    o = pd.DecoOptions(numbers=pd.NumberOpts(True))
    pix = pd.preview_page(doc, 1, o)
    assert pix.width > 0 and not lines(doc[1])
