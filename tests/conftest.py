# -*- coding: utf-8 -*-
import os
import sys

import pytest
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.utils import fitz, korean_font  # noqa: E402


@pytest.fixture
def sample_pdf(tmp_path):
    """3페이지, 각 페이지에 'Page N 안녕하세요' 텍스트"""
    doc = fitz.open()
    font = korean_font()
    for i in range(3):
        page = doc.new_page(width=595, height=842)
        kw = dict(fontsize=14)
        if font:
            kw.update(fontname="kfont", fontfile=font)
        page.insert_text((72, 100), f"Page {i + 1} 안녕하세요", **kw)
        page.insert_text((72, 140), "hello world", fontsize=12)
    p = tmp_path / "sample.pdf"
    doc.save(str(p))
    return str(p)


@pytest.fixture
def sample_jpg(tmp_path):
    im = Image.effect_noise((1600, 1200), 80).convert("RGB")
    p = tmp_path / "photo.jpg"
    im.save(str(p), "JPEG", quality=95)
    return str(p)


@pytest.fixture
def sample_png(tmp_path):
    im = Image.new("RGBA", (400, 300), (255, 0, 0, 128))
    p = tmp_path / "alpha.png"
    im.save(str(p), "PNG")
    return str(p)
