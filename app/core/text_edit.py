# -*- coding: utf-8 -*-
"""PDF 기존 텍스트 직접 수정 (Qt 의존 없음)

흐름: text_units(page, level) 로 줄/문단 단위 영역 추출 → unit_at() 으로 클릭 위치 찾기
      → replace_unit() 이 원래 글자만 지우고(배경·선·이미지 유지) 같은 위치·크기·색으로 새 글자 삽입.
좌표는 모두 '회전 전' 페이지 좌표 (PyMuPDF get_text 와 동일).
"""
import os
import re
from dataclasses import dataclass, field

from .utils import fitz, FONT_CANDIDATES

LINE, BLOCK = "line", "block"

# PDF 기본 14 글꼴 → PyMuPDF 내장 이름
BASE14 = {
    "helvetica": "helv", "helvetica-bold": "hebo", "helvetica-oblique": "heit", "helvetica-boldoblique": "hebi",
    "arial": "helv", "arial-bold": "hebo", "arialmt": "helv", "arial-boldmt": "hebo",
    "times-roman": "tiro", "times-bold": "tibo", "times-italic": "tiit", "times-bolditalic": "tibi",
    "timesnewroman": "tiro", "timesnewromanpsmt": "tiro", "timesnewromanps-boldmt": "tibo",
    "courier": "cour", "courier-bold": "cobo", "courier-oblique": "coit", "courier-boldoblique": "cobi",
    "couriernew": "cour", "couriernewpsmt": "cour",
}
FLAG_ITALIC, FLAG_BOLD = 2, 16
BOLD_FONT_CANDIDATES = [r"C:\Windows\Fonts\malgunbd.ttf"]


@dataclass
class TextUnit:
    kind: str                 # LINE / BLOCK
    page_no: int
    bbox: object              # fitz.Rect (회전 전 좌표)
    text: str                 # 여러 줄이면 '\n' 로 연결
    size: float
    color: tuple              # (r, g, b) 0~1
    font: str                 # PDF 상의 글꼴 이름
    flags: int
    origins: list = field(default_factory=list)   # 각 줄 기준선 시작점 [(x, y)]
    line_rects: list = field(default_factory=list)

    @property
    def line_pitch(self):
        if len(self.origins) >= 2:
            ys = [o[1] for o in self.origins]
            return max(self.size * 0.9, (ys[-1] - ys[0]) / (len(ys) - 1))
        return self.size * 1.25

    @property
    def bold(self):
        return bool(self.flags & FLAG_BOLD) or "bold" in self.font.lower()


def int_to_rgb(c):
    return ((c >> 16) & 255) / 255, ((c >> 8) & 255) / 255, (c & 255) / 255


def _norm(name):
    name = re.sub(r"^[A-Z]{6}\+", "", name or "")
    return re.sub(r"[\s_\-,]", "", name).lower()


def _dominant_span(spans):
    spans = [s for s in spans if s["text"].strip()] or spans
    return max(spans, key=lambda s: len(s["text"].strip()))


def page_has_text(page):
    return bool(page.get_text("text").strip())


def _line_size(ln):
    return _dominant_span(ln["spans"])["size"]


def horizontal_rules(page):
    """표 테두리·칸 배경 경계 등 가로선 [(x0, x1, y)]"""
    rules = []
    try:
        drawings = page.get_drawings()
    except Exception:
        return rules
    for dr in drawings:
        for it in dr["items"]:
            if it[0] == "l":
                a, b = it[1], it[2]
                if abs(a.y - b.y) <= 1.0 and abs(a.x - b.x) >= 5:
                    rules.append((min(a.x, b.x), max(a.x, b.x), (a.y + b.y) / 2))
            elif it[0] == "re":
                r = fitz.Rect(it[1])
                if r.width < 5:
                    continue
                if r.height <= 2:
                    rules.append((r.x0, r.x1, (r.y0 + r.y1) / 2))
                else:                               # 칸 배경 등 면: 위·아래 경계
                    rules += [(r.x0, r.x1, r.y0), (r.x0, r.x1, r.y1)]
    return rules


def _ruled_between(rules, upper, lower):
    y_top, y_bot = upper["bbox"][3] - 1.0, lower["bbox"][1] + 1.0
    x0 = max(upper["bbox"][0], lower["bbox"][0])
    x1 = min(upper["bbox"][2], lower["bbox"][2])
    return any(y_top <= y <= y_bot and rx0 < x1 and rx1 > x0 for rx0, rx1, y in rules)


def _group_paragraphs(lines, rules=()):
    """줄들을 문단으로 묶는다 (MuPDF 블록 구분은 줄 간격에 따라 들쭉날쭉해서 직접 판단)
    같은 문단 조건: 바로 위 줄과 글자 크기 비슷(±15%), 기준선 간격 ≤ 크기×2.2 (Word 기본 줄 간격 ≈ 2.0),
    왼쪽 정렬이 같거나 가로로 겹침, 두 줄 사이에 가로선(표 테두리) 없음"""
    groups = []
    for ln in sorted(lines, key=lambda l: (l["spans"][0]["origin"][1], l["bbox"][0])):
        size = _line_size(ln)
        x0, x1 = ln["bbox"][0], ln["bbox"][2]
        y = _first_span(ln)["origin"][1]
        best, best_dy = None, None
        for g in groups:
            last = g[-1]
            ls = _line_size(last)
            dy = y - _first_span(last)["origin"][1]
            if not (0 < dy <= max(size, ls) * 2.2) or not (0.85 <= size / ls <= 1.15):
                continue
            if rules and _ruled_between(rules, last, ln):
                continue
            lx0, lx1 = last["bbox"][0], last["bbox"][2]
            overlap = min(x1, lx1) - max(x0, lx0)
            if abs(x0 - lx0) <= size * 1.2 or overlap > 0.5 * min(x1 - x0, lx1 - lx0):
                if best is None or dy < best_dy:
                    best, best_dy = g, dy
        if best is not None:
            best.append(ln)
        else:
            groups.append([ln])
    return groups


def text_units(page, level=LINE):
    """페이지의 수정 가능한 텍스트 단위 목록. 가로쓰기 줄만 대상"""
    out = []
    d = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_PRESERVE_LIGATURES)
    all_lines = []
    for b in d["blocks"]:
        if b.get("type", 0) != 0:
            continue
        all_lines += [ln for ln in b["lines"]
                      if abs(ln["dir"][1]) < 1e-3 and ln["dir"][0] > 0
                      and "".join(s["text"] for s in ln["spans"]).strip()]
    if all_lines:
        groups = ([[ln] for ln in all_lines] if level == LINE
                  else _group_paragraphs(all_lines, horizontal_rules(page)))
        for g in groups:
            spans = [s for ln in g for s in ln["spans"]]
            dom = _dominant_span(spans)
            rect = fitz.Rect()
            for ln in g:
                rect |= fitz.Rect(ln["bbox"])
            texts = ["".join(s["text"] for s in ln["spans"]).rstrip() for ln in g]
            origins = [tuple(_first_span(ln)["origin"]) for ln in g]
            out.append(TextUnit(
                kind=level, page_no=page.number, bbox=rect, text="\n".join(texts),
                size=round(dom["size"], 2), color=int_to_rgb(dom["color"]), font=dom["font"], flags=dom["flags"],
                origins=origins, line_rects=[fitz.Rect(ln["bbox"]) for ln in g]))
    return out


def _first_span(line):
    for s in line["spans"]:
        if s["text"].strip():
            return s
    return line["spans"][0]


def unit_at(units, x, y, pad=1.5):
    """(x, y) 회전 전 좌표에 있는 단위. 겹치면 가장 작은 것"""
    pt = fitz.Point(x, y)
    hits = [u for u in units if (fitz.Rect(u.bbox) + (-pad, -pad, pad, pad)).contains(pt)]
    return min(hits, key=lambda u: u.bbox.width * u.bbox.height) if hits else None


# ── 글꼴 ──
def _embedded_font(doc, page, font_name):
    """페이지에 내장된 원본 글꼴 버퍼 (없거나 추출 불가면 None)"""
    want = _norm(font_name)
    for f in page.get_fonts(full=True):
        xref, ext, _typ, basefont = f[0], f[1], f[2], f[3]
        if ext in ("n/a", "", None):
            continue
        cands = {_norm(basefont)}
        try:
            name, ext2, _t, buf = doc.extract_font(xref)
        except Exception:
            continue
        if not buf:
            continue
        cands.add(_norm(name))
        try:
            cands.add(_norm(fitz.Font(fontbuffer=buf).name))
        except Exception:
            pass
        if any(c and (c == want or c.startswith(want) or want.startswith(c)) for c in cands):
            return buf
    return None


def _covers(font, text):
    return all(font.has_glyph(ord(ch)) for ch in text if not ch.isspace())


def fallback_font_file(bold=False):
    for f in (BOLD_FONT_CANDIDATES if bold else []) + FONT_CANDIDATES:
        if os.path.exists(f):
            return f
    return None


def choose_font(doc, page, unit, new_text, fallback=None):
    """새 글자를 쓸 글꼴 결정 → (insert_text 인자 dict, 설명)
    1) 원본 내장 글꼴에 새 글자가 모두 있으면 재사용  2) 기본14 글꼴(라틴만)  3) 맑은 고딕(굵게면 굵은 글꼴)"""
    buf = _embedded_font(doc, page, unit.font)
    if buf:
        try:
            fnt = fitz.Font(fontbuffer=buf)
            if _covers(fnt, new_text):
                key = re.sub(r"[^A-Za-z0-9]", "", _norm(unit.font))[:24] or "f"
                return dict(fontname=f"orig{key}", fontbuffer=buf), "원본 글꼴"
        except Exception:
            pass
    b14 = BASE14.get(_norm(unit.font))
    if b14 and all(ord(ch) < 256 for ch in new_text):
        return dict(fontname=b14), "원본 글꼴(기본)"
    bold_file = fallback_font_file(True) if unit.bold else None
    if bold_file and not _is_bold_file(bold_file):
        bold_file = None
    ff = bold_file or fallback or fallback_font_file(False)
    if ff:
        kw = dict(fontname="kfontb" if _is_bold_file(ff) else "kfont", fontfile=ff)
        if unit.bold and not _is_bold_file(ff):
            kw["_fake_bold"] = True          # 굵은 글꼴이 없으면 윤곽선 덧그려 굵게
        return kw, "맑은 고딕(대체)"
    return dict(fontname="hebo" if unit.bold else "helv"), "기본 글꼴(대체)"


def _is_bold_file(path):
    return bool(path) and os.path.basename(path).lower() in ("malgunbd.ttf",)


# ── 지우기/쓰기 ──
def erase_text(page, rects):
    """글자만 지움: 배경색·표 선·이미지는 그대로 둔다"""
    for r in rects:
        r = fitz.Rect(r)
        inset = r.height * 0.2
        page.add_redact_annot(fitz.Rect(r.x0 + 0.3, r.y0 + inset, r.x1 - 0.3, r.y1 - inset), fill=False)
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                          text=fitz.PDF_REDACT_TEXT_REMOVE)


def write_lines(page, unit, new_text, font_kw):
    font_kw = dict(font_kw)
    if font_kw.pop("_fake_bold", False):
        font_kw.update(render_mode=2, border_width=max(0.02, unit.size * 0.0035))
    buf = font_kw.pop("fontbuffer", None)
    if buf is not None:     # 원본 내장 글꼴: 페이지에 등록 후 이름으로 사용
        page.insert_font(fontname=font_kw["fontname"], fontbuffer=buf)
    lines = new_text.split("\n")
    pitch = unit.line_pitch
    x0, y0 = unit.origins[0] if unit.origins else (unit.bbox.x0, unit.bbox.y1 - unit.size * 0.2)
    for i, ln in enumerate(lines):
        if not ln:
            continue
        x = unit.origins[i][0] if i < len(unit.origins) else x0
        y = unit.origins[i][1] if i < len(unit.origins) else y0 + pitch * i
        page.insert_text((x, y), ln, fontsize=unit.size, color=unit.color, **font_kw)


def replace_unit(doc, page, unit, new_text, fallback=None):
    """unit 의 글자를 new_text 로 교체. 사용한 글꼴 설명 반환"""
    new_text = new_text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")
    font_kw, desc = choose_font(doc, page, unit, new_text, fallback)
    erase_text(page, unit.line_rects or [unit.bbox])
    if new_text.strip():
        write_lines(page, unit, new_text, font_kw)
    return desc


def replace_in_lines(doc, page, old, new, fallback=None):
    """찾아 바꾸기: old 가 들어있는 줄 전체를 원래 글꼴·크기·색으로 다시 쓴다 (글자 겹침 방지).
    바뀐 건수 반환. 줄을 넘는 검색어 등 줄에서 못 찾은 경우는 0"""
    cnt = 0
    for u in text_units(page, LINE):
        n = u.text.count(old)
        if n:
            replace_unit(doc, page, u, u.text.replace(old, new), fallback)
            cnt += n
    return cnt
