# -*- coding: utf-8 -*-
"""공용 위젯·헬퍼"""
import os

from PySide6.QtCore import Qt, QSize, QRect, QPoint, Signal
from PySide6.QtGui import QPixmap, QImage, QIcon, QPainter, QPen, QColor
from PySide6.QtWidgets import (
    QApplication, QListWidget, QListWidgetItem, QAbstractItemView, QLabel, QListView,
    QHBoxLayout, QLineEdit, QPushButton, QFileDialog,
)

from app.core.utils import collect_files, human
from app.core.image_ops import open_image


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


# ── 레이아웃 헬퍼 ──
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


def run_button(text, slot, font_px=13):
    b = QPushButton(text)
    b.setMinimumHeight(38)
    b.setStyleSheet(f"font-weight:bold;font-size:{font_px}px;")
    b.clicked.connect(slot)
    return b


# ── 위젯 ──
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
