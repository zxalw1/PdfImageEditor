# -*- coding: utf-8 -*-
"""대화상자"""
import os

from PySide6.QtCore import Qt, QPointF, QBuffer, QIODevice
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QImage
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QHBoxLayout, QVBoxLayout, QRadioButton, QButtonGroup, QSpinBox, QLineEdit,
    QLabel, QCheckBox, QDialogButtonBox, QInputDialog, QWidget, QFrame, QComboBox, QPushButton,
    QMessageBox,
)

from app.core.utils import parse_ranges
from app.core.pdf_ops import split_each, split_every


def ask_password(parent):
    """pdf_ops.open_pdf 의 password_cb 로 사용"""
    def cb(path):
        pw, ok = QInputDialog.getText(parent, "암호", f"{os.path.basename(path)} 암호:", QLineEdit.Password)
        return pw if ok else None
    return cb


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
        h1 = QHBoxLayout()
        h1.addWidget(self.r_every)
        h1.addWidget(self.sp_n)
        h1.addStretch()
        f.addRow(h1)
        h2 = QHBoxLayout()
        h2.addWidget(self.r_range)
        h2.addWidget(self.ed_range)
        f.addRow(h2)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def groups(self):
        if self.r_each.isChecked():
            return split_each(self.n)
        if self.r_every.isChecked():
            return split_every(self.n, self.sp_n.value())
        return parse_ranges(self.ed_range.text(), self.n)


class SignatureCanvas(QWidget):
    """마우스로 서명 그리기 (투명 배경 PNG 로 내보냄)"""
    SCALE = 3          # 내보낼 때 해상도 배율

    def __init__(self):
        super().__init__()
        self.setMinimumSize(560, 220)
        self.setCursor(Qt.CrossCursor)
        self.strokes = []          # [(QColor, width, [QPointF])]
        self.color = QColor("#111827")
        self.width_px = 3.0

    def clear(self):
        self.strokes = []
        self.update()

    def is_empty(self):
        return not any(len(s[2]) > 1 for s in self.strokes)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.strokes.append((QColor(self.color), self.width_px, [e.position()]))
            self.update()

    def mouseMoveEvent(self, e):
        if self.strokes and e.buttons() & Qt.LeftButton:
            self.strokes[-1][2].append(e.position())
            self.update()

    @staticmethod
    def _path(pts):
        path = QPainterPath(pts[0])
        if len(pts) < 3:
            for p in pts[1:]:
                path.lineTo(p)
            return path
        for i in range(1, len(pts) - 1):        # 중점 2차 곡선으로 부드럽게
            mid = (pts[i] + pts[i + 1]) / 2
            path.quadTo(pts[i], mid)
        path.lineTo(pts[-1])
        return path

    def _draw(self, p, scale=1.0):
        p.setRenderHint(QPainter.Antialiasing)
        for col, w, pts in self.strokes:
            if len(pts) == 1:
                pts = [pts[0], pts[0] + QPointF(0.1, 0.1)]
            p.setPen(QPen(col, w * scale, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            p.drawPath(self._path([q * scale for q in pts]))

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#FFFFFF"))
        p.setPen(QPen(QColor("#CBD2DC"), 1, Qt.DashLine))
        y = int(self.height() * 0.72)
        p.drawLine(24, y, self.width() - 24, y)
        if self.is_empty():
            p.setPen(QColor("#A3AAB5"))
            p.drawText(self.rect(), Qt.AlignCenter, "여기에 마우스로 서명하세요")
        self._draw(p)
        p.end()

    def to_png(self):
        s = self.SCALE
        img = QImage(self.width() * s, self.height() * s, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        self._draw(p, s)
        p.end()
        # 그린 부분만 잘라내기
        pts = [q for _c, _w, st in self.strokes for q in st]
        pad = max(w for _c, w, _s in self.strokes) * s + 6
        x0 = max(0, int(min(q.x() for q in pts) * s - pad))
        y0 = max(0, int(min(q.y() for q in pts) * s - pad))
        x1 = min(img.width(), int(max(q.x() for q in pts) * s + pad))
        y1 = min(img.height(), int(max(q.y() for q in pts) * s + pad))
        img = img.copy(x0, y0, max(1, x1 - x0), max(1, y1 - y0))
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        img.save(buf, "PNG")
        return bytes(buf.data()), (img.width(), img.height())


class SignatureDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("서명 그리기")
        self.result_png = None
        v = QVBoxLayout(self)
        v.setSpacing(10)
        v.addWidget(QLabel("마우스로 서명한 뒤 ‘확인’을 누르세요. 배경은 투명하게 들어갑니다.", objectName="Muted"))
        self.canvas = SignatureCanvas()
        frame = QFrame(objectName="Card")
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(1, 1, 1, 1)
        fl.addWidget(self.canvas)
        v.addWidget(frame)
        h = QHBoxLayout()
        h.addWidget(QLabel("굵기"))
        self.cb_w = QComboBox()
        self.cb_w.addItems(["가늘게", "보통", "굵게"])
        self.cb_w.setCurrentIndex(1)
        self.cb_w.currentIndexChanged.connect(lambda i: setattr(self.canvas, "width_px", [2.0, 3.0, 4.5][i]))
        h.addWidget(self.cb_w)
        h.addSpacing(10)
        h.addWidget(QLabel("색"))
        self.cb_c = QComboBox()
        self.cb_c.addItems(["검정", "파랑"])
        self.cb_c.currentIndexChanged.connect(
            lambda i: setattr(self.canvas, "color", QColor(["#111827", "#1D3FB8"][i])))
        h.addWidget(self.cb_c)
        h.addStretch()
        b_clear = QPushButton("지우기")
        b_clear.clicked.connect(self.canvas.clear)
        h.addWidget(b_clear)
        v.addLayout(h)
        self.cb_save = QCheckBox("이 서명 저장해두기 (다음에 ‘저장된 서명’에서 바로 사용)")
        self.cb_save.setChecked(True)
        v.addWidget(self.cb_save)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("확인")
        bb.button(QDialogButtonBox.Ok).setObjectName("Primary")
        bb.button(QDialogButtonBox.Cancel).setText("취소")
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def _ok(self):
        if self.canvas.is_empty():
            QMessageBox.information(self, "서명 그리기", "서명을 그려 주세요.")
            return
        self.result_png = self.canvas.to_png()
        self.accept()


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
