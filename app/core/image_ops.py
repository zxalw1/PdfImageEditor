# -*- coding: utf-8 -*-
"""이미지 처리 (Qt 의존 없음)"""
import io
import os
from dataclasses import dataclass

from PIL import Image, ImageOps

from .utils import SAVE_FORMATS, EXT_OF, FMT_FROM_EXT, unique_path, task_or_null

# 회전 콤보 인덱스: 0 없음, 1 90°우, 2 90°좌, 3 180°
ROTATIONS = {1: Image.ROTATE_270, 2: Image.ROTATE_90, 3: Image.ROTATE_180}
# 크기 방식 인덱스
RESIZE_NONE, RESIZE_PCT, RESIZE_WIDTH, RESIZE_HEIGHT, RESIZE_BOX = range(5)


def open_image(path):
    im = Image.open(path)
    try:
        im = ImageOps.exif_transpose(im)
    except Exception:
        pass
    return im


def flatten_white(im):
    if im.mode in ('RGBA', 'LA') or (im.mode == 'P' and 'transparency' in im.info):
        im = im.convert('RGBA')
        bg = Image.new('RGB', im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        return bg
    return im.convert('RGB')


def prepare_mode(im, pf):
    if im.mode not in ('RGB', 'RGBA', 'L', 'LA', 'P'):
        try:
            im = im.convert('RGBA' if 'A' in im.mode else 'RGB')
        except Exception:
            im = im.convert('RGB')
    if pf in ('JPEG', 'BMP'):
        im = flatten_white(im)
    return im


def encode_image(im, pf, quality):
    b = io.BytesIO()
    kw = {}
    if pf == 'JPEG':
        kw = dict(quality=quality, optimize=True, progressive=True)
    elif pf == 'WEBP':
        kw = dict(quality=quality, method=6)
    elif pf == 'PNG':
        kw = dict(optimize=True)
    elif pf == 'TIFF':
        kw = dict(compression='tiff_lzw')
    elif pf == 'ICO':
        s = min(256, im.width, im.height)
        kw = dict(sizes=[(s, s)])
    im.save(b, pf, **kw)
    return b.getvalue()


def save_image(im, path, fmt, quality=90, target_kb=0):
    pf = SAVE_FORMATS[fmt]
    im = prepare_mode(im, pf)
    data = encode_image(im, pf, quality)
    if target_kb and len(data) > target_kb * 1024:
        limit = target_kb * 1024
        best = None
        if pf in ('JPEG', 'WEBP'):
            lo, hi = 5, quality
            while lo <= hi:
                mid = (lo + hi) // 2
                d = encode_image(im, pf, mid)
                if len(d) <= limit:
                    best, lo = d, mid + 1
                else:
                    hi = mid - 1
        if best is None:
            img = im
            q = min(quality, 60)
            while True:
                nw, nh = int(img.width * 0.85), int(img.height * 0.85)
                if nw < 32 or nh < 32:
                    break
                img = img.resize((nw, nh), Image.LANCZOS)
                d = encode_image(img, pf, q)
                best = d
                if len(d) <= limit:
                    break
        if best is not None:
            data = best
    with open(path, 'wb') as f:
        f.write(data)
    return len(data)


@dataclass
class TransformOptions:
    rotate: int = 0          # ROTATIONS 인덱스
    flip_x: bool = False
    flip_y: bool = False
    resize_mode: int = RESIZE_NONE
    pct: int = 50
    width: int = 1920
    height: int = 1080
    keep_ratio: bool = True
    no_upscale: bool = True


def transform_image(im, o: TransformOptions):
    if o.rotate in ROTATIONS:
        im = im.transpose(ROTATIONS[o.rotate])
    if o.flip_x:
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
    if o.flip_y:
        im = im.transpose(Image.FLIP_TOP_BOTTOM)

    mode = o.resize_mode
    w, h = im.size
    nw, nh = w, h
    if mode == RESIZE_PCT:
        k = o.pct / 100
        nw, nh = round(w * k), round(h * k)
    elif mode == RESIZE_WIDTH:
        nw = o.width
        nh = round(h * nw / w)
    elif mode == RESIZE_HEIGHT:
        nh = o.height
        nw = round(w * nh / h)
    elif mode == RESIZE_BOX:
        tw, th = o.width, o.height
        if o.keep_ratio:
            k = min(tw / w, th / h)
            nw, nh = round(w * k), round(h * k)
        else:
            nw, nh = tw, th
    if mode in (RESIZE_WIDTH, RESIZE_HEIGHT, RESIZE_BOX) and o.no_upscale and (nw > w or nh > h):
        nw, nh = w, h
    nw, nh = max(1, nw), max(1, nh)
    if (nw, nh) != (w, h):
        if im.mode == 'P':
            im = im.convert('RGBA')
        im = im.resize((nw, nh), Image.LANCZOS)
    return im


@dataclass
class BatchResult:
    ok: int = 0
    before: int = 0
    after: int = 0
    last_dir: str = ""
    errors: list = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


def batch_convert(paths, fmt_sel, quality, target_kb, suffix, out_dir, opts: TransformOptions, task=None):
    """fmt_sel: '원본 유지' 또는 SAVE_FORMATS 키. 진행률은 task.report(완료 수, 파일명)."""
    task = task_or_null(task)
    res = BatchResult()
    for i, p in enumerate(paths):
        if task.cancelled():
            break
        task.report(i, os.path.basename(p))
        try:
            fmt = FMT_FROM_EXT.get(os.path.splitext(p)[1].lower(), 'JPG') if fmt_sel == "원본 유지" else fmt_sel
            im = transform_image(open_image(p), opts)
            d = out_dir or os.path.join(os.path.dirname(p), "변환")
            os.makedirs(d, exist_ok=True)
            res.last_dir = d
            name = os.path.splitext(os.path.basename(p))[0] + suffix + EXT_OF[fmt]
            dst = unique_path(os.path.join(d, name))
            size = save_image(im, dst, fmt, quality, target_kb)
            res.before += os.path.getsize(p)
            res.after += size
            res.ok += 1
        except Exception as ex:
            res.errors.append(f"{os.path.basename(p)}: {ex}")
        task.report(i + 1)
    return res
