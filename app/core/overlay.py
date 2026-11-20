# -*- coding: utf-8 -*-
"""삽입 객체 레이어 (이미지·서명·도장) — 저장 전까지 객체로 관리 (Qt 의존 없음)

- 객체는 페이지의 xref(페이지 순서가 바뀌어도 유지)로 연결되고, 좌표는 '화면에 보이는(회전 후)' 페이지 좌표.
- 저장(또는 페이지 회전·추출·분할) 시 flatten 으로 PDF 에 합친다.
"""
import copy
import io
from dataclasses import dataclass, field

from PIL import Image

from .utils import fitz
from .image_ops import open_image

KINDS = {"image": "이미지", "signature": "서명", "stamp": "도장"}
MAX_PX = 2400          # 삽입 이미지 최대 변(px) — 용량 관리
MIN_SIDE = 6.0         # 최소 크기(pt)


@dataclass
class PlacedImage:
    id: int
    page_xref: int
    rect: tuple                 # (x0, y0, x1, y1) 회전 후 페이지 좌표(pt)
    data: bytes                 # PNG/JPEG
    px_size: tuple              # 원본 픽셀 크기 (w, h)
    kind: str = "image"

    @property
    def aspect(self):
        return self.px_size[0] / self.px_size[1]

    def frect(self):
        return fitz.Rect(self.rect)


@dataclass
class ObjectLayer:
    items: list = field(default_factory=list)
    _next: int = 1

    # ── 기본 ──
    def add(self, page_xref, rect, data, px_size, kind="image"):
        o = PlacedImage(self._next, page_xref, tuple(fitz.Rect(rect)), data, tuple(px_size), kind)
        self._next += 1
        self.items.append(o)
        return o

    def get(self, oid):
        return next((o for o in self.items if o.id == oid), None)

    def remove(self, oid):
        self.items = [o for o in self.items if o.id != oid]

    def on_page(self, xref):
        return [o for o in self.items if o.page_xref == xref]

    def clear(self):
        self.items = []

    def __len__(self):
        return len(self.items)

    def copy(self):
        return copy.deepcopy(self)

    # ── 조작 ──
    def hit(self, xref, x, y):
        """맨 위(나중에 넣은) 객체 우선"""
        for o in reversed(self.on_page(xref)):
            if o.frect().contains(fitz.Point(x, y)):
                return o
        return None

    def move(self, oid, dx, dy, bounds=None):
        o = self.get(oid)
        r = o.frect() + (dx, dy, dx, dy)
        if bounds is not None:
            b = fitz.Rect(bounds)
            # 페이지 밖으로 완전히 나가지 않게 (최소 절반은 페이지 안)
            ox = min(0, b.x1 - (r.x0 + r.width / 2)) + max(0, b.x0 - (r.x1 - r.width / 2))
            oy = min(0, b.y1 - (r.y0 + r.height / 2)) + max(0, b.y0 - (r.y1 - r.height / 2))
            r = r + (ox, oy, ox, oy)
        o.rect = tuple(r)

    def resize(self, oid, handle, x, y, keep_aspect=True):
        """handle: 'tl','tr','bl','br' 모서리를 (x, y)로. 반대 모서리 고정"""
        o = self.get(oid)
        r = o.frect()
        ax = r.x1 if "l" in handle else r.x0         # 고정점
        ay = r.y1 if "t" in handle else r.y0
        w = max(MIN_SIDE, abs(x - ax))
        h = max(MIN_SIDE, abs(y - ay))
        if keep_aspect:
            if w / h > o.aspect:
                w = h * o.aspect
            else:
                h = w / o.aspect
        x0 = ax - w if "l" in handle else ax
        y0 = ay - h if "t" in handle else ay
        o.rect = (x0, y0, x0 + w, y0 + h)

    def drop_missing(self, doc):
        alive = {doc[i].xref for i in range(doc.page_count)}
        self.items = [o for o in self.items if o.page_xref in alive]

    # ── PDF 에 합치기 ──
    def flatten(self, doc, page_xrefs=None):
        """객체를 PDF 에 그려 넣고 레이어에서 제거. page_xrefs 가 있으면 그 페이지만"""
        by_xref = {doc[i].xref: doc[i] for i in range(doc.page_count)}
        keep = []
        for o in self.items:
            page = by_xref.get(o.page_xref)
            if page is None:
                continue                                  # 삭제된 페이지
            if page_xrefs is not None and o.page_xref not in page_xrefs:
                keep.append(o)
                continue
            draw_image(page, o.frect(), o.data)
        self.items = keep


def draw_image(page, display_rect, data):
    """화면(회전 후) 좌표 사각형에 이미지를 바로 선 방향으로 그린다"""
    unrot = fitz.Rect(display_rect) * page.derotation_matrix
    page.insert_image(unrot, stream=data, rotate=page.rotation, keep_proportion=False, overlay=True)


def flattened_copy(doc, layer):
    """원본·레이어는 그대로 두고, 객체가 합쳐진 사본 문서 (추출·분할용)"""
    tmp = fitz.open(stream=doc.tobytes(), filetype="pdf")
    if len(layer):
        layer.copy().flatten(tmp)
    return tmp


# ── 저장된 서명 (%LOCALAPPDATA%\PdfImageEditor\signatures\*.png) ──
def signature_dir():
    import os
    from .utils import LOG_DIR
    d = os.path.join(LOG_DIR, "signatures")
    os.makedirs(d, exist_ok=True)
    return d


def list_signatures():
    import os
    d = signature_dir()
    fs = [os.path.join(d, f) for f in os.listdir(d) if f.lower().endswith(".png")]
    return sorted(fs, key=os.path.getmtime, reverse=True)


def save_signature(data):
    import os
    import time
    p = os.path.join(signature_dir(), time.strftime("서명_%Y%m%d_%H%M%S.png"))
    with open(p, "wb") as f:
        f.write(data)
    return p


# ── 이미지 준비 ──
def remove_white_background(im, threshold=225, soft=30):
    """흰 배경을 투명하게 (스캔한 서명·도장용). threshold 이상 밝은 픽셀은 투명, 경계는 부드럽게"""
    im = im.convert("RGBA")
    r, g, b, a = im.split()
    lum = Image.merge("RGB", (r, g, b)).convert("L")
    lo = threshold - soft

    def alpha_of(v):
        if v >= threshold:
            return 0
        if v <= lo:
            return 255
        return int(255 * (threshold - v) / soft)
    mask = lum.point(alpha_of)
    from PIL import ImageChops
    im.putalpha(ImageChops.multiply(a, mask))
    return im


def trim_transparent(im, pad=4):
    if im.mode != "RGBA":
        return im
    box = im.getchannel("A").getbbox()
    if not box:
        return im
    x0, y0, x1, y1 = box
    return im.crop((max(0, x0 - pad), max(0, y0 - pad), min(im.width, x1 + pad), min(im.height, y1 + pad)))


def prepare_image(src, remove_bg=False, threshold=225):
    """파일 경로 또는 bytes → (PNG/JPEG bytes, (w, h)). EXIF 회전 보정·크기 제한·투명 유지"""
    im = open_image(src) if isinstance(src, str) else Image.open(io.BytesIO(src))
    if remove_bg:
        im = trim_transparent(remove_white_background(im, threshold))
    has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
    if max(im.size) > MAX_PX:
        im = im.copy()
        im.thumbnail((MAX_PX, MAX_PX), Image.LANCZOS)
    out = io.BytesIO()
    if has_alpha:
        im.convert("RGBA").save(out, "PNG", optimize=True)
    else:
        im.convert("RGB").save(out, "JPEG", quality=92, optimize=True)
    return out.getvalue(), im.size


def default_rect(page_rect, px_size, center=None, frac=0.3, dpi_hint=96):
    """기본 배치 크기: 원본 크기(96dpi 기준)와 페이지 폭의 frac 중 작은 쪽, 비율 유지"""
    pr = fitz.Rect(page_rect)
    w_px, h_px = px_size
    w = min(w_px * 72 / dpi_hint, pr.width * frac)
    h = w * h_px / w_px
    if h > pr.height * 0.5:
        h = pr.height * 0.5
        w = h * w_px / h_px
    cx, cy = center if center else (pr.x0 + pr.width / 2, pr.y0 + pr.height / 2)
    r = fitz.Rect(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
    # 페이지 안으로
    dx = max(pr.x0 - r.x0, 0) - max(r.x1 - pr.x1, 0)
    dy = max(pr.y0 - r.y0, 0) - max(r.y1 - pr.y1, 0)
    return r + (dx, dy, dx, dy)


def rect_from_drag(x0, y0, x1, y1, aspect):
    """드래그한 사각형 안에 비율 유지로 맞춤 (시작점 기준)"""
    w, h = abs(x1 - x0), abs(y1 - y0)
    if w / max(h, 1e-6) > aspect:
        w = h * aspect
    else:
        h = w / aspect
    sx = x0 if x1 >= x0 else x0 - w
    sy = y0 if y1 >= y0 else y0 - h
    return fitz.Rect(sx, sy, sx + w, sy + h)
