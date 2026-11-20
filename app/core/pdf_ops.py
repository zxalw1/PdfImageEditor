# -*- coding: utf-8 -*-
"""PDF 편집 처리 (Qt 의존 없음)"""
import io
import os

from .utils import fitz, A4, LETTER, unique_path, task_or_null
from .image_ops import open_image, flatten_white

REDACT_KEEP_IMAGES = getattr(fitz, 'PDF_REDACT_IMAGE_NONE', 0)


# ── 열기/저장 ──
def open_pdf(path, password_cb=None, bad_password_msg="암호가 올바르지 않습니다."):
    """password_cb(path) -> 암호 문자열 또는 None(취소)"""
    with open(path, 'rb') as f:
        data = f.read()
    doc = fitz.open(stream=data, filetype="pdf")
    if doc.needs_pass:
        pw = password_cb(path) if password_cb else None
        if pw is None or not doc.authenticate(pw):
            raise ValueError(bad_password_msg)
    return doc


def doc_from_bytes(data):
    return fitz.open(stream=data, filetype="pdf")


def doc_to_bytes(doc):
    """저장용 (압축·정리)"""
    return doc.tobytes(garbage=3, deflate=True, deflate_images=True, deflate_fonts=True)


def write_doc(doc, path):
    data = doc_to_bytes(doc)
    with open(path, 'wb') as f:
        f.write(data)
    return len(data)


def new_doc():
    return fitz.open()


# ── 페이지 조작 ──
def rotate_pages(doc, rows, ang):
    for r in rows:
        pg = doc[r]
        pg.set_rotation((pg.rotation + ang) % 360)


def delete_pages(doc, rows):
    doc.delete_pages(rows)


def insert_blank(doc, after_row):
    ref = doc[after_row].rect if doc.page_count else fitz.Rect(0, 0, *A4)
    doc.new_page(pno=after_row + 1, width=ref.width, height=ref.height)
    return after_row + 1


def move_order(n, rows, d):
    """선택 행을 d(-1/+1)만큼 이동한 순서 리스트. 이동 불가면 None"""
    if not rows or (d < 0 and rows[0] == 0) or (d > 0 and rows[-1] == n - 1):
        return None
    order = list(range(n))
    for r in (rows if d < 0 else reversed(rows)):
        order[r + d], order[r] = order[r], order[r + d]
    return order


def reorder(doc, order):
    doc.select(order)


def extract_pages(doc, rows, path):
    new = fitz.open()
    for r in rows:
        new.insert_pdf(doc, from_page=r, to_page=r)
    new.save(path, garbage=3, deflate=True)


def split_each(n):
    return [[i] for i in range(n)]


def split_every(n, k):
    return [list(range(i, min(i + k, n))) for i in range(0, n, k)]


def split_doc(doc, groups, out_dir, base, task=None):
    task = task_or_null(task)
    outs = []
    for k, g in enumerate(groups):
        if task.cancelled():
            break
        new = fitz.open()
        new.insert_pdf(doc, from_page=g[0], to_page=g[-1])
        tag = f"p{g[0] + 1}" if len(g) == 1 else f"p{g[0] + 1}-{g[-1] + 1}"
        dst = unique_path(os.path.join(out_dir, f"{base}_{tag}.pdf"))
        new.save(dst, garbage=3, deflate=True)
        outs.append(dst)
        task.report(k + 1)
    return outs


# ── 내용 편집 ──
def view_to_pdf_point(page, x, y, zoom, dy=0.0):
    """미리보기 픽셀 좌표 → PDF 좌표 (회전 보정)"""
    p = fitz.Point(x / zoom, y / zoom + dy)
    return p * page.derotation_matrix


def insert_text(page, point, text, size, color, font=None):
    kw = dict(fontsize=size, color=color, rotate=page.rotation)
    if font:
        kw.update(fontname="kfont", fontfile=font)
    else:
        kw.update(fontname="helv")
    page.insert_text(point, text, **kw)


def redact_rect(page, rect):
    page.add_redact_annot(rect, fill=(1, 1, 1))
    page.apply_redactions(images=REDACT_KEEP_IMAGES)


def replace_text(doc, rows, old, new, font=None):
    """찾아 바꾸기. 바뀐 건수 반환"""
    cnt = 0
    for r in rows:
        page = doc[r]
        hits = page.search_for(old)
        if not hits:
            continue
        for h in hits:
            page.add_redact_annot(h, fill=(1, 1, 1))
        page.apply_redactions(images=REDACT_KEEP_IMAGES)
        if new:
            for h in hits:
                fs = max(4, h.height * 0.78)
                pt = fitz.Point(h.x0, h.y1 - h.height * 0.22)
                try:
                    kw = dict(fontsize=fs, color=(0, 0, 0))
                    if font:
                        kw.update(fontname="kfont", fontfile=font)
                    page.insert_text(pt, new, **kw)
                except Exception:
                    pass
        cnt += len(hits)
    return cnt


# ── 이미지 → PDF 페이지 ──
def images_to_pdf_pages(doc, paths, size_mode, margin_mm, quality):
    m = margin_mm * 72 / 25.4
    for p in paths:
        im = flatten_white(open_image(p))
        w, h = im.size
        b = io.BytesIO()
        im.save(b, 'JPEG', quality=quality, optimize=True)
        data = b.getvalue()
        if size_mode == "이미지 원본 크기":
            dpi = im.info.get('dpi', (96, 96))[0] or 96
            try:
                dpi = float(dpi) if float(dpi) >= 50 else 96
            except Exception:
                dpi = 96
            pw, ph = w * 72 / dpi, h * 72 / dpi
            mm = 0
        else:
            base = LETTER if size_mode.startswith("Letter") else A4
            if "가로" in size_mode or ("자동" in size_mode and w > h):
                pw, ph = base[1], base[0]
            else:
                pw, ph = base
            mm = m
        page = doc.new_page(width=pw, height=ph)
        page.insert_image(fitz.Rect(mm, mm, pw - mm, ph - mm), stream=data, keep_proportion=True)


def merge_into(doc, paths, password_cb=None):
    """PDF/이미지를 doc 뒤에 추가. [(파일명, 오류)] 반환"""
    errs = []
    for p in paths:
        try:
            if os.path.splitext(p)[1].lower() == '.pdf':
                doc.insert_pdf(open_pdf(p, password_cb))
            else:
                images_to_pdf_pages(doc, [p], "이미지 원본 크기", 0, 90)
        except Exception as ex:
            errs.append((os.path.basename(p), ex))
    return errs
