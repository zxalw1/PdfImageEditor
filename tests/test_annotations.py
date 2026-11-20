# -*- coding: utf-8 -*-
import pytest

from app.core import overlay as ov
from app.core.utils import fitz, korean_font

KF = korean_font()


def doc_with_text(rotation=0):
    doc = fitz.open()
    p = doc.new_page(width=595, height=842)
    kw = dict(fontname="kf", fontfile=KF) if KF else {}
    p.insert_text((72, 100), "형광펜 칠할 문장입니다", fontsize=14, **kw)
    p.insert_text((72, 130), "두 번째 줄 문장", fontsize=14, **kw)
    if rotation:
        p.set_rotation(rotation)
    return doc, p


def annots(page):
    return [(a.type[1], a) for a in page.annots()]


def test_highlight_snaps_to_text_and_becomes_markup():
    doc, p = doc_with_text()
    snapped = ov.snap_to_text(p, fitz.Rect(60, 80, 400, 140))
    assert snapped.x0 >= 70 and snapped.y0 > 80 and snapped.y1 < 140   # 두 줄에 딱 맞춤
    L = ov.ObjectLayer()
    L.add_shape(p.xref, "highlight", (60, 80), (400, 140))
    L.flatten(doc)
    (t, a), = annots(p)
    assert t == "Highlight" and len(a.vertices) == 8                    # 두 줄 → 사각 2개
    assert a.colors["stroke"] == pytest.approx(ov.DEFAULT_COLORS["highlight"], abs=0.01)
    assert a.info["title"] == ov.ANNOT_TITLE


def test_highlight_on_blank_area_is_translucent_rect():
    doc, p = doc_with_text()
    L = ov.ObjectLayer()
    L.add_shape(p.xref, "highlight", (100, 500), (300, 540))
    L.flatten(doc)
    (t, a), = annots(p)
    assert t == "Square" and a.opacity == pytest.approx(0.4, abs=0.01)


def test_underline_text_and_blank():
    doc, p = doc_with_text()
    L = ov.ObjectLayer()
    L.add_shape(p.xref, "underline", (60, 85), (400, 105))
    L.add_shape(p.xref, "underline", (100, 600), (300, 600))
    L.flatten(doc)
    kinds = sorted(t for t, _a in annots(p))
    assert kinds == ["Line", "Underline"]


def test_arrow_direction_and_note():
    doc, p = doc_with_text()
    L = ov.ObjectLayer()
    a = L.add_shape(p.xref, "arrow", (300, 400), (100, 300))      # 오른쪽 아래 → 왼쪽 위
    s, e = a.arrow_points()
    assert (s.x, s.y, e.x, e.y) == (300, 400, 100, 300)
    L.add_shape(p.xref, "note", (500, 50), text="검토 필요: 금액 확인")
    L.flatten(doc)
    d = dict((t, x) for t, x in annots(p))
    line = d["Line"]
    assert line.line_ends == (fitz.PDF_ANNOT_LE_NONE, fitz.PDF_ANNOT_LE_CLOSED_ARROW)
    v = line.vertices
    assert v[0] == pytest.approx((300, 400), abs=0.5) and v[1] == pytest.approx((100, 300), abs=0.5)
    assert d["Text"].info["content"] == "검토 필요: 금액 확인"


@pytest.mark.parametrize("rot", [0, 90, 180, 270])
def test_rect_on_rotated_page_appears_where_drawn(rot):
    doc, p = doc_with_text(rot)
    L = ov.ObjectLayer()
    L.add_shape(p.xref, "rect", (200, 200), (400, 300))          # 화면 좌표
    L.flatten(doc)
    pix = p.get_pixmap(dpi=72)
    r, g, b = pix.pixel(300, 200)[:3]                              # 위쪽 테두리 가운데
    assert r > 180 and g < 90 and b < 90
    assert pix.pixel(300, 250)[:3] == (255, 255, 255)              # 안쪽은 비어 있음


def test_shapes_move_resize_free_aspect():
    doc, p = doc_with_text()
    L = ov.ObjectLayer()
    o = L.add_shape(p.xref, "rect", (100, 100), (200, 150))
    assert o.aspect is None and o.resizable
    L.resize(o.id, "br", 400, 160)                                  # 비율 자유
    assert o.frect() == fitz.Rect(100, 100, 400, 160)
    n = L.add_shape(p.xref, "note", (10, 10), text="x")
    assert not n.resizable and n.frect().width == ov.NOTE_SIZE


def test_annotations_persist_and_survive_save(tmp_path):
    doc, p = doc_with_text()
    L = ov.ObjectLayer()
    for k in ("highlight", "underline", "rect", "arrow"):
        L.add_shape(p.xref, k, (60, 80 + len(L) * 100), (300, 120 + len(L) * 100))
    L.add_shape(p.xref, "note", (500, 700), text="메모")
    L.flatten(doc)
    out = tmp_path / "a.pdf"
    doc.save(str(out))
    assert len(list(fitz.open(str(out))[0].annots())) == 5
