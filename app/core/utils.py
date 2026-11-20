# -*- coding: utf-8 -*-
"""공통 상수·유틸 (Qt 의존 없음)"""
import os
import re
import sys

try:
    import pymupdf as fitz  # noqa: F401
except ImportError:  # pragma: no cover
    import fitz  # noqa: F401

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIF = True
except Exception:  # pragma: no cover
    HEIF = False

IMG_EXT = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif', '.tif', '.tiff', '.ico'}
if HEIF:
    IMG_EXT |= {'.heic', '.heif'}
PDF_EXT = {'.pdf'}

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\malgun.ttf",
    r"C:\Windows\Fonts\gulim.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
]

IMG_FILTER = "이미지 (" + " ".join("*" + e for e in sorted(IMG_EXT)) + ")"
PDF_FILTER = "PDF (*.pdf)"

SAVE_FORMATS = {'JPG': 'JPEG', 'PNG': 'PNG', 'WEBP': 'WEBP', 'BMP': 'BMP',
                'TIFF': 'TIFF', 'GIF': 'GIF', 'ICO': 'ICO'}
EXT_OF = {'JPG': '.jpg', 'PNG': '.png', 'WEBP': '.webp', 'BMP': '.bmp',
          'TIFF': '.tif', 'GIF': '.gif', 'ICO': '.ico'}
FMT_FROM_EXT = {'.jpg': 'JPG', '.jpeg': 'JPG', '.png': 'PNG', '.webp': 'WEBP', '.bmp': 'BMP',
                '.tif': 'TIFF', '.tiff': 'TIFF', '.gif': 'GIF', '.ico': 'ICO',
                '.heic': 'JPG', '.heif': 'JPG'}

A4 = (595.28, 841.89)
LETTER = (612.0, 792.0)

# 소스 실행 시 프로젝트 루트(main.py 위치), exe 실행 시 PyInstaller 임시 폴더
ROOT_DIR = getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
LOG_DIR = os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'), 'PdfImageEditor')


def resource_path(*parts):
    return os.path.join(ROOT_DIR, *parts)


def korean_font():
    for f in FONT_CANDIDATES:
        if os.path.exists(f):
            return f
    return None


def parse_ranges(text, n):
    """'1-3,5,7-' -> [[0,1,2],[4],[6..n-1]]"""
    groups = []
    for part in re.split(r'[,\s]+', text.strip()):
        if not part:
            continue
        m = re.fullmatch(r'(\d*)-(\d*)', part)
        if m:
            a = int(m.group(1)) if m.group(1) else 1
            b = int(m.group(2)) if m.group(2) else n
        elif part.isdigit():
            a = b = int(part)
        else:
            raise ValueError(f"잘못된 범위: {part}")
        a, b = max(1, a), min(n, b)
        if a > b:
            raise ValueError(f"잘못된 범위: {part}")
        groups.append(list(range(a - 1, b)))
    return groups


def human(n):
    n = float(n)
    for u in ['B', 'KB', 'MB', 'GB']:
        if n < 1024:
            return f"{n:.0f}{u}" if u == 'B' else f"{n:.1f}{u}"
        n /= 1024
    return f"{n:.1f}TB"


def unique_path(path):
    base, ext = os.path.splitext(path)
    p, i = path, 1
    while os.path.exists(p):
        p = f"{base}_{i}{ext}"
        i += 1
    return p


def collect_files(paths, exts):
    out = []
    for p in paths:
        if os.path.isdir(p):
            for f in sorted(os.listdir(p)):
                fp = os.path.join(p, f)
                if os.path.isfile(fp) and os.path.splitext(f)[1].lower() in exts:
                    out.append(fp)
        elif os.path.splitext(p)[1].lower() in exts:
            out.append(p)
    return out


def out_path(src, out_dir, ext, default_sub="변환"):
    d = out_dir or os.path.join(os.path.dirname(src), default_sub)
    os.makedirs(d, exist_ok=True)
    return unique_path(os.path.join(d, os.path.splitext(os.path.basename(src))[0] + ext))


def with_ext(path, ext):
    return path if path.lower().endswith(ext) else path + ext


class NullTask:
    """진행률 보고/취소 인터페이스 기본 구현. UI 워커(TaskWorker)도 같은 메서드를 가진다."""

    def report(self, value, label=None):
        pass

    def cancelled(self):
        return False


def task_or_null(task):
    return task if task is not None else NullTask()
