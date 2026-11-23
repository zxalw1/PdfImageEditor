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


# ── 사진 이어붙이기 ──
VERTICAL, HORIZONTAL, GRID = "vertical", "horizontal", "grid"
FIT_MIN, FIT_MAX, FIT_NONE = "min", "max", "none"
FORMAT_MAX_SIDE = {"JPG": 65500, "WEBP": 16383, "PNG": 100000, "BMP": 30000, "TIFF": 100000,
                   "GIF": 65535, "ICO": 256}


@dataclass
class StitchOptions:
    direction: str = VERTICAL     # vertical(아래로) / horizontal(옆으로) / grid(격자)
    cols: int = 2                 # 격자 열 수
    fit: str = FIT_MIN            # 세로: 폭을 / 가로: 높이를 / 격자: 칸 크기를  min·max 에 맞춤, none=원본
    gap: int = 0                  # 사진 사이 간격(px)
    margin: int = 0               # 바깥 여백(px)
    bg: tuple = (255, 255, 255)   # 배경색 (None = 투명)
    max_side: int = 20000         # 결과 최대 변(px) — 넘으면 전체를 비율대로 줄임


def _stitch_sizes(sizes, o: StitchOptions):
    """각 사진의 붙일 크기 [(w, h)] 계산 (비율 유지)"""
    if o.fit == FIT_NONE:
        return list(sizes)
    pick = min if o.fit == FIT_MIN else max
    out = []
    if o.direction == VERTICAL:
        tw = pick(w for w, _ in sizes)
        out = [(tw, max(1, round(h * tw / w))) for w, h in sizes]
    elif o.direction == HORIZONTAL:
        th = pick(h for _, h in sizes)
        out = [(max(1, round(w * th / h)), th) for w, h in sizes]
    else:                                     # 격자: 칸 = 기준 폭, 사진은 칸 안에 맞춤
        cw = pick(w for w, _ in sizes)
        out = [(cw, max(1, round(h * cw / w))) for w, h in sizes]
    return out


def stitch_layout(sizes, o: StitchOptions):
    """(전체 크기, 각 사진 위치·크기 [(x, y, w, h)]) — 그리기 전에 미리 계산 (미리보기·크기 검사용)"""
    s = _stitch_sizes(sizes, o)
    g, m = max(0, o.gap), max(0, o.margin)
    boxes = []
    if o.direction == VERTICAL:
        W = max(w for w, _ in s)
        y = m
        for w, h in s:
            boxes.append(((W - w) // 2 + m, y, w, h))
            y += h + g
        total = (W + 2 * m, y - g + m)
    elif o.direction == HORIZONTAL:
        H = max(h for _, h in s)
        x = m
        for w, h in s:
            boxes.append((x, (H - h) // 2 + m, w, h))
            x += w + g
        total = (x - g + m, H + 2 * m)
    else:
        cols = max(1, min(o.cols, len(s)))
        cw = max(w for w, _ in s)
        rows = [s[i:i + cols] for i in range(0, len(s), cols)]
        y = m
        for r in rows:
            rh = max(h for _, h in r)
            for k, (w, h) in enumerate(r):
                boxes.append((m + k * (cw + g) + (cw - w) // 2, y + (rh - h) // 2, w, h))
            y += rh + g
        total = (m * 2 + cols * cw + (cols - 1) * g, y - g + m)
    return total, boxes


def stitch_images(images, o: StitchOptions, task=None):
    """PIL 이미지 목록을 한 장으로. max_side 를 넘으면 전체를 같은 비율로 줄여서 그림"""
    task = task_or_null(task)
    if not images:
        raise ValueError("이어붙일 사진이 없습니다")
    (W, H), boxes = stitch_layout([im.size for im in images], o)
    k = min(1.0, o.max_side / max(W, H))
    orig = boxes
    while max(W, H) > o.max_side:            # 크기 줄여서 다시 배치 (간격·여백도 같이, 내림으로 한계 안 넘게)
        small = StitchOptions(o.direction, o.cols, FIT_NONE, int(o.gap * k), int(o.margin * k), o.bg, o.max_side)
        sizes = [(max(1, int(w * k)), max(1, int(h * k))) for (_x, _y, w, h) in orig]
        (W, H), boxes = stitch_layout(sizes, small)
        k *= 0.999
    transparent = o.bg is None
    canvas = Image.new("RGBA" if transparent else "RGB", (W, H), (0, 0, 0, 0) if transparent else tuple(o.bg))
    for i, (im, (x, y, w, h)) in enumerate(zip(images, boxes)):
        if task.cancelled():
            raise InterruptedError("취소했습니다")
        task.report(i, f"{i + 1}/{len(images)} 붙이는 중...")
        src = im if im.mode in ("RGB", "RGBA") else im.convert("RGBA")
        if src.size != (w, h):
            src = src.resize((w, h), Image.LANCZOS)
        if src.mode == "RGBA":
            canvas.paste(src, (x, y), src)
        else:
            canvas.paste(src, (x, y))
        task.report(i + 1)
    return canvas


def stitch_files(paths, dst, fmt, o: StitchOptions, quality=90, target_kb=0, task=None):
    """파일들을 이어붙여 저장. (저장 크기 bytes, (가로, 세로)) 반환"""
    limit = FORMAT_MAX_SIDE.get(fmt, 20000)
    o = StitchOptions(**{**o.__dict__, "max_side": min(o.max_side, limit)})
    images = [open_image(p) for p in paths]
    out = stitch_images(images, o, task)
    size = save_image(out, dst, fmt, quality, target_kb)
    return size, out.size
