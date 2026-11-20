# -*- coding: utf-8 -*-
import io

import pytest
from PIL import Image

from app.core import overlay as ov
from app.core.utils import fitz


def png_bytes(size=(200, 100), color=(0, 0, 255, 255), corner=(255, 0, 0, 255)):
    im = Image.new("RGBA", size, color)
    for x in range(size[0] // 4):
        for y in range(size[1] // 2):
            im.putpixel((x, y), corner)
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


def new_doc(n=2, rotation=0):
    doc = fitz.open()
    for _ in range(n):
        p = doc.new_page(width=595, height=842)
        p.set_rotation(rotation)
    return doc


def test_add_hit_move_resize_remove():
    doc = new_doc()
    L = ov.ObjectLayer()
    o = L.add(doc[0].xref, (100, 100, 300, 200), png_bytes(), (200, 100))
    assert L.hit(doc[0].xref, 150, 150) is o and L.hit(doc[1].xref, 150, 150) is None
    L.move(o.id, 50, 20)
    assert o.rect == (150, 120, 350, 220)
    L.move(o.id, 5000, 0, bounds=doc[0].rect)        # 절반 이상 페이지 밖으로 못 나감
    assert o.frect().x0 + o.frect().width / 2 <= 595
    L.resize(o.id, "br", o.rect[0] + 100, o.rect[1] + 400)   # 비율 유지
    assert o.frect().width == pytest.approx(100) and o.frect().height == pytest.approx(50)
    L.resize(o.id, "tl", o.rect[0] - 100, o.rect[1] - 10, keep_aspect=False)
    assert o.frect().width == pytest.approx(200) and o.frect().height == pytest.approx(60)
    L.resize(o.id, "br", o.rect[0], o.rect[1])                 # 최소 크기
    assert o.frect().width >= ov.MIN_SIDE
    L.remove(o.id)
    assert len(L) == 0


def test_hit_topmost():
    doc = new_doc()
    L = ov.ObjectLayer()
    a = L.add(doc[0].xref, (100, 100, 300, 300), png_bytes(), (200, 100))
    b = L.add(doc[0].xref, (150, 150, 250, 250), png_bytes(), (200, 100))
    assert L.hit(doc[0].xref, 200, 200) is b
    assert L.hit(doc[0].xref, 110, 110) is a


@pytest.mark.parametrize("rot", [0, 90, 180, 270])
def test_flatten_position_and_orientation(rot):
    doc = new_doc(1, rot)
    L = ov.ObjectLayer()
    L.add(doc[0].xref, (100, 100, 300, 200), png_bytes(), (200, 100))
    L.flatten(doc)
    assert len(L) == 0
    pix = doc[0].get_pixmap(dpi=72)
    assert pix.pixel(105, 105)[:3] == (255, 0, 0)      # 왼쪽 위 = 빨강 (바로 선 방향)
    assert pix.pixel(290, 190)[:3] == (0, 0, 255)
    assert pix.pixel(350, 150)[:3] == (255, 255, 255)


def test_flatten_follows_page_reorder_and_drops_deleted():
    doc = new_doc(3)
    L = ov.ObjectLayer()
    x0, x2 = doc[0].xref, doc[2].xref
    L.add(x0, (10, 10, 60, 35), png_bytes(), (200, 100))
    L.add(x2, (10, 10, 60, 35), png_bytes(), (200, 100))
    doc.select([2, 1, 0])                               # 순서 바꾸기
    assert doc[2].xref == x0
    doc.delete_page(0)                                  # 원래 2번(x2) 삭제
    L.drop_missing(doc)
    assert [o.page_xref for o in L.items] == [x0]
    L.flatten(doc)
    assert doc[1].get_images() and not doc[0].get_images()


def test_flatten_only_some_pages():
    doc = new_doc(2)
    L = ov.ObjectLayer()
    L.add(doc[0].xref, (10, 10, 60, 35), png_bytes(), (200, 100))
    L.add(doc[1].xref, (10, 10, 60, 35), png_bytes(), (200, 100))
    L.flatten(doc, {doc[0].xref})
    assert len(L) == 1 and L.items[0].page_xref == doc[1].xref


def test_flattened_copy_keeps_layer():
    doc = new_doc(1)
    L = ov.ObjectLayer()
    L.add(doc[0].xref, (10, 10, 60, 35), png_bytes(), (200, 100))
    cp = ov.flattened_copy(doc, L)
    assert cp[0].get_images() and not doc[0].get_images() and len(L) == 1


def test_transparent_png_kept(tmp_path):
    im = Image.new("RGBA", (100, 50), (0, 0, 0, 0))
    for x in range(10, 90):
        im.putpixel((x, 25), (0, 0, 0, 255))
    p = tmp_path / "sig.png"
    im.save(p)
    data, size = ov.prepare_image(str(p))
    assert Image.open(io.BytesIO(data)).mode == "RGBA" and size == (100, 50)
    doc = fitz.open()
    page = doc.new_page()
    page.draw_rect(fitz.Rect(0, 0, 595, 842), color=None, fill=(1, 1, 0))   # 노란 배경
    ov.draw_image(page, fitz.Rect(100, 100, 300, 200), data)
    pix = page.get_pixmap(dpi=72)
    r, g, b = pix.pixel(110, 110)[:3]
    assert r > 240 and g > 240 and b < 30               # 투명 부분은 배경 그대로


def test_remove_white_background(tmp_path):
    im = Image.new("RGB", (120, 80), (252, 252, 250))   # 스캔한 흰 종이
    for x in range(30, 90):
        for y in range(30, 50):
            im.putpixel((x, y), (200, 20, 20))           # 빨간 도장
    p = tmp_path / "stamp.jpg"
    im.save(p, quality=95)
    data, size = ov.prepare_image(str(p), remove_bg=True)
    out = Image.open(io.BytesIO(data))
    assert out.mode == "RGBA"
    assert size[0] < 120 and size[1] < 80                # 투명 여백 잘라냄
    a = out.getchannel("A")
    assert a.getpixel((0, 0)) == 0                      # 흰 배경 → 투명
    assert a.getpixel((out.width // 2, out.height // 2)) == 255


def test_prepare_large_and_jpeg(tmp_path):
    p = tmp_path / "big.jpg"
    Image.new("RGB", (5000, 2500), (10, 200, 10)).save(p)
    data, size = ov.prepare_image(str(p))
    assert max(size) == ov.MAX_PX and Image.open(io.BytesIO(data)).format == "JPEG"


def test_default_rect_and_drag():
    pr = fitz.Rect(0, 0, 595, 842)
    r = ov.default_rect(pr, (2000, 1000))
    assert r.width == pytest.approx(595 * 0.3) and r.height == pytest.approx(r.width / 2)
    assert pr.contains(r)
    r = ov.default_rect(pr, (100, 50), center=(590, 10))   # 페이지 가장자리 → 안으로
    assert pr.contains(r) and r.width == pytest.approx(75)
    d = ov.rect_from_drag(100, 100, 300, 300, 2.0)
    assert (d.width, d.height) == (200, 100)
    d = ov.rect_from_drag(300, 300, 100, 250, 2.0)        # 거꾸로 드래그
    assert d.x1 == 300 and d.width == pytest.approx(100)
