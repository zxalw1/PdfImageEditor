# -*- coding: utf-8 -*-
"""문서 변환 처리 (Qt 의존 없음)"""
import os
import re
import shutil
import tempfile
from dataclasses import dataclass

from PIL import Image

from .utils import fitz, EXT_OF, unique_path, out_path, task_or_null
from .pdf_ops import images_to_pdf_pages
from .office_com import OfficeConverter

NUM_RE = re.compile(r'-?[\d,]*\d(\.\d+)?')


def cell_value(c):
    if c is None:
        return None
    if not isinstance(c, str):
        return c
    s = c.replace('\n', ' ').strip()
    if NUM_RE.fullmatch(s) and not (len(s) > 1 and s.startswith('0') and '.' not in s):
        t = s.replace(',', '')
        try:
            return float(t) if '.' in t else int(t)
        except ValueError:
            pass
    return s


# ── PDF → 문서 ──
def pdf_to_xlsx(src, dst):
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter
    doc = fitz.open(src)
    wb = Workbook()
    wb.remove(wb.active)
    cnt = 0
    for i, page in enumerate(doc):
        try:
            tabs = page.find_tables().tables
        except Exception:
            tabs = []
        for k, t in enumerate(tabs):
            ws = wb.create_sheet(f"p{i + 1}_표{k + 1}"[:31])
            for row in t.extract():
                ws.append([cell_value(c) for c in row])
            cnt += 1
    if cnt == 0:
        ws = wb.create_sheet("텍스트")
        ws.append(["페이지", "내용"])
        for i, page in enumerate(doc):
            for line in page.get_text().splitlines():
                if line.strip():
                    ws.append([i + 1, cell_value(line)])
    for ws in wb.worksheets:
        for col in ws.columns:
            w = max((len(str(c.value)) for c in col if c.value is not None), default=4)
            ws.column_dimensions[get_column_letter(col[0].column)].width = min(60, max(6, w * 1.3 + 2))
    wb.save(dst)
    doc.close()
    return cnt


def pdf_to_txt(src, dst):
    doc = fitz.open(src)
    with open(dst, 'w', encoding='utf-8-sig') as f:
        for i, page in enumerate(doc):
            f.write(f"===== {i + 1} 페이지 =====\n{page.get_text()}\n")
    doc.close()


# PDF→Word(pdf2docx)는 v1.9.0 에서 제거 (opencv 등 약 160MB 의존성, 배포 용량 최적화)
PDF_DOC_TARGETS = [("Excel (.xlsx) - 표 추출", '.xlsx', pdf_to_xlsx),
                   ("텍스트 (.txt)", '.txt', pdf_to_txt)]


def pdfs_to_docs(paths, target_index, out_dir, task=None):
    task = task_or_null(task)
    _, ext, func = PDF_DOC_TARGETS[target_index]
    outs, errs = [], []
    for k, p in enumerate(paths):
        if task.cancelled():
            break
        task.report(k, os.path.basename(p))
        try:
            dst = out_path(p, out_dir, ext)
            func(p, dst)
            outs.append(dst)
        except Exception as ex:
            errs.append(f"{os.path.basename(p)}: {ex}")
        task.report(k + 1)
    return outs, errs


# ── PDF → 이미지 ──
@dataclass
class PdfImageJob:
    doc: object
    name: str
    pages: list
    out_dir: str
    base: str
    digits: int


def save_page_image(page, dst, fmt, dpi, quality):
    pix = page.get_pixmap(dpi=dpi, alpha=False)
    im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    if fmt == "PNG":
        im.save(dst, "PNG", optimize=True, dpi=(dpi, dpi))
    elif fmt == "JPG":
        im.save(dst, "JPEG", quality=quality, optimize=True, dpi=(dpi, dpi))
    else:
        im.save(dst, "WEBP", quality=quality)


def pdf_to_images(jobs, fmt, dpi, quality, task=None):
    """jobs: [PdfImageJob]. (저장 수, 오류 목록) 반환. 진행률은 전체 페이지 기준"""
    task = task_or_null(task)
    total, errs, done = 0, [], 0
    for job in jobs:
        if task.cancelled():
            break
        task.report(done, f"{job.name} 변환 중...")
        try:
            os.makedirs(job.out_dir, exist_ok=True)
            for i in job.pages:
                if task.cancelled():
                    break
                dst = unique_path(os.path.join(job.out_dir, f"{job.base}_p{str(i + 1).zfill(job.digits)}{EXT_OF[fmt]}"))
                save_page_image(job.doc[i], dst, fmt, dpi, quality)
                total += 1
                done += 1
                task.report(done)
        except Exception as ex:
            errs.append(f"{job.name}: {ex}")
    return total, errs


def pdf_to_single_images(jobs, fmt, dpi, quality, gap=20, task=None):
    """PDF 1개 → 모든 페이지를 세로로 이어붙인 이미지 1장. (저장 수, 오류 목록, 안내 목록)
    결과가 형식 한계(JPG 65500px, WEBP 16383px)를 넘으면 해상도를 자동으로 낮춘다"""
    from .image_ops import stitch_images, StitchOptions, FORMAT_MAX_SIDE, FIT_NONE, VERTICAL
    task = task_or_null(task)
    total, errs, notes, done = 0, [], [], 0
    limit = FORMAT_MAX_SIDE.get(fmt, 20000)
    for job in jobs:
        if task.cancelled():
            break
        try:
            rects = [job.doc[i].rect for i in job.pages]
            px = dpi / 72
            tall = sum(r.height * px for r in rects) + gap * (len(rects) - 1)
            wide = max(r.width * px for r in rects)
            use_dpi = dpi
            if max(tall, wide) > limit:
                use_dpi = max(20, int(dpi * (limit - gap * len(rects)) / max(tall, wide)))
                notes.append(f"{job.name}: 이미지가 너무 길어 해상도를 {dpi} → {use_dpi} DPI 로 낮춤")
            images = []
            for i in job.pages:
                if task.cancelled():
                    break
                task.report(done, f"{job.name} {i + 1}페이지 그리는 중...")
                pix = job.doc[i].get_pixmap(dpi=use_dpi, alpha=False)
                images.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
                done += 1
                task.report(done)
            if task.cancelled() or not images:
                break
            task.report(done, f"{job.name} 이어붙이는 중...")
            out = stitch_images(images, StitchOptions(VERTICAL, fit=FIT_NONE, gap=gap, bg=(229, 231, 235),
                                                      max_side=limit))
            os.makedirs(job.out_dir, exist_ok=True)
            dst = unique_path(os.path.join(job.out_dir, f"{job.base}_전체{EXT_OF[fmt]}"))
            if fmt == "PNG":
                out.save(dst, "PNG", optimize=True, dpi=(use_dpi, use_dpi))
            elif fmt == "JPG":
                out.save(dst, "JPEG", quality=quality, optimize=True, dpi=(use_dpi, use_dpi))
            else:
                out.save(dst, "WEBP", quality=quality)
            total += 1
        except Exception as ex:
            errs.append(f"{job.name}: {ex}")
    return total, errs, notes


# ── 이미지 → PDF ──
def images_to_pdf_each(paths, out_dir, size_mode, margin_mm, quality, task=None):
    task = task_or_null(task)
    ok, errs = 0, []
    for k, p in enumerate(paths):
        if task.cancelled():
            break
        try:
            doc = fitz.open()
            images_to_pdf_pages(doc, [p], size_mode, margin_mm, quality)
            doc.save(out_path(p, out_dir, '.pdf'), garbage=3, deflate=True)
            ok += 1
        except Exception as ex:
            errs.append(f"{os.path.basename(p)}: {ex}")
        task.report(k + 1)
    return ok, errs


def images_to_pdf_single(paths, dst, size_mode, margin_mm, quality, task=None):
    """(페이지 수, 오류 목록). 페이지가 0이면 저장하지 않음"""
    task = task_or_null(task)
    doc = fitz.open()
    errs = []
    for k, p in enumerate(paths):
        if task.cancelled():
            break
        try:
            images_to_pdf_pages(doc, [p], size_mode, margin_mm, quality)
        except Exception as ex:
            errs.append(f"{os.path.basename(p)}: {ex}")
        task.report(k + 1)
    n = doc.page_count
    if n:
        doc.save(dst, garbage=3, deflate=True)
    return n, errs


# ── Office → PDF ──
def merge_pdfs(paths, dst):
    doc = fitz.open()
    for o in paths:
        doc.insert_pdf(fitz.open(o))
    doc.save(dst, garbage=3, deflate=True)


def office_to_pdf(paths, engines, fit_width, out_dir, merged_dst=None, task=None):
    """(출력 목록, 오류 목록). merged_dst가 있으면 임시 변환 후 1개로 합침"""
    task = task_or_null(task)
    tmpdir = tempfile.mkdtemp() if merged_dst else None
    outs, errs = [], []
    try:
        with OfficeConverter(engines, fit_width) as cv:
            for k, p in enumerate(paths):
                if task.cancelled():
                    break
                task.report(k, os.path.basename(p))
                try:
                    dst = os.path.join(tmpdir, f"{k:04d}.pdf") if tmpdir else out_path(p, out_dir, '.pdf')
                    cv.convert(p, dst)
                    outs.append(dst)
                except Exception as ex:
                    errs.append(f"{os.path.basename(p)}: {ex}")
                task.report(k + 1)
        if merged_dst and outs:
            merge_pdfs(outs, merged_dst)
    finally:
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)
    return outs, errs
