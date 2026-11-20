# -*- coding: utf-8 -*-
"""PDF 용량 줄이기 — 이미지 해상도(DPI)·품질 재압축 (Qt 의존 없음)"""
from dataclasses import dataclass

from .utils import fitz
from .pdf_ops import doc_to_bytes

PRESETS = [
    ("화면용 · 가장 작게 (96 DPI)", 96, 55),
    ("일반 문서 (150 DPI)", 150, 75),
    ("인쇄용 (220 DPI)", 220, 85),
]


@dataclass
class CompressResult:
    before: int
    after: int
    data: bytes

    @property
    def saved_pct(self):
        return (1 - self.after / self.before) * 100 if self.before else 0.0


def image_dpis(doc):
    """페이지에 놓인 이미지들의 실제 DPI 목록 (진단용)"""
    out = []
    for page in doc:
        for img in page.get_images(full=True):
            xref, w = img[0], img[2]
            for r in page.get_image_rects(xref):
                if r.width > 0:
                    out.append(w / (r.width / 72))
    return out


def compress_doc_bytes(data, dpi=150, quality=75, gray=False):
    """PDF bytes → 이미지 재압축 + 정리한 bytes. dpi 보다 높은 이미지만 dpi 로 줄인다"""
    d = fitz.open(stream=data, filetype="pdf")
    d.rewrite_images(dpi_threshold=int(dpi * 1.1) + 1, dpi_target=dpi, quality=quality,
                     set_to_gray=gray)
    return doc_to_bytes(d)


def compress(doc, dpi=150, quality=75, gray=False, task=None):
    """원본 doc 는 그대로. 결과 bytes 와 전후 용량"""
    if task is not None:
        task.report(0, "현재 용량 계산 중...")
    before = doc_to_bytes(doc)
    if task is not None:
        task.report(1, "이미지 다시 압축 중...")
    after = compress_doc_bytes(before, dpi, quality, gray)
    if task is not None:
        task.report(2)
    if len(after) >= len(before):        # 줄지 않으면 원본 유지
        after = before
    return CompressResult(len(before), len(after), after)
