# -*- coding: utf-8 -*-
import os

import pytest
from PIL import Image

from app.core import convert_ops as cv
from app.core.office_com import detect_engines, OfficeConverter
from app.core.utils import fitz


def test_cell_value():
    assert cv.cell_value(None) is None
    assert cv.cell_value(5) == 5
    assert cv.cell_value("1,234") == 1234
    assert cv.cell_value("-3.5") == -3.5
    assert cv.cell_value("0123") == "0123"  # 앞자리 0 유지
    assert cv.cell_value(" a\nb ") == "a b"


def test_pdf_to_txt(sample_pdf, tmp_path):
    dst = tmp_path / "o.txt"
    cv.pdf_to_txt(sample_pdf, str(dst))
    t = dst.read_text(encoding="utf-8-sig")
    assert "===== 3 페이지 =====" in t and "hello world" in t


def test_pdf_to_xlsx_text_fallback(sample_pdf, tmp_path):
    from openpyxl import load_workbook
    dst = tmp_path / "o.xlsx"
    assert cv.pdf_to_xlsx(sample_pdf, str(dst)) == 0
    ws = load_workbook(dst)["텍스트"]
    assert ws.cell(1, 1).value == "페이지"
    assert ws.max_row >= 7


def test_pdf_to_xlsx_table(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    x0, y0, cw, rh = 72, 72, 100, 24
    for r in range(4):
        page.draw_line((x0, y0 + r * rh), (x0 + 3 * cw, y0 + r * rh))
    for c in range(4):
        page.draw_line((x0 + c * cw, y0), (x0 + c * cw, y0 + 3 * rh))
    for r in range(3):
        for c in range(3):
            page.insert_text((x0 + c * cw + 5, y0 + r * rh + 16), f"{r * 10 + c}", fontsize=10)
    src = tmp_path / "t.pdf"
    doc.save(str(src))
    dst = tmp_path / "t.xlsx"
    assert cv.pdf_to_xlsx(str(src), str(dst)) >= 1


def test_pdfs_to_docs(sample_pdf, tmp_path):
    assert [t[1] for t in cv.PDF_DOC_TARGETS] == ['.xlsx', '.txt']
    outs, errs = cv.pdfs_to_docs([sample_pdf], 1, str(tmp_path / "o"))
    assert len(outs) == 1 and not errs and outs[0].endswith(".txt")


def test_pdf_to_images(sample_pdf, tmp_path):
    doc = fitz.open(sample_pdf)
    jobs = [cv.PdfImageJob(doc, "sample.pdf", [0, 2], str(tmp_path / "img"), "sample", 3)]
    total, errs = cv.pdf_to_images(jobs, "JPG", 72, 80)
    assert total == 2 and not errs
    assert sorted(os.listdir(tmp_path / "img")) == ["sample_p001.jpg", "sample_p003.jpg"]
    assert Image.open(tmp_path / "img" / "sample_p001.jpg").size == (595, 842)


def test_images_to_pdf(sample_jpg, sample_png, tmp_path):
    dst = str(tmp_path / "all.pdf")
    n, errs = cv.images_to_pdf_single([sample_jpg, sample_png, "없음.jpg"], dst, "A4 (자동 방향)", 5, 85)
    assert n == 2 and len(errs) == 1 and fitz.open(dst).page_count == 2
    ok, errs = cv.images_to_pdf_each([sample_jpg, sample_png], str(tmp_path / "each"), "A4 세로", 0, 85)
    assert ok == 2 and len(os.listdir(tmp_path / "each")) == 2


def test_merge_pdfs(sample_pdf, tmp_path):
    dst = str(tmp_path / "m.pdf")
    cv.merge_pdfs([sample_pdf, sample_pdf], dst)
    assert fitz.open(dst).page_count == 6


def test_detect_engines_keys():
    e = detect_engines()
    assert set(e) == {'excel', 'word', 'ppt', 'hwp', 'soffice'}


def test_office_no_engine(tmp_path):
    src = tmp_path / "a.docx"
    src.write_bytes(b"")
    none = {'excel': False, 'word': False, 'ppt': False, 'hwp': False, 'soffice': None}
    with OfficeConverter(none) as c:
        with pytest.raises(RuntimeError):
            c.convert(str(src), str(tmp_path / "a.pdf"))
        with pytest.raises(RuntimeError):
            c.convert(str(tmp_path / "a.hwp"), str(tmp_path / "b.pdf"))
