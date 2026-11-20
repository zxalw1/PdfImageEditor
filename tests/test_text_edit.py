# -*- coding: utf-8 -*-
import pytest

from app.core import text_edit as te
from app.core import pdf_ops
from app.core.utils import fitz, korean_font

KF = korean_font()
needs_kfont = pytest.mark.skipif(not KF, reason="한글 글꼴 없음")


def make_doc(rotation=0):
    doc = fitz.open()
    p = doc.new_page(width=595, height=842)
    p.draw_rect(fitz.Rect(60, 180, 400, 210), color=None, fill=(1, 1, 0))          # 노란 배경
    p.insert_text((72, 100), "Page 1 원본 문서", fontsize=16, fontname="kf", fontfile=KF, color=(0.8, 0, 0))
    p.insert_text((72, 140), "hello world", fontsize=12)                            # Helvetica
    p.insert_text((72, 200), "노란 배경 위 글자", fontsize=12, fontname="kf", fontfile=KF)
    # 문단(줄 간격 좁음) 3줄
    for i, t in enumerate(["첫째 줄입니다", "둘째 줄입니다", "셋째 줄입니다"]):
        p.insert_text((72, 300 + i * 14), t, fontsize=12, fontname="kf", fontfile=KF)
    if rotation:
        p.set_rotation(rotation)
    return doc, p


def line_texts(page):
    """화면 위→아래 순서의 줄 텍스트 (새로 쓴 줄은 추출 순서가 뒤로 가므로 위치로 정렬)"""
    units = sorted(te.text_units(page, te.LINE), key=lambda u: (round(u.origins[0][1]), u.origins[0][0]))
    return [u.text for u in units]


def unit_with(page, s, level=te.LINE):
    return next(u for u in te.text_units(page, level) if s in u.text)


@needs_kfont
def test_units_line_and_block():
    doc, p = make_doc()
    lines = line_texts(p)
    assert "Page 1 원본 문서" in lines and "hello world" in lines and "둘째 줄입니다" in lines
    blk = unit_with(p, "둘째", te.BLOCK)
    assert blk.text.split("\n") == ["첫째 줄입니다", "둘째 줄입니다", "셋째 줄입니다"]
    assert abs(blk.line_pitch - 14) < 0.5
    u = unit_with(p, "원본")
    assert u.size == 16 and u.color[0] > 0.7 and u.origins[0] == pytest.approx((72, 100), abs=0.5)


@needs_kfont
def test_paragraph_grouping_wide_spacing_and_table():
    doc = fitz.open()
    p = doc.new_page()
    for i in range(3):                               # 줄 간격 넓은 문단 (11pt, 18pt 간격)
        p.insert_text((60, 140 + i * 18), f"문단 {i + 1}번째 줄", fontsize=11, fontname="kf", fontfile=KF)
    for k, (a, b) in enumerate([("생산량", "12,480"), ("불량률", "0.6%")]):   # 표 2행 2열
        y = 220 + k * 26
        p.insert_text((68, y + 17), a, fontsize=10.5, fontname="kf", fontfile=KF)
        p.insert_text((208, y + 17), b, fontsize=10.5, fontname="kf", fontfile=KF)
    p.insert_text((60, 400), "큰 제목", fontsize=20, fontname="kf", fontfile=KF)
    p.insert_text((60, 420), "작은 본문", fontsize=10, fontname="kf", fontfile=KF)
    blocks = sorted(u.text for u in te.text_units(p, te.BLOCK))
    assert "문단 1번째 줄\n문단 2번째 줄\n문단 3번째 줄" in blocks
    for cell in ("생산량", "12,480", "불량률", "0.6%", "큰 제목", "작은 본문"):
        assert cell in blocks                        # 표 칸·크기 다른 줄은 따로


@needs_kfont
def test_paragraph_word_spacing_and_table_rules():
    """Word 기본 줄 간격(≈2배)은 한 문단, 표 테두리로 나뉜 위아래 칸은 따로"""
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((90, 138), "워드 문단 첫 줄", fontsize=11, fontname="kf", fontfile=KF)
    p.insert_text((90, 160), "워드 문단 둘째 줄", fontsize=11, fontname="kf", fontfile=KF)
    for y in (210, 229, 249):                        # 표 가로 테두리
        p.draw_line((85, y), (516, y), width=0.5)
    p.insert_text((90, 224), "항목", fontsize=11, fontname="kf", fontfile=KF)
    p.insert_text((90, 243.7), "불량률", fontsize=11, fontname="kf", fontfile=KF)
    blocks = [u.text for u in te.text_units(p, te.BLOCK)]
    assert "워드 문단 첫 줄\n워드 문단 둘째 줄" in blocks
    assert "항목" in blocks and "불량률" in blocks


@pytest.mark.skipif(not te.fallback_font_file(True) or not te._is_bold_file(te.fallback_font_file(True)),
                    reason="굵은 맑은 고딕 없음")
def test_bold_kept_with_fallback(tmp_path):
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((72, 100), "굵은 제목", fontsize=16, fontname="kb", fontfile=te.fallback_font_file(True))
    d2 = pdf_ops.doc_from_bytes(pdf_ops.doc_to_bytes(doc))   # 서브셋 → 대체 글꼴 경로
    p2 = d2[0]
    u = unit_with(p2, "굵은")
    assert u.bold
    te.replace_unit(d2, p2, u, "굵은 제목 수정", fallback=KF)   # 앱처럼 보통 글꼴을 넘겨도
    n = unit_with(p2, "수정")
    assert n.bold and "bold" in n.font.lower()


@needs_kfont
def test_unit_at():
    doc, p = make_doc()
    units = te.text_units(p)
    assert te.unit_at(units, 80, 95).text == "Page 1 원본 문서"
    assert te.unit_at(units, 500, 500) is None


@needs_kfont
def test_replace_keeps_position_size_color():
    doc, p = make_doc()
    u = unit_with(p, "원본")
    desc = te.replace_unit(doc, p, u, "Page 1 수정한 문서")
    assert desc == "원본 글꼴"                       # 맑은 고딕 전체가 내장 → 재사용
    n = unit_with(p, "수정한")
    assert n.text == "Page 1 수정한 문서"
    assert n.size == 16 and n.color[0] > 0.7
    assert n.origins[0] == pytest.approx(u.origins[0], abs=0.5)
    assert "원본" not in p.get_text()
    # 다른 줄은 그대로
    assert "hello world" in line_texts(p) and "둘째 줄입니다" in line_texts(p)


@needs_kfont
def test_base14_and_fallback():
    doc, p = make_doc()
    u = unit_with(p, "hello")
    assert te.replace_unit(doc, p, u, "hello PDF") == "원본 글꼴(기본)"
    u = unit_with(p, "hello PDF")
    assert te.replace_unit(doc, p, u, "안녕 PDF") == "맑은 고딕(대체)"   # 기본 글꼴엔 한글 없음
    assert "안녕 PDF" in line_texts(p)


@needs_kfont
def test_subset_font_missing_glyph_falls_back(tmp_path):
    doc, p = make_doc()
    data = pdf_ops.doc_to_bytes(doc)                 # 서브셋 저장 → 쓰인 글자만 남음
    d2 = pdf_ops.doc_from_bytes(data)
    p2 = d2[0]
    # 서브셋 글꼴은 유니코드 대응표가 없어 글자를 확인할 수 없음 → 안전하게 대체 글꼴 사용 (깨짐 방지)
    u = unit_with(p2, "원본")
    assert te.replace_unit(d2, p2, u, "완전히 새로운 낱말") == "맑은 고딕(대체)"
    assert "완전히 새로운 낱말" in line_texts(p2)
    out = tmp_path / "re.pdf"
    pdf_ops.write_doc(d2, str(out))
    assert "완전히 새로운 낱말" in fitz.open(str(out))[0].get_text()


@needs_kfont
def test_background_preserved():
    doc, p = make_doc()
    u = unit_with(p, "노란 배경")
    te.replace_unit(doc, p, u, "바뀐 글자")
    pix = p.get_pixmap(dpi=72, clip=fitz.Rect(300, 185, 390, 205))
    r, g, b = pix.pixel(pix.width // 2, pix.height // 2)[:3]
    assert r > 240 and g > 240 and b < 30           # 노란 배경 유지
    assert "바뀐 글자" in line_texts(p)


@needs_kfont
def test_tight_lines_not_affected():
    doc, p = make_doc()
    u = unit_with(p, "둘째")
    te.replace_unit(doc, p, u, "둘째 줄 수정")
    assert line_texts(p)[-3:] == ["첫째 줄입니다", "둘째 줄 수정", "셋째 줄입니다"]


@needs_kfont
def test_block_multiline_edit():
    doc, p = make_doc()
    u = unit_with(p, "둘째", te.BLOCK)
    te.replace_unit(doc, p, u, "하나\n둘\n셋\n넷")
    lines = line_texts(p)
    assert lines[-4:] == ["하나", "둘", "셋", "넷"]
    ys = [x.origins[0][1] for x in te.text_units(p) if x.text in ("하나", "둘", "셋", "넷")]
    assert ys == pytest.approx([300, 314, 328, 342], abs=0.6)   # 원래 줄 간격 유지


@needs_kfont
def test_delete_text():
    doc, p = make_doc()
    te.replace_unit(doc, p, unit_with(p, "hello"), "")
    assert "hello" not in p.get_text()


@needs_kfont
@pytest.mark.parametrize("rot", [90, 180, 270])
def test_rotated_page(rot):
    doc, p = make_doc(rot)
    u = unit_with(p, "원본")
    te.replace_unit(doc, p, u, "회전 페이지 수정")
    n = unit_with(p, "회전 페이지")
    assert n.origins[0] == pytest.approx(u.origins[0], abs=0.5)
    assert p.rotation == rot


def test_scanned_page_has_no_text(sample_jpg):
    doc = fitz.open()
    pdf_ops.images_to_pdf_pages(doc, [sample_jpg], "A4 세로", 0, 80)
    assert not te.page_has_text(doc[0])
    assert te.text_units(doc[0]) == []


@needs_kfont
def test_replace_text_no_overlap():
    doc, p = make_doc()
    n = pdf_ops.replace_text(doc, [0], "원본", "새로 고친", KF)
    assert n == 1
    assert "Page 1 새로 고친 문서" in line_texts(p)   # 글자 겹침 없이 한 줄로


@needs_kfont
def test_save_subsets_fonts(tmp_path):
    doc, p = make_doc()
    full = len(doc.tobytes(garbage=3, deflate=True))
    out = tmp_path / "s.pdf"
    size = pdf_ops.write_doc(doc, str(out))
    assert size < full / 5
    assert "Page 1 원본 문서" in fitz.open(str(out))[0].get_text()
    # 편집 중 문서는 서브셋 영향 없음 → 새 글자 계속 입력 가능
    u = unit_with(p, "원본")
    assert te.replace_unit(doc, p, u, "저장 후 완전히 다른 글자") == "원본 글꼴"
