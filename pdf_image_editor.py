# -*- coding: utf-8 -*-
"""
PDF·이미지 통합 편집기 v1.0.0
설치: pip install -r requirements.txt
빌드: build.bat
"""
import os
import sys
import io
import re
import shutil
import subprocess
import tempfile

try:
    import pymupdf as fitz
except ImportError:
    import fitz
from PIL import Image, ImageOps

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIF = True
except Exception:
    HEIF = False

from PySide6.QtCore import Qt, QSize, QRect, QPoint, Signal
from PySide6.QtGui import QPixmap, QImage, QIcon, QPainter, QPen, QColor, QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QFormLayout, QListWidget, QListWidgetItem, QAbstractItemView, QLabel, QScrollArea,
    QToolBar, QPushButton, QComboBox, QSpinBox, QCheckBox, QLineEdit, QGroupBox, QSlider,
    QFileDialog, QMessageBox, QInputDialog, QColorDialog, QDialog, QDialogButtonBox,
    QRadioButton, QButtonGroup, QProgressDialog, QSplitter, QStatusBar, QListView,
)

APP_NAME = "PDF·이미지 통합 편집기"
VERSION = "1.0.0"

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


# ───────────────────────── 공통 함수 ─────────────────────────
def resource_path(name):
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


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


def pix_to_qimage(pix):
    fmt = QImage.Format_RGBA8888 if pix.alpha else QImage.Format_RGB888
    return QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()


def pil_thumb_pixmap(im, size):
    im = im.copy()
    im.thumbnail((size, size))
    im = im.convert("RGBA")
    data = im.tobytes("raw", "RGBA")
    q = QImage(data, im.width, im.height, im.width * 4, QImage.Format_RGBA8888).copy()
    return QPixmap.fromImage(q)


def open_image(path):
    im = Image.open(path)
    try:
        im = ImageOps.exif_transpose(im)
    except Exception:
        pass
    return im


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


def progress(parent, title, n):
    dlg = QProgressDialog(title, "취소", 0, n, parent)
    dlg.setWindowTitle(APP_NAME)
    dlg.setWindowModality(Qt.WindowModal)
    dlg.setMinimumDuration(300)
    dlg.setValue(0)
    return dlg


# ───────────────────────── 공용 위젯 ─────────────────────────
class FileList(QListWidget):
    filesDropped = Signal(list)

    def __init__(self, exts, icon=64, parent=None, thumbs=True):
        super().__init__(parent)
        self.exts = exts
        self.thumbs = thumbs
        self.setAcceptDrops(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setIconSize(QSize(icon, icon))
        self.icon = icon

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e):
        if e.mimeData().hasUrls():
            files = collect_files([u.toLocalFile() for u in e.mimeData().urls()], self.exts)
            if files:
                self.filesDropped.emit(files)
            e.acceptProposedAction()
        else:
            super().dropEvent(e)

    def add_files(self, files):
        exist = set(self.paths())
        for p in files:
            if p in exist:
                continue
            it = QListWidgetItem(os.path.basename(p))
            it.setData(Qt.UserRole, p)
            it.setToolTip(p)
            if not self.thumbs:
                try:
                    it.setText(f"{os.path.basename(p)}   ({human(os.path.getsize(p))})")
                except OSError:
                    pass
                self.addItem(it)
                continue
            try:
                im = open_image(p)
                if hasattr(im, 'draft'):
                    try:
                        im.draft('RGB', (self.icon * 2, self.icon * 2))
                    except Exception:
                        pass
                w, h = im.size
                it.setIcon(QIcon(pil_thumb_pixmap(im, self.icon)))
                it.setText(f"{os.path.basename(p)}\n{w}×{h} · {human(os.path.getsize(p))}")
            except Exception:
                it.setText(f"{os.path.basename(p)}\n(미리보기 불가)")
            self.addItem(it)
            QApplication.processEvents()

    def paths(self):
        return [self.item(i).data(Qt.UserRole) for i in range(self.count())]

    def selected_paths(self):
        rows = sorted(self.row(i) for i in self.selectedItems())
        return [self.item(r).data(Qt.UserRole) for r in rows]

    def remove_selected(self):
        for it in self.selectedItems():
            self.takeItem(self.row(it))

    def move_selected(self, d):
        rows = sorted(self.row(i) for i in self.selectedItems())
        if not rows:
            return
        if d < 0 and rows[0] == 0:
            return
        if d > 0 and rows[-1] == self.count() - 1:
            return
        for r in (rows if d < 0 else reversed(rows)):
            it = self.takeItem(r)
            self.insertItem(r + d, it)
        self.clearSelection()
        for r in rows:
            self.item(r + d).setSelected(True)

    def sort_by_name(self):
        ps = sorted(self.paths(), key=lambda p: os.path.basename(p).lower())
        items = {self.item(i).data(Qt.UserRole): self.takeItem(0) for i in range(self.count())}
        for p in ps:
            self.addItem(items[p])


class PageList(QListWidget):
    reordered = Signal()

    def __init__(self):
        super().__init__()
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setIconSize(QSize(110, 150))
        self.setSpacing(3)
        self.setViewMode(QListView.ListMode)

    def dropEvent(self, e):
        super().dropEvent(e)
        self.reordered.emit()


class PageView(QLabel):
    clicked = Signal(QPoint)
    dragged = Signal(QRect)

    def __init__(self):
        super().__init__()
        self.mode = None
        self._start = None
        self._cur = None

    def set_mode(self, m):
        self.mode = m
        self.setCursor(Qt.CrossCursor if m else Qt.ArrowCursor)

    def mousePressEvent(self, e):
        if self.mode and e.button() == Qt.LeftButton:
            self._start = self._cur = e.position().toPoint()
            self.update()

    def mouseMoveEvent(self, e):
        if self._start is not None:
            self._cur = e.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, e):
        if self._start is None:
            return
        s, c = self._start, e.position().toPoint()
        self._start = self._cur = None
        self.update()
        if self.mode == 'text':
            self.clicked.emit(s)
        elif self.mode == 'white':
            r = QRect(s, c).normalized()
            if r.width() > 3 and r.height() > 3:
                self.dragged.emit(r)

    def paintEvent(self, e):
        super().paintEvent(e)
        if self.mode == 'white' and self._start is not None:
            p = QPainter(self)
            p.setPen(QPen(QColor(220, 0, 0), 1, Qt.DashLine))
            p.setBrush(QColor(255, 255, 255, 160))
            p.drawRect(QRect(self._start, self._cur).normalized())
            p.end()


# ───────────────────────── 대화상자 ─────────────────────────
class SplitDialog(QDialog):
    def __init__(self, n, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PDF 분할")
        self.n = n
        f = QFormLayout(self)
        self.r_each = QRadioButton("페이지마다 1개 파일")
        self.r_every = QRadioButton("N페이지씩")
        self.r_range = QRadioButton("범위 지정")
        self.r_each.setChecked(True)
        g = QButtonGroup(self)
        for r in (self.r_each, self.r_every, self.r_range):
            g.addButton(r)
        self.sp_n = QSpinBox()
        self.sp_n.setRange(1, max(1, n))
        self.sp_n.setValue(2)
        self.ed_range = QLineEdit()
        self.ed_range.setPlaceholderText("예: 1-3, 4-6, 7-")
        f.addRow(QLabel(f"전체 {n}페이지"))
        f.addRow(self.r_each)
        h1 = QHBoxLayout(); h1.addWidget(self.r_every); h1.addWidget(self.sp_n); h1.addStretch()
        f.addRow(h1)
        h2 = QHBoxLayout(); h2.addWidget(self.r_range); h2.addWidget(self.ed_range)
        f.addRow(h2)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def groups(self):
        if self.r_each.isChecked():
            return [[i] for i in range(self.n)]
        if self.r_every.isChecked():
            k = self.sp_n.value()
            return [list(range(i, min(i + k, self.n))) for i in range(0, self.n, k)]
        return parse_ranges(self.ed_range.text(), self.n)


class ReplaceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("텍스트 찾아 바꾸기")
        f = QFormLayout(self)
        self.ed_old = QLineEdit()
        self.ed_new = QLineEdit()
        self.cb_all = QCheckBox("전체 페이지")
        self.cb_all.setChecked(True)
        f.addRow("찾을 내용", self.ed_old)
        f.addRow("바꿀 내용", self.ed_new)
        f.addRow(self.cb_all)
        f.addRow(QLabel("※ 원본 글꼴과 다르게 표시될 수 있음 (스캔본 불가)"))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)


# ───────────────────────── PDF 편집 탭 ─────────────────────────
class PdfTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.doc = None
        self.path = None
        self.modified = False
        self.undo_stack = []
        self.zoom = 1.0
        self.color = (0, 0, 0)
        self.font = korean_font()
        self._build()
        self._update_state()

    # UI
    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(4, 4, 4, 4)
        tb = QToolBar()
        tb.setToolButtonStyle(Qt.ToolButtonTextOnly)
        v.addWidget(tb)

        def act(text, slot, sc=None, checkable=False):
            a = QAction(text, self)
            a.setCheckable(checkable)
            if sc:
                a.setShortcut(QKeySequence(sc))
            a.triggered.connect(slot)
            tb.addAction(a)
            return a

        act("열기", self.open_pdf, "Ctrl+O")
        act("PDF/이미지 추가(병합)", self.merge_files)
        self.a_save = act("저장", self.save, "Ctrl+S")
        self.a_saveas = act("다른 이름 저장", self.save_as, "Ctrl+Shift+S")
        tb.addSeparator()
        self.a_undo = act("실행취소", self.undo, "Ctrl+Z")
        tb.addSeparator()
        self.a_rl = act("⟲ 좌회전", lambda: self.rotate(-90), "Ctrl+L")
        self.a_rr = act("⟳ 우회전", lambda: self.rotate(90), "Ctrl+R")
        self.a_del = act("페이지 삭제", self.delete_pages, "Delete")
        self.a_blank = act("빈 페이지", self.insert_blank)
        self.a_up = act("▲ 위로", lambda: self.move(-1))
        self.a_dn = act("▼ 아래로", lambda: self.move(1))
        tb.addSeparator()
        self.a_ext = act("선택 페이지 추출", self.extract)
        self.a_split = act("분할", self.split)
        tb.addSeparator()
        self.a_text = act("텍스트 추가", lambda c: self.set_mode('text' if c else None), checkable=True)
        self.a_white = act("영역 지우기", lambda c: self.set_mode('white' if c else None), checkable=True)
        self.a_repl = act("찾아 바꾸기", self.replace_text, "Ctrl+H")
        tb.addSeparator()
        tb.addWidget(QLabel(" 글자 "))
        self.sp_font = QSpinBox()
        self.sp_font.setRange(4, 200)
        self.sp_font.setValue(12)
        tb.addWidget(self.sp_font)
        self.btn_color = QPushButton("■")
        self.btn_color.setFixedWidth(30)
        self.btn_color.setStyleSheet("color:#000;font-size:16px;")
        self.btn_color.clicked.connect(self.pick_color)
        tb.addWidget(self.btn_color)
        tb.addWidget(QLabel(" 배율 "))
        self.cb_zoom = QComboBox()
        self.cb_zoom.addItems(["폭 맞춤", "50%", "75%", "100%", "125%", "150%", "200%"])
        self.cb_zoom.setCurrentText("폭 맞춤")
        self.cb_zoom.currentTextChanged.connect(lambda _: self.render_preview())
        tb.addWidget(self.cb_zoom)

        sp = QSplitter()
        self.pages = PageList()
        self.pages.setMinimumWidth(190)
        self.pages.currentRowChanged.connect(lambda _: self.render_preview())
        self.pages.reordered.connect(self.on_reordered)
        sp.addWidget(self.pages)

        self.scroll = QScrollArea()
        self.scroll.setAlignment(Qt.AlignCenter)
        self.scroll.setStyleSheet("QScrollArea{background:#6b6b6b;}")
        self.view = PageView()
        self.view.clicked.connect(self.on_text_click)
        self.view.dragged.connect(self.on_white_drag)
        self.scroll.setWidget(self.view)
        self.scroll.setWidgetResizable(False)
        sp.addWidget(self.scroll)
        sp.setStretchFactor(1, 1)
        sp.setSizes([210, 900])
        v.addWidget(sp)

        self.lbl_drop = QLabel("PDF 파일을 열거나 여기로 끌어다 놓으세요")
        self.lbl_drop.setAlignment(Qt.AlignCenter)
        self.setAcceptDrops(True)
        self.edit_actions = [self.a_save, self.a_saveas, self.a_rl, self.a_rr, self.a_del, self.a_blank,
                             self.a_up, self.a_dn, self.a_ext, self.a_split, self.a_text, self.a_white,
                             self.a_repl]

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        files = collect_files([u.toLocalFile() for u in e.mimeData().urls()], PDF_EXT | IMG_EXT)
        if not files:
            return
        if self.doc is None and os.path.splitext(files[0])[1].lower() == '.pdf':
            self.load(files[0])
            files = files[1:]
        if files:
            self.merge_files(files)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.cb_zoom.currentText() == "폭 맞춤":
            self.render_preview()

    # 상태
    def _update_state(self):
        has = self.doc is not None
        for a in self.edit_actions:
            a.setEnabled(has)
        self.a_undo.setEnabled(bool(self.undo_stack))
        name = os.path.basename(self.path) if self.path else ("새 문서" if has else "")
        info = f"{name}{' *' if self.modified else ''}"
        if has:
            info += f"  |  {self.doc.page_count}페이지"
        self.win.set_status(info)

    def snapshot(self):
        self.undo_stack.append(self.doc.tobytes())
        if len(self.undo_stack) > 15:
            self.undo_stack.pop(0)
        self.modified = True

    def undo(self):
        if not self.undo_stack:
            return
        cur = self.pages.currentRow()
        self.doc = fitz.open(stream=self.undo_stack.pop(), filetype="pdf")
        self.refresh([min(max(cur, 0), self.doc.page_count - 1)])

    def sel_rows(self):
        rows = sorted({self.pages.row(i) for i in self.pages.selectedItems()})
        if not rows and self.pages.currentRow() >= 0:
            rows = [self.pages.currentRow()]
        return rows

    def confirm_discard(self):
        if self.doc is None or not self.modified:
            return True
        r = QMessageBox.question(self, APP_NAME, "변경 내용을 저장할까요?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Save:
            return self.save()
        return r == QMessageBox.Discard

    # 파일
    def open_pdf(self):
        if not self.confirm_discard():
            return
        p, _ = QFileDialog.getOpenFileName(self, "PDF 열기", "", PDF_FILTER)
        if p:
            self.load(p)

    def open_doc(self, path):
        with open(path, 'rb') as f:
            data = f.read()
        doc = fitz.open(stream=data, filetype="pdf")
        if doc.needs_pass:
            pw, ok = QInputDialog.getText(self, "암호", f"{os.path.basename(path)} 암호:", QLineEdit.Password)
            if not ok or not doc.authenticate(pw):
                raise ValueError("암호가 올바르지 않습니다.")
        return doc

    def load(self, path):
        try:
            self.doc = self.open_doc(path)
        except Exception as ex:
            QMessageBox.warning(self, APP_NAME, f"열기 실패\n{ex}")
            return
        self.path = path
        self.modified = False
        self.undo_stack.clear()
        self.refresh([0])

    def merge_files(self, files=None):
        if not files:
            files, _ = QFileDialog.getOpenFileNames(self, "추가할 파일", "",
                                                    f"PDF/이미지 (*.pdf {' '.join('*' + e for e in IMG_EXT)})")
        if not files:
            return
        if self.doc is None:
            self.doc = fitz.open()
            self.path = None
        else:
            self.snapshot()
        start = self.doc.page_count
        for p in files:
            try:
                if os.path.splitext(p)[1].lower() == '.pdf':
                    self.doc.insert_pdf(self.open_doc(p))
                else:
                    images_to_pdf_pages(self.doc, [p], "이미지 원본 크기", 0, 90)
            except Exception as ex:
                QMessageBox.warning(self, APP_NAME, f"{os.path.basename(p)} 추가 실패\n{ex}")
        self.modified = True
        self.refresh([min(start, self.doc.page_count - 1)])

    def save(self):
        if self.doc is None:
            return False
        if not self.path:
            return self.save_as()
        return self._write(self.path)

    def save_as(self):
        if self.doc is None:
            return False
        p, _ = QFileDialog.getSaveFileName(self, "다른 이름 저장", self.path or "편집본.pdf", PDF_FILTER)
        if not p:
            return False
        if not p.lower().endswith('.pdf'):
            p += '.pdf'
        if self._write(p):
            self.path = p
            self._update_state()
            return True
        return False

    def _write(self, path):
        try:
            data = self.doc.tobytes(garbage=3, deflate=True, deflate_images=True, deflate_fonts=True)
            with open(path, 'wb') as f:
                f.write(data)
        except Exception as ex:
            QMessageBox.warning(self, APP_NAME, f"저장 실패\n{ex}")
            return False
        self.modified = False
        self._update_state()
        self.win.statusBar().showMessage(f"저장 완료: {path} ({human(len(data))})", 5000)
        return True

    # 화면
    def refresh(self, select=None):
        self.pages.blockSignals(True)
        self.pages.clear()
        if self.doc is not None:
            for i, page in enumerate(self.doc):
                pix = page.get_pixmap(matrix=fitz.Matrix(0.2, 0.2), alpha=False)
                it = QListWidgetItem(QIcon(QPixmap.fromImage(pix_to_qimage(pix))), f"{i + 1}")
                it.setData(Qt.UserRole, i)
                self.pages.addItem(it)
                if i % 20 == 0:
                    QApplication.processEvents()
        self.pages.blockSignals(False)
        if self.doc is not None and self.doc.page_count:
            sel = [r for r in (select or [0]) if 0 <= r < self.doc.page_count] or [0]
            self.pages.setCurrentRow(sel[0])
            for r in sel:
                self.pages.item(r).setSelected(True)
        self.render_preview()
        self._update_state()

    def current_page(self):
        r = self.pages.currentRow()
        if self.doc is None or r < 0 or r >= self.doc.page_count:
            return None
        return self.doc[r]

    def render_preview(self):
        page = self.current_page()
        if page is None:
            self.view.clear()
            self.view.setText("PDF 파일을 열거나 여기로 끌어다 놓으세요")
            self.view.setStyleSheet("color:#eee;font-size:14px;")
            self.view.resize(500, 200)
            return
        self.view.setStyleSheet("")
        z = self.cb_zoom.currentText()
        if z == "폭 맞춤":
            w = max(200, self.scroll.viewport().width() - 30)
            self.zoom = w / page.rect.width
        else:
            self.zoom = int(z.rstrip('%')) / 100
        pix = page.get_pixmap(matrix=fitz.Matrix(self.zoom, self.zoom), alpha=False)
        pm = QPixmap.fromImage(pix_to_qimage(pix))
        self.view.setPixmap(pm)
        self.view.resize(pm.size())

    def to_pdf_point(self, page, qp, dy=0.0):
        p = fitz.Point(qp.x() / self.zoom, qp.y() / self.zoom + dy)
        return p * page.derotation_matrix

    # 페이지 조작
    def rotate(self, ang):
        rows = self.sel_rows()
        if not rows:
            return
        self.snapshot()
        for r in rows:
            pg = self.doc[r]
            pg.set_rotation((pg.rotation + ang) % 360)
        self.refresh(rows)

    def delete_pages(self):
        rows = self.sel_rows()
        if not rows:
            return
        if len(rows) >= self.doc.page_count:
            QMessageBox.information(self, APP_NAME, "모든 페이지는 삭제할 수 없습니다.")
            return
        if QMessageBox.question(self, APP_NAME, f"{len(rows)}개 페이지를 삭제할까요?") != QMessageBox.Yes:
            return
        self.snapshot()
        self.doc.delete_pages(rows)
        self.refresh([min(rows[0], self.doc.page_count - 1)])

    def insert_blank(self):
        r = max(self.pages.currentRow(), 0)
        ref = self.doc[r].rect if self.doc.page_count else fitz.Rect(0, 0, *A4)
        self.snapshot()
        self.doc.new_page(pno=r + 1, width=ref.width, height=ref.height)
        self.refresh([r + 1])

    def move(self, d):
        rows = self.sel_rows()
        n = self.doc.page_count
        if not rows or (d < 0 and rows[0] == 0) or (d > 0 and rows[-1] == n - 1):
            return
        order = list(range(n))
        for r in (rows if d < 0 else reversed(rows)):
            order[r + d], order[r] = order[r], order[r + d]
        self.snapshot()
        self.doc.select(order)
        self.refresh([r + d for r in rows])

    def on_reordered(self):
        order = [self.pages.item(i).data(Qt.UserRole) for i in range(self.pages.count())]
        if order == list(range(len(order))):
            return
        sel = self.sel_rows()
        self.snapshot()
        self.doc.select(order)
        self.refresh(sel)

    def extract(self):
        rows = self.sel_rows()
        if not rows:
            return
        base = os.path.splitext(os.path.basename(self.path or "문서.pdf"))[0]
        p, _ = QFileDialog.getSaveFileName(self, "추출 파일 저장", f"{base}_추출.pdf", PDF_FILTER)
        if not p:
            return
        new = fitz.open()
        for r in rows:
            new.insert_pdf(self.doc, from_page=r, to_page=r)
        new.save(p, garbage=3, deflate=True)
        self.win.statusBar().showMessage(f"{len(rows)}페이지 추출 완료: {p}", 5000)

    def split(self):
        dlg = SplitDialog(self.doc.page_count, self)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            groups = dlg.groups()
        except ValueError as ex:
            QMessageBox.warning(self, APP_NAME, str(ex))
            return
        if not groups:
            return
        out = QFileDialog.getExistingDirectory(self, "저장 폴더",
                                               os.path.dirname(self.path) if self.path else "")
        if not out:
            return
        base = os.path.splitext(os.path.basename(self.path or "문서.pdf"))[0]
        pd = progress(self, "분할 중...", len(groups))
        for k, g in enumerate(groups):
            if pd.wasCanceled():
                break
            new = fitz.open()
            new.insert_pdf(self.doc, from_page=g[0], to_page=g[-1])
            tag = f"p{g[0] + 1}" if len(g) == 1 else f"p{g[0] + 1}-{g[-1] + 1}"
            new.save(unique_path(os.path.join(out, f"{base}_{tag}.pdf")), garbage=3, deflate=True)
            pd.setValue(k + 1)
        pd.close()
        QMessageBox.information(self, APP_NAME, f"{len(groups)}개 파일로 분할 완료\n{out}")

    # 내용 편집
    def set_mode(self, m):
        self.a_text.setChecked(m == 'text')
        self.a_white.setChecked(m == 'white')
        self.view.set_mode(m)

    def pick_color(self):
        c = QColorDialog.getColor(QColor(*[int(x * 255) for x in self.color]), self, "글자 색")
        if c.isValid():
            self.color = (c.redF(), c.greenF(), c.blueF())
            self.btn_color.setStyleSheet(f"color:{c.name()};font-size:16px;")

    def _insert_text(self, page, point, text, size, color):
        kw = dict(fontsize=size, color=color, rotate=page.rotation)
        if self.font:
            kw.update(fontname="kfont", fontfile=self.font)
        else:
            kw.update(fontname="helv")
        page.insert_text(point, text, **kw)

    def on_text_click(self, qp):
        page = self.current_page()
        if page is None:
            return
        text, ok = QInputDialog.getMultiLineText(self, "텍스트 추가", "입력할 내용:")
        if not ok or not text.strip():
            return
        size = self.sp_font.value()
        self.snapshot()
        try:
            self._insert_text(page, self.to_pdf_point(page, qp, size), text, size, self.color)
        except Exception as ex:
            QMessageBox.warning(self, APP_NAME, f"텍스트 추가 실패\n{ex}")
        self.refresh([self.pages.currentRow()])

    def on_white_drag(self, qr):
        page = self.current_page()
        if page is None:
            return
        p1 = self.to_pdf_point(page, qr.topLeft())
        p2 = self.to_pdf_point(page, qr.bottomRight())
        rect = fitz.Rect(p1, p2).normalize()
        self.snapshot()
        page.add_redact_annot(rect, fill=(1, 1, 1))
        page.apply_redactions(images=getattr(fitz, 'PDF_REDACT_IMAGE_NONE', 0))
        self.refresh([self.pages.currentRow()])

    def replace_text(self):
        dlg = ReplaceDialog(self)
        if dlg.exec() != QDialog.Accepted or not dlg.ed_old.text():
            return
        old, new = dlg.ed_old.text(), dlg.ed_new.text()
        rows = range(self.doc.page_count) if dlg.cb_all.isChecked() else [self.pages.currentRow()]
        self.snapshot()
        cnt = 0
        for r in rows:
            page = self.doc[r]
            hits = page.search_for(old)
            if not hits:
                continue
            for h in hits:
                page.add_redact_annot(h, fill=(1, 1, 1))
            page.apply_redactions(images=getattr(fitz, 'PDF_REDACT_IMAGE_NONE', 0))
            if new:
                for h in hits:
                    fs = max(4, h.height * 0.78)
                    pt = fitz.Point(h.x0, h.y1 - h.height * 0.22)
                    try:
                        kw = dict(fontsize=fs, color=(0, 0, 0))
                        if self.font:
                            kw.update(fontname="kfont", fontfile=self.font)
                        page.insert_text(pt, new, **kw)
                    except Exception:
                        pass
            cnt += len(hits)
        if cnt == 0:
            self.undo_stack.pop()
            QMessageBox.information(self, APP_NAME, "찾는 내용이 없습니다.")
            return
        self.refresh([max(self.pages.currentRow(), 0)])
        QMessageBox.information(self, APP_NAME, f"{cnt}건 변경 완료")


# ───────────────────────── 사진 편집 탭 ─────────────────────────
class ImageTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self._build()

    def _build(self):
        h = QHBoxLayout(self)
        h.setContentsMargins(4, 4, 4, 4)

        left = QVBoxLayout()
        bar = QHBoxLayout()
        for t, s in [("파일 추가", self.add), ("폴더 추가", self.add_folder),
                     ("선택 삭제", lambda: self.lst.remove_selected()), ("전체 비우기", lambda: self.lst.clear())]:
            b = QPushButton(t)
            b.clicked.connect(s)
            bar.addWidget(b)
        left.addLayout(bar)
        self.lst = FileList(IMG_EXT, 56)
        self.lst.filesDropped.connect(self.lst.add_files)
        self.lst.currentItemChanged.connect(self.show_preview)
        left.addWidget(self.lst)
        hint = QLabel("파일·폴더를 끌어다 놓아도 됩니다" + ("" if HEIF else "  (HEIC: pip install pillow-heif)"))
        hint.setStyleSheet("color:#777;")
        left.addWidget(hint)
        h.addLayout(left, 3)

        right = QVBoxLayout()
        self.preview = QLabel("미리보기")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(320, 240)
        self.preview.setStyleSheet("background:#f0f0f0;border:1px solid #ccc;")
        right.addWidget(self.preview)
        self.info = QLabel("")
        right.addWidget(self.info)

        g1 = QGroupBox("형식 / 용량")
        f1 = QFormLayout(g1)
        self.cb_fmt = QComboBox()
        self.cb_fmt.addItems(["원본 유지"] + list(SAVE_FORMATS.keys()))
        self.cb_fmt.setCurrentText("JPG")
        f1.addRow("저장 형식", self.cb_fmt)
        qh = QHBoxLayout()
        self.sl_q = QSlider(Qt.Horizontal)
        self.sl_q.setRange(10, 100)
        self.sl_q.setValue(85)
        self.lb_q = QLabel("85")
        self.sl_q.valueChanged.connect(lambda v: self.lb_q.setText(str(v)))
        qh.addWidget(self.sl_q)
        qh.addWidget(self.lb_q)
        f1.addRow("품질(JPG/WEBP)", qh)
        th = QHBoxLayout()
        self.cb_target = QCheckBox("목표 용량 이하")
        self.sp_target = QSpinBox()
        self.sp_target.setRange(10, 100000)
        self.sp_target.setValue(500)
        self.sp_target.setSuffix(" KB")
        th.addWidget(self.cb_target)
        th.addWidget(self.sp_target)
        f1.addRow(th)
        right.addWidget(g1)

        g2 = QGroupBox("크기")
        f2 = QFormLayout(g2)
        self.cb_resize = QComboBox()
        self.cb_resize.addItems(["변경 안 함", "비율(%)", "가로 기준(px)", "세로 기준(px)", "가로×세로 지정(px)"])
        self.cb_resize.currentIndexChanged.connect(self._resize_ui)
        f2.addRow("방식", self.cb_resize)
        self.sp_pct = QSpinBox(); self.sp_pct.setRange(1, 1000); self.sp_pct.setValue(50); self.sp_pct.setSuffix(" %")
        self.sp_w = QSpinBox(); self.sp_w.setRange(1, 20000); self.sp_w.setValue(1920)
        self.sp_h = QSpinBox(); self.sp_h.setRange(1, 20000); self.sp_h.setValue(1080)
        self.cb_keep = QCheckBox("비율 유지(범위 안에 맞춤)"); self.cb_keep.setChecked(True)
        self.cb_noup = QCheckBox("원본보다 크게 확대 안 함"); self.cb_noup.setChecked(True)
        f2.addRow("비율", self.sp_pct)
        f2.addRow("가로", self.sp_w)
        f2.addRow("세로", self.sp_h)
        f2.addRow(self.cb_keep)
        f2.addRow(self.cb_noup)
        right.addWidget(g2)

        g3 = QGroupBox("회전 / 반전")
        h3 = QHBoxLayout(g3)
        self.cb_rot = QComboBox()
        self.cb_rot.addItems(["회전 없음", "90° 우", "90° 좌", "180°"])
        self.cb_fx = QCheckBox("좌우반전")
        self.cb_fy = QCheckBox("상하반전")
        h3.addWidget(self.cb_rot)
        h3.addWidget(self.cb_fx)
        h3.addWidget(self.cb_fy)
        right.addWidget(g3)

        g4 = QGroupBox("저장")
        f4 = QFormLayout(g4)
        oh = QHBoxLayout()
        self.ed_out = QLineEdit()
        self.ed_out.setPlaceholderText("비우면 원본 폴더\\변환 폴더에 저장")
        b = QPushButton("...")
        b.setFixedWidth(30)
        b.clicked.connect(lambda: self._pick_dir(self.ed_out))
        oh.addWidget(self.ed_out)
        oh.addWidget(b)
        f4.addRow("출력 폴더", oh)
        self.ed_suffix = QLineEdit("")
        self.ed_suffix.setPlaceholderText("예: _변환")
        f4.addRow("파일명 뒤에", self.ed_suffix)
        self.cb_only_sel = QCheckBox("선택한 파일만")
        f4.addRow(self.cb_only_sel)
        right.addWidget(g4)

        run = QPushButton("실행")
        run.setMinimumHeight(38)
        run.setStyleSheet("font-weight:bold;font-size:14px;")
        run.clicked.connect(self.run)
        right.addWidget(run)
        right.addStretch()
        rw = QWidget()
        rw.setLayout(right)
        rw.setMaximumWidth(430)
        h.addWidget(rw, 2)
        self._resize_ui()

    def _resize_ui(self):
        i = self.cb_resize.currentIndex()
        self.sp_pct.setEnabled(i == 1)
        self.sp_w.setEnabled(i in (2, 4))
        self.sp_h.setEnabled(i in (3, 4))
        self.cb_keep.setEnabled(i == 4)
        self.cb_noup.setEnabled(i in (2, 3, 4))

    def _pick_dir(self, ed):
        d = QFileDialog.getExistingDirectory(self, "폴더 선택", ed.text())
        if d:
            ed.setText(d)

    def add(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "이미지 추가", "", IMG_FILTER)
        if fs:
            self.lst.add_files(fs)

    def add_folder(self):
        d = QFileDialog.getExistingDirectory(self, "폴더 추가")
        if d:
            self.lst.add_files(collect_files([d], IMG_EXT))

    def show_preview(self, cur, _prev=None):
        if cur is None:
            self.preview.setText("미리보기")
            self.info.setText("")
            return
        p = cur.data(Qt.UserRole)
        try:
            im = open_image(p)
            w, h = im.size
            fmt = im.format or os.path.splitext(p)[1][1:].upper()
            self.preview.setPixmap(pil_thumb_pixmap(im, 400))
            self.info.setText(f"{os.path.basename(p)}\n{w}×{h}px · {human(os.path.getsize(p))} · {fmt} · {im.mode}")
        except Exception as ex:
            self.preview.setText(f"열 수 없음\n{ex}")

    def transform(self, im):
        r = self.cb_rot.currentIndex()
        if r == 1:
            im = im.transpose(Image.ROTATE_270)
        elif r == 2:
            im = im.transpose(Image.ROTATE_90)
        elif r == 3:
            im = im.transpose(Image.ROTATE_180)
        if self.cb_fx.isChecked():
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        if self.cb_fy.isChecked():
            im = im.transpose(Image.FLIP_TOP_BOTTOM)

        mode = self.cb_resize.currentIndex()
        w, h = im.size
        nw, nh = w, h
        if mode == 1:
            k = self.sp_pct.value() / 100
            nw, nh = round(w * k), round(h * k)
        elif mode == 2:
            nw = self.sp_w.value(); nh = round(h * nw / w)
        elif mode == 3:
            nh = self.sp_h.value(); nw = round(w * nh / h)
        elif mode == 4:
            tw, th = self.sp_w.value(), self.sp_h.value()
            if self.cb_keep.isChecked():
                k = min(tw / w, th / h)
                nw, nh = round(w * k), round(h * k)
            else:
                nw, nh = tw, th
        if mode in (2, 3, 4) and self.cb_noup.isChecked() and (nw > w or nh > h):
            nw, nh = w, h
        nw, nh = max(1, nw), max(1, nh)
        if (nw, nh) != (w, h):
            if im.mode == 'P':
                im = im.convert('RGBA')
            im = im.resize((nw, nh), Image.LANCZOS)
        return im

    def run(self):
        paths = self.lst.selected_paths() if self.cb_only_sel.isChecked() else self.lst.paths()
        if not paths:
            QMessageBox.information(self, APP_NAME, "처리할 이미지가 없습니다.")
            return
        fsel = self.cb_fmt.currentText()
        q = self.sl_q.value()
        tkb = self.sp_target.value() if self.cb_target.isChecked() else 0
        suffix = self.ed_suffix.text()
        out_dir = self.ed_out.text().strip()
        pd = progress(self, "이미지 처리 중...", len(paths))
        before = after = ok = 0
        errs = []
        last_dir = ""
        for i, p in enumerate(paths):
            if pd.wasCanceled():
                break
            pd.setLabelText(os.path.basename(p))
            try:
                fmt = FMT_FROM_EXT.get(os.path.splitext(p)[1].lower(), 'JPG') if fsel == "원본 유지" else fsel
                im = self.transform(open_image(p))
                d = out_dir or os.path.join(os.path.dirname(p), "변환")
                os.makedirs(d, exist_ok=True)
                last_dir = d
                name = os.path.splitext(os.path.basename(p))[0] + suffix + EXT_OF[fmt]
                dst = unique_path(os.path.join(d, name))
                size = save_image(im, dst, fmt, q, tkb)
                before += os.path.getsize(p)
                after += size
                ok += 1
            except Exception as ex:
                errs.append(f"{os.path.basename(p)}: {ex}")
            pd.setValue(i + 1)
            QApplication.processEvents()
        pd.close()
        msg = f"완료 {ok}건 / 실패 {len(errs)}건\n용량: {human(before)} → {human(after)}"
        if before:
            msg += f" ({(1 - after / before) * 100:+.1f}% 감소)".replace("+-", "+").replace("% 감소", "%")
        if last_dir:
            msg += f"\n저장 위치: {last_dir}"
        if errs:
            msg += "\n\n" + "\n".join(errs[:10])
        QMessageBox.information(self, APP_NAME, msg)


# ───────────────────────── 문서 변환 엔진 ─────────────────────────
EXCEL_EXT = {'.xlsx', '.xls', '.xlsm', '.csv', '.ods'}
WORD_EXT = {'.docx', '.doc', '.rtf', '.txt', '.odt'}
PPT_EXT = {'.pptx', '.ppt', '.odp'}
HWP_EXT = {'.hwp', '.hwpx'}
OFFICE_EXT = EXCEL_EXT | WORD_EXT | PPT_EXT | HWP_EXT
OFFICE_FILTER = "문서 (" + " ".join("*" + e for e in sorted(OFFICE_EXT)) + ")"
NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0


def com_available(progid):
    if sys.platform != 'win32':
        return False
    try:
        import winreg
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, progid))
        return True
    except OSError:
        return False


def find_soffice():
    p = shutil.which('soffice')
    if p:
        return p
    for base in (os.environ.get('ProgramFiles', r'C:\Program Files'),
                 os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')):
        c = os.path.join(base, 'LibreOffice', 'program', 'soffice.exe')
        if os.path.exists(c):
            return c
    return None


def detect_engines():
    return {
        'excel': com_available('Excel.Application'),
        'word': com_available('Word.Application'),
        'ppt': com_available('PowerPoint.Application'),
        'hwp': com_available('HWPFrame.HwpObject'),
        'soffice': find_soffice(),
    }


class OfficeConverter:
    """MS Office / 한글 COM 우선, 없으면 LibreOffice 사용"""

    def __init__(self, engines, fit_width=False):
        self.e = engines
        self.fit = fit_width
        self.apps = {}
        if sys.platform == 'win32':
            try:
                import pythoncom
                pythoncom.CoInitialize()
            except Exception:
                pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def _app(self, progid):
        if progid in self.apps:
            return self.apps[progid]
        import win32com.client
        app = win32com.client.DispatchEx(progid)
        if progid == 'Excel.Application':
            app.Visible = False
            app.DisplayAlerts = False
            app.ScreenUpdating = False
        elif progid == 'Word.Application':
            app.Visible = False
            app.DisplayAlerts = 0
        elif progid == 'HWPFrame.HwpObject':
            try:
                app.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
            except Exception:
                pass
            try:
                app.XHwpWindows.Item(0).Visible = False
            except Exception:
                pass
        self.apps[progid] = app
        return app

    def close(self):
        for progid, app in self.apps.items():
            try:
                if progid == 'HWPFrame.HwpObject':
                    app.Clear(1)
                app.Quit()
            except Exception:
                pass
        self.apps.clear()

    def convert(self, src, dst):
        src, dst = os.path.abspath(src), os.path.abspath(dst)
        ext = os.path.splitext(src)[1].lower()
        if ext in HWP_EXT:
            if not self.e['hwp']:
                raise RuntimeError("한글(HWP) 프로그램이 설치된 PC에서만 변환 가능합니다.")
            return self._hwp(src, dst)
        kind = 'excel' if ext in EXCEL_EXT else 'word' if ext in WORD_EXT else 'ppt'
        err = None
        if self.e[kind]:
            try:
                return getattr(self, '_' + kind)(src, dst)
            except Exception as ex:
                err = ex
        if self.e['soffice']:
            return self._soffice(src, dst)
        if err:
            raise err
        raise RuntimeError("MS Office 또는 LibreOffice가 설치되어 있어야 합니다.")

    def _excel(self, src, dst):
        app = self._app('Excel.Application')
        wb = app.Workbooks.Open(src, 0, True)
        try:
            if self.fit:
                for ws in wb.Worksheets:
                    try:
                        ps = ws.PageSetup
                        ps.Zoom = False
                        ps.FitToPagesWide = 1
                        ps.FitToPagesTall = False
                    except Exception:
                        pass
            wb.ExportAsFixedFormat(0, dst)
        finally:
            wb.Close(False)

    def _word(self, src, dst):
        app = self._app('Word.Application')
        doc = app.Documents.Open(src, False, True)
        try:
            doc.ExportAsFixedFormat(dst, 17)
        finally:
            doc.Close(0)

    def _ppt(self, src, dst):
        app = self._app('PowerPoint.Application')
        pres = app.Presentations.Open(src, True, False, False)
        try:
            pres.SaveAs(dst, 32)
        finally:
            pres.Close()

    def _hwp(self, src, dst):
        hwp = self._app('HWPFrame.HwpObject')
        if not hwp.Open(src, "", "forceopen:true"):
            raise RuntimeError("한글 파일을 열 수 없습니다.")
        try:
            hwp.SaveAs(dst, "PDF", "")
        finally:
            hwp.Clear(1)
        if not os.path.exists(dst):
            raise RuntimeError("한글 PDF 저장 실패")

    def _soffice(self, src, dst):
        tmp = tempfile.mkdtemp()
        try:
            subprocess.run([self.e['soffice'], '--headless', '--convert-to', 'pdf', '--outdir', tmp, src],
                           timeout=300, capture_output=True, creationflags=NO_WINDOW)
            out = os.path.join(tmp, os.path.splitext(os.path.basename(src))[0] + '.pdf')
            if not os.path.exists(out):
                raise RuntimeError("LibreOffice 변환 실패")
            shutil.move(out, dst)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


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


def pdf_to_docx(src, dst):
    try:
        from pdf2docx import Converter
    except ImportError:
        raise RuntimeError("pdf2docx 모듈이 없습니다 (pip install pdf2docx)")
    cv = Converter(src)
    try:
        cv.convert(dst)
    finally:
        cv.close()


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


# ───────────────────────── 변환 탭 ─────────────────────────
def dir_row(parent, placeholder):
    h = QHBoxLayout()
    ed = QLineEdit()
    ed.setPlaceholderText(placeholder)
    b = QPushButton("...")
    b.setFixedWidth(30)

    def pick():
        d = QFileDialog.getExistingDirectory(parent, "폴더 선택", ed.text())
        if d:
            ed.setText(d)
    b.clicked.connect(pick)
    h.addWidget(ed)
    h.addWidget(b)
    return h, ed


def list_bar(lst, add_slot, extra=True):
    bar = QHBoxLayout()
    items = [("추가", add_slot), ("삭제", lst.remove_selected)]
    if extra:
        items += [("▲", lambda: lst.move_selected(-1)), ("▼", lambda: lst.move_selected(1)),
                  ("이름순", lst.sort_by_name)]
    items += [("비우기", lst.clear)]
    for t, s in items:
        b = QPushButton(t)
        b.clicked.connect(s)
        bar.addWidget(b)
    return bar


def run_button(text, slot):
    b = QPushButton(text)
    b.setMinimumHeight(38)
    b.setStyleSheet("font-weight:bold;font-size:13px;")
    b.clicked.connect(slot)
    return b


def out_path(src, out_dir, ext, default_sub="변환"):
    d = out_dir or os.path.join(os.path.dirname(src), default_sub)
    os.makedirs(d, exist_ok=True)
    return unique_path(os.path.join(d, os.path.splitext(os.path.basename(src))[0] + ext))


class Pdf2ImgPanel(QWidget):
    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        self.lst = FileList(PDF_EXT, 32, thumbs=False)
        self.lst.filesDropped.connect(self.lst.add_files)
        v.addLayout(list_bar(self.lst, self.add, extra=False))
        v.addWidget(self.lst)
        f = QFormLayout()
        self.ed_pages = QLineEdit()
        self.ed_pages.setPlaceholderText("비우면 전체 (예: 1-3, 5)")
        f.addRow("페이지", self.ed_pages)
        self.sp_dpi = QSpinBox(); self.sp_dpi.setRange(50, 600); self.sp_dpi.setValue(150); self.sp_dpi.setSuffix(" DPI")
        f.addRow("해상도", self.sp_dpi)
        self.cb_fmt = QComboBox(); self.cb_fmt.addItems(["PNG", "JPG", "WEBP"])
        f.addRow("형식", self.cb_fmt)
        self.sp_q = QSpinBox(); self.sp_q.setRange(10, 100); self.sp_q.setValue(90)
        f.addRow("품질(JPG/WEBP)", self.sp_q)
        row, self.ed_out = dir_row(self, "비우면 PDF 폴더\\PDF파일명 폴더")
        f.addRow("출력 폴더", row)
        v.addLayout(f)
        v.addWidget(run_button("PDF → 이미지 변환", self.run))

    def add(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "PDF 선택", "", PDF_FILTER)
        if fs:
            self.lst.add_files(fs)

    def run(self):
        paths = self.lst.paths()
        if not paths:
            QMessageBox.information(self, APP_NAME, "PDF 파일을 추가하세요.")
            return
        fmt, dpi, q = self.cb_fmt.currentText(), self.sp_dpi.value(), self.sp_q.value()
        txt = self.ed_pages.text().strip()
        total, errs, last = 0, [], ""
        for p in paths:
            try:
                with open(p, 'rb') as fh:
                    doc = fitz.open(stream=fh.read(), filetype="pdf")
                if doc.needs_pass:
                    pw, ok = QInputDialog.getText(self, "암호", f"{os.path.basename(p)} 암호:", QLineEdit.Password)
                    if not ok or not doc.authenticate(pw):
                        raise ValueError("암호 오류")
                n = doc.page_count
                pages = [i for g in parse_ranges(txt, n) for i in g] if txt else list(range(n))
                base = os.path.splitext(os.path.basename(p))[0]
                out = self.ed_out.text().strip() or os.path.join(os.path.dirname(p), base)
                os.makedirs(out, exist_ok=True)
                last = out
                digits = max(3, len(str(n)))
                pd = progress(self, f"{os.path.basename(p)} 변환 중...", len(pages))
                for k, i in enumerate(pages):
                    if pd.wasCanceled():
                        break
                    pix = doc[i].get_pixmap(dpi=dpi, alpha=False)
                    im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                    dst = unique_path(os.path.join(out, f"{base}_p{str(i + 1).zfill(digits)}{EXT_OF[fmt]}"))
                    if fmt == "PNG":
                        im.save(dst, "PNG", optimize=True, dpi=(dpi, dpi))
                    elif fmt == "JPG":
                        im.save(dst, "JPEG", quality=q, optimize=True, dpi=(dpi, dpi))
                    else:
                        im.save(dst, "WEBP", quality=q)
                    total += 1
                    pd.setValue(k + 1)
                    QApplication.processEvents()
                pd.close()
            except Exception as ex:
                errs.append(f"{os.path.basename(p)}: {ex}")
        msg = f"이미지 {total}개 저장 완료" + (f"\n{last}" if last else "")
        if errs:
            msg += "\n\n실패:\n" + "\n".join(errs[:10])
        QMessageBox.information(self, APP_NAME, msg)


class Img2PdfPanel(QWidget):
    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        self.lst = FileList(IMG_EXT, 48)
        self.lst.filesDropped.connect(self.lst.add_files)
        v.addLayout(list_bar(self.lst, self.add))
        v.addWidget(self.lst)
        f = QFormLayout()
        self.cb_mode = QComboBox()
        self.cb_mode.addItems(["전체를 PDF 1개로", "이미지마다 PDF 1개"])
        f.addRow("만들기", self.cb_mode)
        self.cb_size = QComboBox()
        self.cb_size.addItems(["A4 (자동 방향)", "A4 세로", "A4 가로", "Letter (자동 방향)", "이미지 원본 크기"])
        f.addRow("페이지 크기", self.cb_size)
        self.sp_margin = QSpinBox(); self.sp_margin.setRange(0, 50); self.sp_margin.setValue(5); self.sp_margin.setSuffix(" mm")
        f.addRow("여백", self.sp_margin)
        self.sp_q = QSpinBox(); self.sp_q.setRange(10, 100); self.sp_q.setValue(85)
        f.addRow("이미지 품질", self.sp_q)
        v.addLayout(f)
        v.addWidget(run_button("이미지 → PDF 만들기", self.run))

    def add(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "이미지 추가", "", IMG_FILTER)
        if fs:
            self.lst.add_files(fs)

    def run(self):
        paths = self.lst.paths()
        if not paths:
            QMessageBox.information(self, APP_NAME, "이미지를 추가하세요.")
            return
        args = (self.cb_size.currentText(), self.sp_margin.value(), self.sp_q.value())
        if self.cb_mode.currentIndex() == 1:
            d = QFileDialog.getExistingDirectory(self, "저장 폴더", os.path.dirname(paths[0]))
            if not d:
                return
            pd = progress(self, "PDF 생성 중...", len(paths))
            ok, errs = 0, []
            for k, p in enumerate(paths):
                if pd.wasCanceled():
                    break
                try:
                    doc = fitz.open()
                    images_to_pdf_pages(doc, [p], *args)
                    doc.save(out_path(p, d, '.pdf'), garbage=3, deflate=True)
                    ok += 1
                except Exception as ex:
                    errs.append(f"{os.path.basename(p)}: {ex}")
                pd.setValue(k + 1)
                QApplication.processEvents()
            pd.close()
            msg = f"PDF {ok}개 생성 완료\n{d}" + ("\n\n실패:\n" + "\n".join(errs[:10]) if errs else "")
            QMessageBox.information(self, APP_NAME, msg)
            return
        first = os.path.splitext(os.path.basename(paths[0]))[0]
        dst, _ = QFileDialog.getSaveFileName(self, "PDF 저장",
                                             os.path.join(os.path.dirname(paths[0]), f"{first}.pdf"), PDF_FILTER)
        if not dst:
            return
        if not dst.lower().endswith('.pdf'):
            dst += '.pdf'
        doc = fitz.open()
        pd = progress(self, "PDF 생성 중...", len(paths))
        errs = []
        for k, p in enumerate(paths):
            if pd.wasCanceled():
                break
            try:
                images_to_pdf_pages(doc, [p], *args)
            except Exception as ex:
                errs.append(f"{os.path.basename(p)}: {ex}")
            pd.setValue(k + 1)
            QApplication.processEvents()
        pd.close()
        if doc.page_count == 0:
            QMessageBox.warning(self, APP_NAME, "생성된 페이지가 없습니다.\n" + "\n".join(errs[:10]))
            return
        doc.save(dst, garbage=3, deflate=True)
        msg = f"{doc.page_count}페이지 PDF 생성 완료 ({human(os.path.getsize(dst))})\n{dst}"
        if errs:
            msg += "\n\n실패:\n" + "\n".join(errs[:10])
        QMessageBox.information(self, APP_NAME, msg)


class Office2PdfPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.engines = None
        v = QVBoxLayout(self)
        self.lb_eng = QLabel("변환 프로그램 확인 중...")
        self.lb_eng.setWordWrap(True)
        self.lb_eng.setStyleSheet("background:#f6f8fb;border:1px solid #d6dde8;padding:6px;")
        v.addWidget(self.lb_eng)
        self.lst = FileList(OFFICE_EXT, 32, thumbs=False)
        self.lst.filesDropped.connect(self.lst.add_files)
        v.addLayout(list_bar(self.lst, self.add))
        v.addWidget(self.lst)
        f = QFormLayout()
        self.cb_fit = QCheckBox("Excel: 시트 가로폭을 1페이지에 맞춤")
        self.cb_fit.setChecked(True)
        f.addRow(self.cb_fit)
        self.cb_merge = QCheckBox("변환 후 PDF 1개로 합치기 (목록 순서)")
        f.addRow(self.cb_merge)
        row, self.ed_out = dir_row(self, "비우면 원본 폴더\\변환 폴더")
        f.addRow("출력 폴더", row)
        v.addLayout(f)
        v.addWidget(run_button("문서 → PDF 변환", self.run))

    def showEvent(self, e):
        super().showEvent(e)
        if self.engines is None:
            self.engines = detect_engines()
            e_ = self.engines
            yn = lambda b: "✔" if b else "✘"
            self.lb_eng.setText(
                f"MS Excel {yn(e_['excel'])}   MS Word {yn(e_['word'])}   MS PowerPoint {yn(e_['ppt'])}   "
                f"한글(HWP) {yn(e_['hwp'])}   LibreOffice {yn(bool(e_['soffice']))}\n"
                "※ PC에 설치된 Office/한글/LibreOffice로 변환합니다. Office가 없으면 무료 LibreOffice 설치 시 사용 가능 (HWP는 한글 필수)")

    def add(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "문서 추가", "", OFFICE_FILTER)
        if fs:
            self.lst.add_files(fs)

    def run(self):
        paths = self.lst.paths()
        if not paths:
            QMessageBox.information(self, APP_NAME, "변환할 문서를 추가하세요.")
            return
        merged_dst = None
        if self.cb_merge.isChecked():
            first = os.path.splitext(os.path.basename(paths[0]))[0]
            merged_dst, _ = QFileDialog.getSaveFileName(self, "합친 PDF 저장",
                                                        os.path.join(os.path.dirname(paths[0]), f"{first}_합본.pdf"),
                                                        PDF_FILTER)
            if not merged_dst:
                return
            if not merged_dst.lower().endswith('.pdf'):
                merged_dst += '.pdf'
        tmpdir = tempfile.mkdtemp() if merged_dst else None
        outs, errs = [], []
        pd = progress(self, "문서 변환 중...", len(paths))
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            with OfficeConverter(self.engines or detect_engines(), self.cb_fit.isChecked()) as cv:
                for k, p in enumerate(paths):
                    if pd.wasCanceled():
                        break
                    pd.setLabelText(os.path.basename(p))
                    QApplication.processEvents()
                    try:
                        dst = (os.path.join(tmpdir, f"{k:04d}.pdf") if tmpdir
                               else out_path(p, self.ed_out.text().strip(), '.pdf'))
                        cv.convert(p, dst)
                        outs.append(dst)
                    except Exception as ex:
                        errs.append(f"{os.path.basename(p)}: {ex}")
                    pd.setValue(k + 1)
            if merged_dst and outs:
                doc = fitz.open()
                for o in outs:
                    doc.insert_pdf(fitz.open(o))
                doc.save(merged_dst, garbage=3, deflate=True)
        finally:
            QApplication.restoreOverrideCursor()
            pd.close()
            if tmpdir:
                shutil.rmtree(tmpdir, ignore_errors=True)
        if merged_dst and outs:
            msg = f"{len(outs)}개 문서 → PDF 1개 합치기 완료\n{merged_dst}"
        else:
            msg = f"PDF {len(outs)}개 변환 완료" + (f"\n{os.path.dirname(outs[-1])}" if outs else "")
        if errs:
            msg += "\n\n실패:\n" + "\n".join(errs[:10])
        QMessageBox.information(self, APP_NAME, msg)


class Pdf2DocPanel(QWidget):
    TARGETS = [("Word (.docx)", '.docx', pdf_to_docx),
               ("Excel (.xlsx) - 표 추출", '.xlsx', pdf_to_xlsx),
               ("텍스트 (.txt)", '.txt', pdf_to_txt)]

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        self.lst = FileList(PDF_EXT, 32, thumbs=False)
        self.lst.filesDropped.connect(self.lst.add_files)
        v.addLayout(list_bar(self.lst, self.add, extra=False))
        v.addWidget(self.lst)
        f = QFormLayout()
        self.cb_t = QComboBox()
        self.cb_t.addItems([t[0] for t in self.TARGETS])
        f.addRow("변환 형식", self.cb_t)
        f.addRow(QLabel("※ 텍스트가 있는 PDF만 가능 (스캔 이미지 PDF는 내용 추출 불가)\n"
                        "※ Excel 변환: 표를 찾아 시트별로 저장, 표가 없으면 텍스트를 줄 단위로 저장"))
        row, self.ed_out = dir_row(self, "비우면 원본 폴더\\변환 폴더")
        f.addRow("출력 폴더", row)
        v.addLayout(f)
        v.addWidget(run_button("PDF → 문서 변환", self.run))

    def add(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "PDF 선택", "", PDF_FILTER)
        if fs:
            self.lst.add_files(fs)

    def run(self):
        paths = self.lst.paths()
        if not paths:
            QMessageBox.information(self, APP_NAME, "PDF 파일을 추가하세요.")
            return
        _, ext, func = self.TARGETS[self.cb_t.currentIndex()]
        outs, errs = [], []
        pd = progress(self, "변환 중...", len(paths))
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            for k, p in enumerate(paths):
                if pd.wasCanceled():
                    break
                pd.setLabelText(os.path.basename(p))
                QApplication.processEvents()
                try:
                    dst = out_path(p, self.ed_out.text().strip(), ext)
                    func(p, dst)
                    outs.append(dst)
                except Exception as ex:
                    errs.append(f"{os.path.basename(p)}: {ex}")
                pd.setValue(k + 1)
        finally:
            QApplication.restoreOverrideCursor()
            pd.close()
        msg = f"{len(outs)}개 변환 완료" + (f"\n{os.path.dirname(outs[-1])}" if outs else "")
        if errs:
            msg += "\n\n실패:\n" + "\n".join(errs[:10])
        QMessageBox.information(self, APP_NAME, msg)


class ConvertTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        v = QVBoxLayout(self)
        v.setContentsMargins(4, 4, 4, 4)
        t = QTabWidget()
        t.setDocumentMode(True)
        t.addTab(Pdf2ImgPanel(), "PDF → 이미지")
        t.addTab(Img2PdfPanel(), "이미지 → PDF")
        t.addTab(Office2PdfPanel(), "Excel·Word·PPT·한글 → PDF")
        t.addTab(Pdf2DocPanel(), "PDF → Word·Excel·텍스트")
        v.addWidget(t)


# ───────────────────────── 메인 ─────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{VERSION}")
        self.resize(1280, 820)
        self.setStatusBar(QStatusBar())
        self.lbl_doc = QLabel("")
        self.statusBar().addPermanentWidget(self.lbl_doc)
        self.tabs = QTabWidget()
        self.pdf = PdfTab(self)
        self.img = ImageTab(self)
        self.conv = ConvertTab(self)
        self.tabs.addTab(self.pdf, "  PDF 편집  ")
        self.tabs.addTab(self.img, "  사진 편집  ")
        self.tabs.addTab(self.conv, "  PDF ↔ 이미지 변환  ")
        self.setCentralWidget(self.tabs)
        self.pdf._update_state()

    def set_status(self, text):
        self.lbl_doc.setText(text)

    def closeEvent(self, e):
        if self.pdf.confirm_discard():
            e.accept()
        else:
            e.ignore()


STYLE = """
QWidget{font-family:'Malgun Gothic';font-size:9pt;}
QToolBar{spacing:2px;border:none;background:#f4f4f4;}
QToolButton{padding:4px 7px;border-radius:3px;}
QToolButton:hover{background:#dde8f5;}
QToolButton:checked{background:#2d6cdf;color:white;}
QGroupBox{font-weight:bold;border:1px solid #ccc;border-radius:4px;margin-top:8px;padding-top:6px;}
QGroupBox::title{subcontrol-origin:margin;left:8px;padding:0 3px;}
QPushButton{padding:4px 10px;}
QTabBar::tab{padding:7px 14px;}
QTabBar::tab:selected{font-weight:bold;}
"""


LOG_DIR = os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'), 'PdfImageEditor')


def setup_crash_log():
    import traceback
    import faulthandler
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        log = os.path.join(LOG_DIR, 'error.log')
        fh = open(os.path.join(LOG_DIR, 'crash.log'), 'w', encoding='utf-8')
        faulthandler.enable(fh)
    except Exception:
        log = None

    def hook(et, ev, tb):
        msg = ''.join(traceback.format_exception(et, ev, tb))
        try:
            if log:
                with open(log, 'a', encoding='utf-8') as f:
                    f.write(msg + '\n')
        except Exception:
            pass
        try:
            if QApplication.instance():
                QMessageBox.critical(None, APP_NAME, f"오류가 발생했습니다.\n\n{ev}\n\n로그: {log}")
            elif sys.platform == 'win32':
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, msg[-1500:], APP_NAME, 0x10)
        except Exception:
            pass
    sys.excepthook = hook


def main():
    setup_crash_log()
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("CnC.PdfImageEditor")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    ico = resource_path("app.ico")
    if os.path.exists(ico):
        app.setWindowIcon(QIcon(ico))
    w = MainWindow()
    w.show()
    if len(sys.argv) > 1 and sys.argv[1].lower().endswith('.pdf') and os.path.isfile(sys.argv[1]):
        w.pdf.load(sys.argv[1])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
