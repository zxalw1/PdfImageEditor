# -*- coding: utf-8 -*-
"""공용 위젯·헬퍼"""
import os

from PySide6.QtCore import Qt, QSize, QRect, QPoint, Signal
from PySide6.QtGui import QPixmap, QImage, QIcon, QPainter, QPen, QColor
from PySide6.QtWidgets import (
    QApplication, QListWidget, QListWidgetItem, QAbstractItemView, QLabel, QListView,
    QHBoxLayout, QVBoxLayout, QFormLayout, QLineEdit, QPushButton, QFileDialog, QFrame, QWidget,
    QStyledItemDelegate, QStyleOptionViewItem, QSizePolicy,
)

from app.core.utils import collect_files, human
from app.core.image_ops import open_image
from app.ui import theme
from app.ui.theme import bind_icon


# ── 변환 헬퍼 ──
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


def framed(pm, color=None):
    """페이지 썸네일 둘레에 1px 테두리 (흰 배경에서도 페이지 경계가 보이도록)"""
    out = QPixmap(pm.width() + 2, pm.height() + 2)
    out.fill(QColor(color or theme.C['border_strong']))
    p = QPainter(out)
    p.drawPixmap(1, 1, pm)
    p.end()
    return out


def plain_icon(pm):
    """선택 시 파란 덧칠 없이 그대로 보이는 아이콘"""
    ic = QIcon()
    ic.addPixmap(pm, QIcon.Normal)
    ic.addPixmap(pm, QIcon.Selected)
    return ic


# ── 버튼·레이아웃 헬퍼 ──
def icon_button(text, icon, slot=None, kind="Ghost", tip=None, size=16):
    b = QPushButton((" " + text) if text else "")
    if kind:
        b.setObjectName(kind)
    bind_icon(b, icon, 'on_accent' if kind == "Primary" else ('text2' if kind == "Ghost" else 'text'), size)
    b.setIconSize(QSize(size, size))
    b.setCursor(Qt.PointingHandCursor)
    if tip:
        b.setToolTip(tip)
    if slot:
        b.clicked.connect(slot)
    return b


def run_button(text, slot, icon="play"):
    b = icon_button(text, icon, slot, kind="Primary")
    b.setMinimumHeight(40)
    return b


def card(layout_cls=QVBoxLayout, margins=(16, 14, 16, 16), spacing=10):
    f = QFrame(objectName="Card")
    lay = layout_cls(f)
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    return f, lay


def dir_row(parent, placeholder):
    h = QHBoxLayout()
    h.setSpacing(6)
    ed = QLineEdit()
    ed.setPlaceholderText(placeholder)

    def pick():
        d = QFileDialog.getExistingDirectory(parent, "폴더 선택", ed.text())
        if d:
            ed.setText(d)
    b = icon_button("", "open", pick, kind=None, tip="폴더 선택")
    b.setFixedWidth(36)
    h.addWidget(ed)
    h.addWidget(b)
    return h, ed


def list_bar(lst, add_slot, extra=True, add_folder=None):
    bar = QHBoxLayout()
    bar.setSpacing(2)
    items = [("추가", "plus", add_slot)]
    if add_folder:
        items.append(("폴더", "folder-add", add_folder))
    items.append(("삭제", "minus", lst.remove_selected))
    if extra:
        items += [("", "arrow-up", lambda: lst.move_selected(-1)), ("", "arrow-down", lambda: lst.move_selected(1)),
                  ("이름순", "sort", lst.sort_by_name)]
    items += [("비우기", "trash", lst.clear)]
    tips = {"arrow-up": "위로", "arrow-down": "아래로"}
    for t, ic, s in items:
        bar.addWidget(icon_button(t, ic, s, tip=tips.get(ic)))
    return bar


# ── 위젯 ──
class FileList(QListWidget):
    filesDropped = Signal(list)
    countChanged = Signal(int)

    def __init__(self, exts, icon=64, parent=None, thumbs=True, placeholder="파일을 여기로 끌어다 놓으세요"):
        super().__init__(parent)
        self.exts = exts
        self.thumbs = thumbs
        self.placeholder = placeholder
        self.setAcceptDrops(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setIconSize(QSize(icon, icon))
        self.icon = icon
        # 바운드 메서드로 연결해야 위젯 삭제 시 Qt가 자동으로 연결을 끊는다 (종료 시 오류 방지)
        self.model().rowsInserted.connect(self._emit_count)
        self.model().rowsRemoved.connect(self._emit_count)
        self.model().modelReset.connect(self._emit_count)

    def _emit_count(self, *_):
        self.countChanged.emit(self.count())

    def paintEvent(self, e):
        super().paintEvent(e)
        if self.count() == 0 and self.placeholder:
            p = QPainter(self.viewport())
            r = self.viewport().rect()
            pm = theme.svg_pixmap("upload", theme.C['text3'], 32)
            p.drawPixmap(r.center().x() - 16, r.center().y() - 34, pm)
            p.setPen(QColor(theme.C['text3']))
            p.drawText(QRect(r.left(), r.center().y() + 6, r.width(), 24), Qt.AlignCenter, self.placeholder)
            p.end()

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
                    it.setText(f"{os.path.basename(p)}   ·  {human(os.path.getsize(p))}")
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
                it.setIcon(plain_icon(pil_thumb_pixmap(im, self.icon)))
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


class _ThumbDelegate(QStyledItemDelegate):
    """썸네일 위, 페이지 번호 아래 (목록 모드 유지 → 드래그 순서변경 그대로)"""

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.decorationPosition = QStyleOptionViewItem.Top
        option.displayAlignment = Qt.AlignHCenter | Qt.AlignTop


class PageList(QListWidget):
    reordered = Signal()

    def __init__(self):
        super().__init__()
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setIconSize(QSize(120, 160))
        self.setSpacing(4)
        self.setViewMode(QListView.ListMode)
        self.setItemDelegate(_ThumbDelegate(self))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def dropEvent(self, e):
        super().dropEvent(e)
        self.reordered.emit()


class PageView(QLabel):
    """페이지 미리보기. 모드: None / 'text'(클릭 위치에 추가) / 'white'(드래그 지우기) / 'edit'(기존 글자 수정)"""
    clicked = Signal(QPoint)
    dragged = Signal(QRect)
    editRequested = Signal(object)      # 클릭한 텍스트 단위 (edit 모드)
    emptyClicked = Signal()             # edit 모드에서 글자 없는 곳 클릭

    def __init__(self):
        super().__init__()
        self.setObjectName("PageView")
        self.setMouseTracking(True)
        self.mode = None
        self._start = None
        self._cur = None
        self.edit_items = []            # [(QRectF 화면 좌표, unit)]
        self._hover = None

    def set_mode(self, m):
        self.mode = m
        self._hover = None
        self.setCursor(Qt.CrossCursor if m in ('text', 'white') else Qt.ArrowCursor)
        self.update()

    def set_edit_items(self, items):
        self.edit_items = items
        self._hover = None
        self.update()

    def item_at(self, pos):
        hits = [it for it in self.edit_items if it[0].adjusted(-2, -2, 2, 2).contains(pos)]
        return min(hits, key=lambda it: it[0].width() * it[0].height()) if hits else None

    def mousePressEvent(self, e):
        if self.mode == 'edit' and e.button() == Qt.LeftButton:
            it = self.item_at(e.position())
            if it:
                self.editRequested.emit(it[1])
            else:
                self.emptyClicked.emit()
            return
        if self.mode and e.button() == Qt.LeftButton:
            self._start = self._cur = e.position().toPoint()
            self.update()

    def mouseMoveEvent(self, e):
        if self.mode == 'edit':
            it = self.item_at(e.position())
            if it is not self._hover:
                self._hover = it
                self.setCursor(Qt.IBeamCursor if it else Qt.ArrowCursor)
                self.setToolTip("클릭해서 글자 수정" if it else "")
                self.update()
            return
        if self._start is not None:
            self._cur = e.position().toPoint()
            self.update()

    def leaveEvent(self, e):
        if self._hover is not None:
            self._hover = None
            self.update()
        super().leaveEvent(e)

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
            p.setPen(QPen(QColor(theme.C['danger']), 1.5, Qt.DashLine))
            p.setBrush(QColor(255, 255, 255, 170))
            p.drawRect(QRect(self._start, self._cur).normalized())
            p.end()
        elif self.mode == 'edit' and self.edit_items:
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            acc = QColor(theme.C['accent'])
            faint = QColor(acc)
            faint.setAlpha(70)
            p.setPen(QPen(faint, 1, Qt.DotLine))
            p.setBrush(Qt.NoBrush)
            for r, _u in self.edit_items:          # 수정 가능한 영역 옅게 표시
                p.drawRect(r.adjusted(-1, -1, 1, 1))
            if self._hover:
                fill = QColor(acc)
                fill.setAlpha(28)
                p.setPen(QPen(acc, 1.5, Qt.DashLine))
                p.setBrush(fill)
                p.drawRoundedRect(self._hover[0].adjusted(-2, -2, 2, 2), 3, 3)
            p.end()


class InlineTextEditor(QFrame):
    """페이지 위 제자리 편집 상자. Ctrl+Enter 확인 / Esc 취소"""
    committed = Signal(str)
    cancelled = Signal()

    def __init__(self, parent, text, px_size, color, family, min_width):
        super().__init__(parent, objectName="InlineEditor")
        from PySide6.QtWidgets import QPlainTextEdit
        from PySide6.QtGui import QFont, QFontMetrics
        px = max(11, int(round(px_size)))
        # 전역 QSS 의 font-size 가 setFont 를 덮어쓰므로 스타일시트로 크기 지정 (원본 글자 크기와 맞춤)
        self.setStyleSheet(
            f"QFrame#InlineEditor{{background:{theme.C['surface']};border:1.5px solid {theme.C['accent']};"
            f"border-radius:6px;}}"
            f"QPlainTextEdit{{background:#FFFFFF;border:none;padding:0;color:{color};"
            f"font-family:'{family}';font-size:{px}px;"
            f"selection-background-color:{theme.C['accent']};}}")
        v = QVBoxLayout(self)
        v.setContentsMargins(3, 3, 3, 3)
        v.setSpacing(3)
        self.ed = QPlainTextEdit()
        f = QFont(family)
        f.setPixelSize(px)
        self.ed.setFont(f)
        self.ed.setPlainText(text)
        self.ed.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.ed.installEventFilter(self)
        v.addWidget(self.ed)
        bar = QHBoxLayout()
        bar.setSpacing(4)
        hint = QLabel("Ctrl+Enter 확인 · Esc 취소", objectName="Caption")
        bar.addWidget(hint)
        bar.addStretch()
        b_no = QPushButton("취소")
        b_no.clicked.connect(self.cancelled.emit)
        b_ok = QPushButton("확인", objectName="Primary")
        b_ok.setStyleSheet("padding:4px 12px;")
        b_ok.clicked.connect(self.commit)
        for b in (b_no, b_ok):
            b.setCursor(Qt.PointingHandCursor)
            bar.addWidget(b)
        v.addLayout(bar)
        self.ed.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.ed.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._fm = QFontMetrics(f)
        self._min_w = min_width
        self.ed.textChanged.connect(self._fit)
        self._fit()

    def _fit(self):
        """입력에 맞춰 상자 크기 자동 조절 (스크롤 없이 전체 내용 보이게)"""
        fm = self._fm
        lines = self.ed.toPlainText().split("\n") or [""]
        w = max(self._min_w, max(fm.horizontalAdvance(ln) for ln in lines) + 36, 260)
        par = self.parentWidget()
        if par is not None:
            w = min(w, max(260, par.width() - self.x() - 4))
        h = fm.lineSpacing() * len(lines) + 22 + 34
        self.resize(int(w), int(h))

    def commit(self):
        self.committed.emit(self.ed.toPlainText())

    def eventFilter(self, obj, e):
        from PySide6.QtCore import QEvent
        if obj is self.ed and e.type() == QEvent.KeyPress:
            if e.key() in (Qt.Key_Return, Qt.Key_Enter) and e.modifiers() & Qt.ControlModifier:
                self.commit()
                return True
            if e.key() == Qt.Key_Escape:
                self.cancelled.emit()
                return True
        return super().eventFilter(obj, e)

    def focus(self):
        self.show()
        self.raise_()
        self.ed.setFocus()
        self.ed.selectAll()


class DropZone(QFrame):
    """빈 화면용 큰 드롭존. 클릭하면 clicked, 파일 놓으면 filesDropped"""
    clicked = Signal()
    filesDropped = Signal(list)

    def __init__(self, exts, title, subtitle, buttons=()):
        super().__init__(objectName="DropZone")
        self.exts = exts
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        v = QVBoxLayout(self)
        v.setAlignment(Qt.AlignCenter)
        v.setSpacing(10)
        ic = QLabel()
        ic.setAlignment(Qt.AlignCenter)
        bind_icon(ic, "upload", 'accent', 56)
        v.addWidget(ic)
        t = QLabel(title, objectName="H1")
        t.setAlignment(Qt.AlignCenter)
        v.addWidget(t)
        s = QLabel(subtitle, objectName="Muted")
        s.setAlignment(Qt.AlignCenter)
        v.addWidget(s)
        if buttons:
            v.addSpacing(8)
            hb = QHBoxLayout()
            hb.setAlignment(Qt.AlignCenter)
            hb.setSpacing(8)
            for b in buttons:
                hb.addWidget(b)
            v.addLayout(hb)

    def _set_drag(self, on):
        self.setProperty("drag", on)
        self.style().unpolish(self)
        self.style().polish(self)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            self._set_drag(True)
            e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self._set_drag(False)

    def dropEvent(self, e):
        self._set_drag(False)
        files = collect_files([u.toLocalFile() for u in e.mimeData().urls()], self.exts)
        if files:
            self.filesDropped.emit(files)
        e.acceptProposedAction()


class ChoiceCard(QFrame):
    """선택형 카드 (아이콘 + 제목 + 설명)"""
    clicked = Signal()

    def __init__(self, icon, title, desc):
        super().__init__(objectName="Card")
        self.setProperty("clickable", True)
        self.setProperty("selected", False)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(132)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 16, 18, 16)
        v.setSpacing(4)
        ic = QLabel(objectName="CardIcon")
        ic.setFixedSize(44, 44)
        ic.setAlignment(Qt.AlignCenter)
        bind_icon(ic, icon, 'accent', 26)
        v.addWidget(ic)
        v.addSpacing(6)
        v.addWidget(QLabel(title, objectName="H2"))
        d = QLabel(desc, objectName="Muted")
        d.setWordWrap(True)
        v.addWidget(d)
        v.addStretch()

    def set_selected(self, on):
        self.setProperty("selected", on)
        for w in [self] + self.findChildren(QLabel):
            w.style().unpolish(w)
            w.style().polish(w)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()


class FilePanel(QWidget):
    """[파일 목록 카드] [옵션 카드] 2단 구성. 하위 클래스가 self.form 에 옵션을 채운다"""

    def __init__(self, exts, icon=32, thumbs=False, extra=True, run_text="실행", run_icon="play",
                 file_filter="", dialog_title="파일 추가", folder=False, placeholder=None):
        super().__init__()
        self.file_filter = file_filter
        self.dialog_title = dialog_title
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(14)

        left, lv = card(margins=(14, 10, 14, 14), spacing=8)
        self.lst = FileList(exts, icon, thumbs=thumbs,
                            placeholder=placeholder or "파일을 여기로 끌어다 놓거나 ‘추가’를 누르세요")
        self.lst.filesDropped.connect(self.lst.add_files)
        hh = QHBoxLayout()
        self.lb_count = QLabel("파일 0개", objectName="H2")
        hh.addWidget(self.lb_count)
        hh.addStretch()
        hh.addLayout(list_bar(self.lst, self.add, extra, self.add_folder if folder else None))
        lv.addLayout(hh)
        lv.addWidget(self.lst, 1)
        self.lst.countChanged.connect(lambda n: self.lb_count.setText(f"파일 {n}개"))
        h.addWidget(left, 3)

        right, rv = card(margins=(16, 12, 16, 16), spacing=10)
        right.setMinimumWidth(320)
        right.setMaximumWidth(440)
        rv.addWidget(QLabel("옵션", objectName="H2"))
        self.form = QFormLayout()
        self.form.setSpacing(10)
        self.form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        rv.addLayout(self.form)
        self.extra_box = QVBoxLayout()
        rv.addLayout(self.extra_box)
        rv.addStretch()
        rv.addWidget(run_button(run_text, self.run, run_icon))
        h.addWidget(right, 2)

    def add(self):
        fs, _ = QFileDialog.getOpenFileNames(self, self.dialog_title, "", self.file_filter)
        if fs:
            self.lst.add_files(fs)

    def add_folder(self):
        d = QFileDialog.getExistingDirectory(self, "폴더 추가")
        if d:
            self.lst.add_files(collect_files([d], self.lst.exts))

    def run(self):  # pragma: no cover - 하위 클래스에서 구현
        raise NotImplementedError
