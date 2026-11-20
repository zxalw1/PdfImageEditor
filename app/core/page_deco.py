# -*- coding: utf-8 -*-
"""페이지 꾸미기: 페이지 번호, 머리글·바닥글, 워터마크(글자/이미지) (Qt 의존 없음)

좌표는 '화면에 보이는(회전 후)' 페이지 기준으로 계산하고, 회전된 페이지도 바로 선 방향으로 넣는다.
"""
import datetime
import io
import os
from dataclasses import dataclass, field

from PIL import Image

from .utils import fitz, korean_font, parse_ranges

POSITIONS = ["아래 가운데", "아래 오른쪽", "아래 왼쪽", "위 가운데", "위 오른쪽", "위 왼쪽"]
NUM_FORMATS = {"1": "{n}", "1 / 10": "{n} / {total}", "- 1 -": "- {n} -", "1페이지": "{n}페이지",
               "1쪽": "{n}쪽", "Page 1": "Page {n}"}
PLACEHOLDERS = "{page} 쪽번호 · {total} 전체 쪽수 · {date} 오늘 날짜 · {file} 파일명"


@dataclass
class NumberOpts:
    enabled: bool = False
    fmt: str = "1 / 10"
    position: str = "아래 가운데"
    start: int = 1
    size: float = 10
    skip_first: bool = False


@dataclass
class HeaderFooterOpts:
    enabled: bool = False
    header: tuple = ("", "", "")         # (왼쪽, 가운데, 오른쪽)
    footer: tuple = ("", "", "")
    size: float = 9


@dataclass
class WatermarkOpts:
    enabled: bool = False
    kind: str = "text"                   # text / image
    text: str = "대외비"
    size: float = 60
    color: tuple = (0.55, 0.55, 0.55)
    opacity: float = 0.25
    angle: float = 45
    image: bytes = None
    scale: float = 0.5                   # 이미지 폭 = 페이지 폭 × scale
    behind: bool = False                 # 본문 뒤로


@dataclass
class DecoOptions:
    numbers: NumberOpts = field(default_factory=NumberOpts)
    hf: HeaderFooterOpts = field(default_factory=HeaderFooterOpts)
    wm: WatermarkOpts = field(default_factory=WatermarkOpts)
    color: tuple = (0.2, 0.2, 0.2)
    margin: float = 28
    pages: str = ""                      # 비우면 전체 (예: 2-5)
    filename: str = ""

    @property
    def any_enabled(self):
        return self.numbers.enabled or self.hf.enabled or self.wm.enabled


# ── 글자 배치 ──
def _font():
    return korean_font()


def text_width(text, size, fontfile=None):
    ff = fontfile or _font()
    if ff:
        return fitz.Font(fontfile=ff).text_length(text, size)
    return fitz.get_text_length(text, "helv", size)


def _font_kw(fontfile=None):
    ff = fontfile or _font()
    return dict(fontname="kdeco", fontfile=ff) if ff else dict(fontname="helv")


def place_text(page, text, vpos, hpos, size, color, margin, opacity=1.0):
    """vpos: top/bottom, hpos: left/center/right — 화면 기준 위치에 한 줄 글자"""
    if not text:
        return
    r = page.rect
    w = text_width(text, size)
    x = {"left": margin, "center": (r.width - w) / 2, "right": r.width - margin - w}[hpos]
    y = margin + size if vpos == "top" else r.height - margin
    pt = fitz.Point(x, y) * page.derotation_matrix
    page.insert_text(pt, text, fontsize=size, color=color, rotate=page.rotation, fill_opacity=opacity,
                     **_font_kw())


def _pos(position):
    v = "top" if position.startswith("위") else "bottom"
    h = {"가운데": "center", "오른쪽": "right", "왼쪽": "left"}[position.split()[1]]
    return v, h


def expand(template, n, total, filename="", date=None):
    date = date or datetime.date.today().strftime("%Y-%m-%d")
    return (template.replace("{page}", str(n)).replace("{total}", str(total))
            .replace("{date}", date).replace("{file}", filename))


# ── 워터마크 ──
def text_watermark(page, o: WatermarkOpts):
    r = page.rect
    c = fitz.Point(r.width / 2, r.height / 2)
    w = text_width(o.text, o.size)
    start = fitz.Point(c.x - w / 2, c.y + o.size * 0.35)
    page.insert_text(start * page.derotation_matrix, o.text, fontsize=o.size, color=o.color,
                     rotate=page.rotation, morph=(c * page.derotation_matrix, fitz.Matrix(o.angle)),
                     fill_opacity=o.opacity, overlay=not o.behind, **_font_kw())


def _faded_png(data, opacity):
    im = Image.open(io.BytesIO(data)).convert("RGBA")
    a = im.getchannel("A").point(lambda v: int(v * opacity))
    im.putalpha(a)
    b = io.BytesIO()
    im.save(b, "PNG", optimize=True)
    return b.getvalue(), im.size


def image_watermark(page, o: WatermarkOpts, _cache={}):
    key = (id(o.image), o.opacity)
    if key not in _cache:
        _cache.clear()
        _cache[key] = _faded_png(o.image, o.opacity)
    data, (iw, ih) = _cache[key]
    r = page.rect
    w = r.width * o.scale
    h = w * ih / iw
    disp = fitz.Rect((r.width - w) / 2, (r.height - h) / 2, (r.width + w) / 2, (r.height + h) / 2)
    page.insert_image(disp * page.derotation_matrix, stream=data, rotate=page.rotation,
                      keep_proportion=False, overlay=not o.behind)


# ── 적용 ──
def target_pages(opts: DecoOptions, page_count):
    if not opts.pages.strip():
        return list(range(page_count))
    return sorted({i for g in parse_ranges(opts.pages, page_count) for i in g})


class _Ctx:
    def __init__(self, opts, page_count):
        self.targets = target_pages(opts, page_count)
        nums = self.targets[1:] if opts.numbers.skip_first and self.targets else self.targets
        self.num_rank = {i: k for k, i in enumerate(nums)}
        self.total = len(nums) + opts.numbers.start - 1
        self.all_total = page_count


def decorate_page(page, index, opts: DecoOptions, ctx: _Ctx):
    """index: 문서 안 페이지 번호(0부터). ctx 는 전체 문서 기준 번호 계산용"""
    if index not in ctx.targets:
        return
    if opts.wm.enabled:
        if opts.wm.kind == "image" and opts.wm.image:
            image_watermark(page, opts.wm)
        elif opts.wm.text.strip():
            text_watermark(page, opts.wm)
    n = opts.numbers
    if n.enabled and index in ctx.num_rank:
        v, h = _pos(n.position)
        txt = NUM_FORMATS.get(n.fmt, n.fmt).format(n=n.start + ctx.num_rank[index], total=ctx.total)
        place_text(page, txt, v, h, n.size, opts.color, opts.margin)
    hf = opts.hf
    if hf.enabled:
        for vpos, texts in (("top", hf.header), ("bottom", hf.footer)):
            for hpos, t in zip(("left", "center", "right"), texts):
                if t.strip():
                    # 페이지 번호와 같은 줄이면 겹치지 않게 한 줄 안쪽으로
                    m = opts.margin
                    if n.enabled and _pos(n.position) == (vpos, hpos):
                        m += n.size * 1.6
                    place_text(page, expand(t, index + 1, ctx.all_total, opts.filename), vpos, hpos,
                               hf.size, opts.color, m)


def decorate(doc, opts: DecoOptions, task=None):
    ctx = _Ctx(opts, doc.page_count)
    for k, i in enumerate(ctx.targets):
        if task is not None:
            if task.cancelled():
                break
            task.report(k + 1)
        decorate_page(doc[i], i, opts, ctx)
    return len(ctx.targets)


def preview_page(doc, index, opts: DecoOptions, zoom=0.6):
    """index 페이지만 사본으로 꾸며서 Pixmap 반환 (원본 문서는 그대로)"""
    tmp = fitz.open()
    tmp.insert_pdf(doc, from_page=index, to_page=index)
    decorate_page(tmp[0], index, opts, _Ctx(opts, doc.page_count))
    return tmp[0].get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)


def filename_of(path):
    return os.path.splitext(os.path.basename(path or "문서.pdf"))[0]
