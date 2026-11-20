# -*- coding: utf-8 -*-
import io

import pytest
from PIL import Image

from app.core import compress as cp
from app.core.utils import fitz


def heavy_doc():
    """고해상도 사진(약 720 DPI)이 든 2쪽 문서 + 투명 PNG + 글자"""
    doc = fitz.open()
    noise = Image.effect_noise((2400, 1600), 60).convert("RGB")
    b = io.BytesIO()
    noise.save(b, "JPEG", quality=95)
    for i in range(2):
        p = doc.new_page()
        p.insert_text((72, 72), f"page {i + 1} text", fontsize=12)
        p.insert_image(fitz.Rect(100, 100, 340, 260), stream=b.getvalue())
    sig = Image.new("RGBA", (600, 200), (0, 0, 0, 0))
    for x in range(50, 550):
        for y in range(95, 105):
            sig.putpixel((x, y), (0, 0, 0, 255))
    s = io.BytesIO()
    sig.save(s, "PNG")
    doc[0].draw_rect(fitz.Rect(100, 400, 400, 500), color=None, fill=(1, 1, 0))
    doc[0].insert_image(fitz.Rect(100, 400, 400, 500), stream=s.getvalue())
    return doc


def test_compress_reduces_size_and_dpi():
    doc = heavy_doc()
    assert max(cp.image_dpis(doc)) > 600
    res = cp.compress(doc, dpi=150, quality=70)
    assert res.after < res.before * 0.5 and res.saved_pct > 50
    out = fitz.open(stream=res.data, filetype="pdf")
    assert out.page_count == 2 and "page 2 text" in out[1].get_text()
    assert max(cp.image_dpis(out)) < 150 * 1.3        # MuPDF 는 정수 배율로 줄임 (720 → 180)
    assert doc[0].get_images()                       # 원본 문서는 그대로


def test_transparency_kept():
    res = cp.compress(heavy_doc(), dpi=96, quality=50)
    out = fitz.open(stream=res.data, filetype="pdf")
    pix = out[0].get_pixmap(dpi=72)
    r, g, b = pix.pixel(150, 420)[:3]                # 서명 PNG 의 투명 부분 → 노란 배경
    assert r > 230 and g > 230 and b < 60


def test_no_images_keeps_original():
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "only text")
    res = cp.compress(doc, dpi=96, quality=50)
    assert res.after <= res.before


def test_gray():
    res = cp.compress(heavy_doc(), dpi=150, quality=70, gray=True)
    out = fitz.open(stream=res.data, filetype="pdf")
    xref = out[0].get_images(full=True)[0][0]
    assert out.extract_image(xref)["colorspace"] == 1


@pytest.mark.parametrize("name,dpi,q", cp.PRESETS)
def test_presets_valid(name, dpi, q):
    assert 50 <= dpi <= 300 and 30 <= q <= 95 and "DPI" in name
