# -*- coding: utf-8 -*-
import os

import pytest

from app.core import pdf_ops
from app.core.utils import fitz, korean_font


def test_open_and_roundtrip(sample_pdf, tmp_path):
    doc = pdf_ops.open_pdf(sample_pdf)
    assert doc.page_count == 3
    out = tmp_path / "out.pdf"
    assert pdf_ops.write_doc(doc, str(out)) > 0
    assert pdf_ops.open_pdf(str(out)).page_count == 3


def test_password(tmp_path):
    doc = fitz.open()
    doc.new_page()
    p = str(tmp_path / "pw.pdf")
    doc.save(p, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="1234", owner_pw="1234")
    with pytest.raises(ValueError):
        pdf_ops.open_pdf(p)
    with pytest.raises(ValueError):
        pdf_ops.open_pdf(p, lambda _: "wrong")
    assert pdf_ops.open_pdf(p, lambda _: "1234").page_count == 1


def test_rotate_delete_blank(sample_pdf):
    doc = pdf_ops.open_pdf(sample_pdf)
    pdf_ops.rotate_pages(doc, [0, 2], 90)
    assert [p.rotation for p in doc] == [90, 0, 90]
    pdf_ops.rotate_pages(doc, [0], -90)
    assert doc[0].rotation == 0
    pdf_ops.delete_pages(doc, [1])
    assert doc.page_count == 2
    assert pdf_ops.insert_blank(doc, 0) == 1
    assert doc.page_count == 3
    assert doc[1].get_text().strip() == ""


def test_move_order():
    assert pdf_ops.move_order(4, [1], -1) == [1, 0, 2, 3]
    assert pdf_ops.move_order(4, [1, 2], 1) == [0, 3, 1, 2]
    assert pdf_ops.move_order(4, [0], -1) is None
    assert pdf_ops.move_order(4, [3], 1) is None
    assert pdf_ops.move_order(4, [], 1) is None


def test_reorder(sample_pdf):
    doc = pdf_ops.open_pdf(sample_pdf)
    pdf_ops.reorder(doc, [2, 0, 1])
    assert "Page 3" in doc[0].get_text()


def test_extract_and_split(sample_pdf, tmp_path):
    doc = pdf_ops.open_pdf(sample_pdf)
    ex = str(tmp_path / "ex.pdf")
    pdf_ops.extract_pages(doc, [0, 2], ex)
    e = fitz.open(ex)
    assert e.page_count == 2 and "Page 3" in e[1].get_text()

    assert pdf_ops.split_each(3) == [[0], [1], [2]]
    assert pdf_ops.split_every(5, 2) == [[0, 1], [2, 3], [4]]
    out = tmp_path / "split"
    out.mkdir()
    outs = pdf_ops.split_doc(doc, [[0, 1], [2]], str(out), "s")
    assert [os.path.basename(x) for x in outs] == ["s_p1-2.pdf", "s_p3.pdf"]


def test_split_cancel(sample_pdf, tmp_path):
    class Cancel:
        def report(self, *a):
            pass

        def cancelled(self):
            return True
    doc = pdf_ops.open_pdf(sample_pdf)
    assert pdf_ops.split_doc(doc, [[0], [1]], str(tmp_path), "s", Cancel()) == []


def test_insert_text_korean(sample_pdf):
    doc = pdf_ops.open_pdf(sample_pdf)
    page = doc[0]
    pdf_ops.insert_text(page, fitz.Point(72, 300), "한글 테스트 ABC", 12, (0, 0, 0), korean_font())
    txt = page.get_text()
    if korean_font():
        assert "한글 테스트 ABC" in txt
    else:
        assert "ABC" in txt


def test_view_to_pdf_point(sample_pdf):
    doc = pdf_ops.open_pdf(sample_pdf)
    p = pdf_ops.view_to_pdf_point(doc[0], 100, 200, 2.0)
    assert (round(p.x), round(p.y)) == (50, 100)


def test_redact_rect(sample_pdf):
    doc = pdf_ops.open_pdf(sample_pdf)
    page = doc[0]
    r = page.search_for("hello")[0]
    pdf_ops.redact_rect(page, r)
    assert "hello" not in page.get_text()
    assert "Page 1" in page.get_text()


def test_replace_text(sample_pdf):
    doc = pdf_ops.open_pdf(sample_pdf)
    n = pdf_ops.replace_text(doc, range(doc.page_count), "hello", "bye", korean_font())
    assert n == 3
    assert all("bye" in p.get_text() and "hello" not in p.get_text() for p in doc)
    assert pdf_ops.replace_text(doc, [0], "없는말", "x") == 0


def test_merge_into(sample_pdf, sample_png, tmp_path):
    doc = pdf_ops.new_doc()
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf")
    errs = pdf_ops.merge_into(doc, [sample_pdf, sample_png, str(bad)])
    assert doc.page_count == 4
    assert len(errs) == 1 and errs[0][0] == "bad.pdf"


def test_images_to_pdf_pages_sizes(sample_jpg, sample_png):
    doc = fitz.open()
    pdf_ops.images_to_pdf_pages(doc, [sample_jpg], "A4 (자동 방향)", 5, 85)  # 가로 이미지 → A4 가로
    pdf_ops.images_to_pdf_pages(doc, [sample_png], "A4 세로", 0, 85)
    pdf_ops.images_to_pdf_pages(doc, [sample_png], "이미지 원본 크기", 0, 85)
    r0, r1, r2 = (doc[i].rect for i in range(3))
    assert round(r0.width) == 842 and round(r0.height) == 595
    assert round(r1.width) == 595
    assert round(r2.width) == 300  # 400px @96dpi → 300pt
