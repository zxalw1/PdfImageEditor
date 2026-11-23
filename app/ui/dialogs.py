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


class PageDecoDialog(QDialog):
    """페이지 번호 · 머리글/바닥글 · 워터마크 설정 + 미리보기"""
    COLORS = [("진한 회색", (0.2, 0.2, 0.2)), ("검정", (0, 0, 0)), ("파랑", (0.15, 0.35, 0.9)),
              ("빨강", (0.86, 0.15, 0.15)), ("연한 회색", (0.55, 0.55, 0.55))]

    def __init__(self, doc, cur_index, filename, parent=None):
        super().__init__(parent)
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QGroupBox, QGridLayout, QScrollArea, QSlider
        from app.core import page_deco as pdc
        self.pdc = pdc
        self.doc = doc
        self.filename = filename
        self.wm_image = None
        self.setWindowTitle("페이지 번호 · 머리글/바닥글 · 워터마크")
        self.resize(1080, 720)
        root = QHBoxLayout(self)
        root.setSpacing(14)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 6, 0)
        lv.setSpacing(10)
        top = QFormLayout()
        self.ed_pages = QLineEdit()
        self.ed_pages.setPlaceholderText("비우면 전체 (예: 2-10)")
        top.addRow("적용할 페이지", self.ed_pages)
        self.cb_color = QComboBox()
        self.cb_color.addItems([c[0] for c in self.COLORS])
        top.addRow("글자 색", self.cb_color)
        lv.addLayout(top)

        # 페이지 번호
        self.g_num = QGroupBox("페이지 번호")
        self.g_num.setCheckable(True)
        self.g_num.setChecked(True)
        f = QFormLayout(self.g_num)
        self.cb_fmt = QComboBox()
        self.cb_fmt.addItems(list(pdc.NUM_FORMATS))
        self.cb_fmt.setCurrentText("1 / 10")
        f.addRow("모양", self.cb_fmt)
        self.cb_pos = QComboBox()
        self.cb_pos.addItems(pdc.POSITIONS)
        f.addRow("위치", self.cb_pos)
        h = QHBoxLayout()
        self.sp_start = QSpinBox()
        self.sp_start.setRange(0, 99999)
        self.sp_start.setValue(1)
        self.sp_nsize = QSpinBox()
        self.sp_nsize.setRange(6, 48)
        self.sp_nsize.setValue(10)
        self.sp_nsize.setSuffix(" pt")
        h.addWidget(QLabel("시작"))
        h.addWidget(self.sp_start)
        h.addWidget(QLabel("크기"))
        h.addWidget(self.sp_nsize)
        f.addRow(h)
        self.cb_skip = QCheckBox("첫 페이지(표지)는 번호 없이")
        f.addRow(self.cb_skip)
        lv.addWidget(self.g_num)

        # 머리글·바닥글
        self.g_hf = QGroupBox("머리글 · 바닥글")
        self.g_hf.setCheckable(True)
        self.g_hf.setChecked(False)
        g = QGridLayout(self.g_hf)
        for c, t in enumerate(("왼쪽", "가운데", "오른쪽")):
            lb = QLabel(t, objectName="Caption")
            lb.setAlignment(Qt.AlignCenter)
            g.addWidget(lb, 0, c + 1)
        self.hf_edits = {}
        for r, (key, name) in enumerate((("header", "머리글"), ("footer", "바닥글"))):
            g.addWidget(QLabel(name), r + 1, 0)
            for c in range(3):
                ed = QLineEdit()
                self.hf_edits[(key, c)] = ed
                g.addWidget(ed, r + 1, c + 1)
        self.hf_edits[("header", 0)].setText("{file}")
        self.hf_edits[("header", 2)].setText("{date}")
        self.sp_hsize = QSpinBox()
        self.sp_hsize.setRange(6, 36)
        self.sp_hsize.setValue(9)
        self.sp_hsize.setSuffix(" pt")
        g.addWidget(QLabel("크기"), 3, 0)
        g.addWidget(self.sp_hsize, 3, 1)
        cap = QLabel(pdc.PLACEHOLDERS, objectName="Caption")
        cap.setWordWrap(True)
        g.addWidget(cap, 4, 0, 1, 4)
        lv.addWidget(self.g_hf)

        # 워터마크
        self.g_wm = QGroupBox("워터마크")
        self.g_wm.setCheckable(True)
        self.g_wm.setChecked(False)
        f3 = QFormLayout(self.g_wm)
        hk = QHBoxLayout()
        self.r_wtext = QRadioButton("글자")
        self.r_wimg = QRadioButton("이미지")
        self.r_wtext.setChecked(True)
        bg = QButtonGroup(self)
        bg.addButton(self.r_wtext)
        bg.addButton(self.r_wimg)
        hk.addWidget(self.r_wtext)
        hk.addWidget(self.r_wimg)
        hk.addStretch()
        f3.addRow("종류", hk)
        self.ed_wm = QLineEdit("대외비")
        f3.addRow("글자", self.ed_wm)
        hw = QHBoxLayout()
        self.sp_wsize = QSpinBox()
        self.sp_wsize.setRange(10, 200)
        self.sp_wsize.setValue(60)
        self.sp_wsize.setSuffix(" pt")
        self.cb_angle = QComboBox()
        self.cb_angle.addItems(["45°", "30°", "0°", "90°"])
        hw.addWidget(self.sp_wsize)
        hw.addWidget(QLabel("각도"))
        hw.addWidget(self.cb_angle)
        f3.addRow("크기", hw)
        hi = QHBoxLayout()
        self.b_img = QPushButton("이미지 선택…")
        self.b_img.clicked.connect(self._pick_image)
        self.lb_img = QLabel("선택 안 함", objectName="Caption")
        self.sp_scale = QSpinBox()
        self.sp_scale.setRange(5, 100)
        self.sp_scale.setValue(50)
        self.sp_scale.setSuffix(" % 폭")
        hi.addWidget(self.b_img)
        hi.addWidget(self.lb_img, 1)
        hi.addWidget(self.sp_scale)
        f3.addRow("이미지", hi)
        ho = QHBoxLayout()
        self.sl_op = QSlider(Qt.Horizontal)
        self.sl_op.setRange(5, 100)
        self.sl_op.setValue(25)
        self.lb_op = QLabel("25%")
        self.lb_op.setFixedWidth(40)
        self.sl_op.valueChanged.connect(lambda v: self.lb_op.setText(f"{v}%"))
        ho.addWidget(self.sl_op)
        ho.addWidget(self.lb_op)
        f3.addRow("진하기", ho)
        self.cb_behind = QCheckBox("본문 뒤에 넣기 (글자를 가리지 않음, 배경이 꽉 찬 페이지에선 안 보일 수 있음)")
        f3.addRow(self.cb_behind)
        lv.addWidget(self.g_wm)
        lv.addStretch()

        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sc.setWidget(left)
        sc.setMinimumWidth(580)
        left.setMaximumWidth(560)
        for ed in self.hf_edits.values():
            ed.setMinimumWidth(60)
        root.addWidget(sc, 1)

        # 미리보기
        right = QFrame(objectName="Card")
        rv = QVBoxLayout(right)
        rv.setContentsMargins(12, 10, 12, 12)
        hh = QHBoxLayout()
        hh.addWidget(QLabel("미리보기", objectName="H2"))
        hh.addStretch()
        hh.addWidget(QLabel("페이지"))
        self.sp_prev = QSpinBox()
        self.sp_prev.setRange(1, doc.page_count)
        self.sp_prev.setValue(cur_index + 1)
        hh.addWidget(self.sp_prev)
        rv.addLayout(hh)
        self.lb_prev = QLabel(objectName="Preview")
        self.lb_prev.setAlignment(Qt.AlignCenter)
        self.lb_prev.setMinimumSize(380, 500)
        rv.addWidget(self.lb_prev, 1)
        self.lb_err = QLabel("", objectName="Caption")
        rv.addWidget(self.lb_err)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("적용")
        bb.button(QDialogButtonBox.Ok).setObjectName("Primary")
        bb.button(QDialogButtonBox.Cancel).setText("취소")
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        rv.addWidget(bb)
        root.addWidget(right, 1)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self.update_preview)
        for cls, sig in ((QLineEdit, "textChanged"), (QComboBox, "currentIndexChanged"), (QSpinBox, "valueChanged"),
                         (QSlider, "valueChanged"), (QCheckBox, "toggled"), (QRadioButton, "toggled"),
                         (QGroupBox, "toggled")):
            for w in self.findChildren(cls):
                getattr(w, sig).connect(lambda *_: self._timer.start())
        self.update_preview()

    def _pick_image(self):
        from PySide6.QtWidgets import QFileDialog
        from app.core.utils import IMG_FILTER
        from app.core.overlay import prepare_image
        p, _ = QFileDialog.getOpenFileName(self, "워터마크 이미지", "", IMG_FILTER)
        if p:
            self.set_image(prepare_image(p)[0], os.path.basename(p))

    def set_image(self, data, name="이미지"):
        self.wm_image = data
        self.lb_img.setText(name)
        self.r_wimg.setChecked(True)
        self._timer.start()

    def options(self):
        pdc = self.pdc
        o = pdc.DecoOptions()
        o.pages = self.ed_pages.text()
        o.color = self.COLORS[self.cb_color.currentIndex()][1]
        o.filename = self.filename
        o.numbers = pdc.NumberOpts(self.g_num.isChecked(), self.cb_fmt.currentText(), self.cb_pos.currentText(),
                                   self.sp_start.value(), self.sp_nsize.value(), self.cb_skip.isChecked())
        o.hf = pdc.HeaderFooterOpts(self.g_hf.isChecked(),
                                    tuple(self.hf_edits[("header", c)].text() for c in range(3)),
                                    tuple(self.hf_edits[("footer", c)].text() for c in range(3)),
                                    self.sp_hsize.value())
        o.wm = pdc.WatermarkOpts(self.g_wm.isChecked(), "image" if self.r_wimg.isChecked() else "text",
                                 self.ed_wm.text(), self.sp_wsize.value(), (0.55, 0.55, 0.55),
                                 self.sl_op.value() / 100, float(self.cb_angle.currentText().rstrip("°")),
                                 self.wm_image, self.sp_scale.value() / 100, self.cb_behind.isChecked())
        return o

    def update_preview(self):
        from app.ui.widgets import pix_to_qimage
        from PySide6.QtGui import QPixmap
        try:
            o = self.options()
            pix = self.pdc.preview_page(self.doc, self.sp_prev.value() - 1, o, zoom=1.0)
            pm = QPixmap.fromImage(pix_to_qimage(pix))
            self.lb_prev.setPixmap(pm.scaled(self.lb_prev.size() * 0.98, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.lb_err.setText("")
        except ValueError as ex:
            self.lb_err.setText(str(ex))

    def _ok(self):
        o = self.options()
        if not o.any_enabled:
            QMessageBox.information(self, self.windowTitle(), "넣을 항목을 하나 이상 켜 주세요.")
            return
        try:
            self.pdc.target_pages(o, self.doc.page_count)
        except ValueError as ex:
            QMessageBox.warning(self, self.windowTitle(), str(ex))
            return
        if o.wm.enabled and o.wm.kind == "image" and not o.wm.image:
            QMessageBox.information(self, self.windowTitle(), "워터마크 이미지를 선택해 주세요.")
            return
        self.accept()


class CompressDialog(QDialog):
    """PDF 용량 줄이기 옵션"""

    def __init__(self, current_size_text="", parent=None):
        super().__init__(parent)
        from app.core.compress import PRESETS
        self.setWindowTitle("PDF 용량 줄이기")
        self.presets = PRESETS
        v = QVBoxLayout(self)
        v.setSpacing(10)
        v.addWidget(QLabel("사진·스캔 이미지의 해상도와 품질을 낮춰 용량을 줄입니다. 글자는 그대로 선명합니다.",
                           objectName="Muted"))
        if current_size_text:
            v.addWidget(QLabel(f"현재 문서: {current_size_text}", objectName="Caption"))
        self.radios = []
        g = QButtonGroup(self)
        for i, (name, dpi, q) in enumerate(PRESETS):
            r = QRadioButton(name)
            g.addButton(r)
            v.addWidget(r)
            self.radios.append(r)
        self.r_custom = QRadioButton("직접 지정")
        g.addButton(self.r_custom)
        v.addWidget(self.r_custom)
        self.radios[1].setChecked(True)
        h = QHBoxLayout()
        h.addSpacing(26)
        h.addWidget(QLabel("해상도"))
        self.sp_dpi = QSpinBox()
        self.sp_dpi.setRange(50, 600)
        self.sp_dpi.setValue(150)
        self.sp_dpi.setSuffix(" DPI")
        h.addWidget(self.sp_dpi)
        h.addWidget(QLabel("품질"))
        self.sp_q = QSpinBox()
        self.sp_q.setRange(20, 95)
        self.sp_q.setValue(75)
        h.addWidget(self.sp_q)
        h.addStretch()
        v.addLayout(h)
        for w in (self.sp_dpi, self.sp_q):
            w.valueChanged.connect(lambda *_: self.r_custom.setChecked(True))
        self.cb_gray = QCheckBox("흑백으로 바꾸기 (컬러가 필요 없는 문서면 더 작아짐)")
        v.addWidget(self.cb_gray)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("줄이기")
        bb.button(QDialogButtonBox.Ok).setObjectName("Primary")
        bb.button(QDialogButtonBox.Cancel).setText("취소")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def values(self):
        """(dpi, quality, gray)"""
        for r, (_n, dpi, q) in zip(self.radios, self.presets):
            if r.isChecked():
                return dpi, q, self.cb_gray.isChecked()
        return self.sp_dpi.value(), self.sp_q.value(), self.cb_gray.isChecked()


class PagePickerWindow(QDialog):
    """다른 PDF 의 페이지를 골라 끌어오기 (창을 띄워둔 채 본 창의 썸네일 목록으로 드래그)"""
    from PySide6.QtCore import Signal as _Signal
    insertRequested = _Signal(str, list)
    openRequested = _Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("다른 PDF에서 페이지 가져오기")
        self.setWindowFlag(Qt.Tool, True)
        self.setModal(False)
        self.resize(560, 640)
        self.token = None
        v = QVBoxLayout(self)
        v.setSpacing(8)
        h = QHBoxLayout()
        b_open = QPushButton("PDF 열기…")
        b_open.clicked.connect(self.openRequested.emit)
        h.addWidget(b_open)
        self.lb_file = QLabel("열린 파일 없음", objectName="Muted")
        h.addWidget(self.lb_file, 1)
        v.addLayout(h)
        hint = QLabel("페이지를 골라(Ctrl·Shift로 여러 장) 본 창 왼쪽 썸네일 목록의 원하는 위치로 끌어다 놓으세요.",
                      objectName="Caption")
        hint.setWordWrap(True)
        v.addWidget(hint)
        from app.ui.widgets import SourcePageList
        self.lst = SourcePageList("")
        v.addWidget(self.lst, 1)
        hb = QHBoxLayout()
        hb.addStretch()
        self.b_ins = QPushButton("선택 페이지를 현재 페이지 뒤에 넣기", objectName="Primary")
        self.b_ins.clicked.connect(self._insert)
        hb.addWidget(self.b_ins)
        b_close = QPushButton("닫기")
        b_close.clicked.connect(self.close)
        hb.addWidget(b_close)
        v.addLayout(hb)

    def set_source(self, token, name, pixmaps):
        from PySide6.QtWidgets import QListWidgetItem
        from app.ui.widgets import plain_icon, framed
        self.token = token
        self.lst.token = token
        self.lst.clear()
        for i, pm in enumerate(pixmaps):
            self.lst.addItem(QListWidgetItem(plain_icon(framed(pm)), str(i + 1)))
        self.lb_file.setText(f"{name} · {len(pixmaps)}페이지")

    def _insert(self):
        pages = self.lst.selected_pages()
        if not self.token or not pages:
            QMessageBox.information(self, self.windowTitle(), "가져올 페이지를 선택하세요.")
            return
        self.insertRequested.emit(self.token, pages)


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


class StitchDialog(QDialog):
    """사진 이어붙이기: 방향·크기 맞춤·간격·배경 설정 + 미리보기 → 저장"""
    DIRS = [("세로로 (아래로 이어붙이기)", "vertical"), ("가로로 (옆으로 이어붙이기)", "horizontal"),
            ("격자 (바둑판)", "grid")]
    FITS = [("작은 사진 크기에 맞춤", "min"), ("큰 사진 크기에 맞춤", "max"), ("원본 크기 그대로", "none")]
    BGS = [("흰색", (255, 255, 255)), ("검정", (0, 0, 0)), ("연한 회색", (229, 231, 235)), ("투명 (PNG)", None)]

    def __init__(self, paths, parent=None):
        super().__init__(parent)
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QScrollArea, QSlider
        from app.core import image_ops as io_
        self.io = io_
        self.paths = list(paths)
        self.setWindowTitle(f"사진 이어붙이기 · {len(self.paths)}장")
        self.resize(980, 640)
        # 미리보기용 작은 사진 (원본 비율 유지, 모두 같은 배율로 줄여야 크기 맞춤 계산이 같음)
        self.sizes, thumbs = [], []
        for p in self.paths:
            im = io_.open_image(p)
            self.sizes.append(im.size)
            thumbs.append(im)
        big = max(max(s) for s in self.sizes)
        self.k = min(1.0, 500 / big)
        self.thumbs = [t.resize((max(1, round(t.width * self.k)), max(1, round(t.height * self.k))))
                       for t in thumbs]
        del thumbs

        root = QHBoxLayout(self)
        root.setSpacing(14)
        left = QWidget()
        f = QFormLayout(left)
        f.setSpacing(10)
        self.cb_dir = QComboBox()
        self.cb_dir.addItems([d[0] for d in self.DIRS])
        f.addRow("방향", self.cb_dir)
        self.sp_cols = QSpinBox()
        self.sp_cols.setRange(1, 20)
        self.sp_cols.setValue(min(3, max(2, round(len(self.paths) ** 0.5))))
        self.sp_cols.setSuffix(" 열")
        f.addRow("격자 열 수", self.sp_cols)
        self.cb_fit = QComboBox()
        self.cb_fit.addItems([x[0] for x in self.FITS])
        f.addRow("크기", self.cb_fit)
        self.sp_gap = QSpinBox()
        self.sp_gap.setRange(0, 500)
        self.sp_gap.setSuffix(" px")
        f.addRow("사진 사이 간격", self.sp_gap)
        self.sp_margin = QSpinBox()
        self.sp_margin.setRange(0, 500)
        self.sp_margin.setSuffix(" px")
        f.addRow("바깥 여백", self.sp_margin)
        self.cb_bg = QComboBox()
        self.cb_bg.addItems([b[0] for b in self.BGS])
        f.addRow("배경색", self.cb_bg)
        self.cb_fmt = QComboBox()
        self.cb_fmt.addItems(["JPG", "PNG", "WEBP"])
        f.addRow("저장 형식", self.cb_fmt)
        self.sp_q = QSpinBox()
        self.sp_q.setRange(10, 100)
        self.sp_q.setValue(90)
        f.addRow("품질(JPG/WEBP)", self.sp_q)
        th = QHBoxLayout()
        self.cb_target = QCheckBox("목표 용량 이하")
        self.sp_target = QSpinBox()
        self.sp_target.setRange(10, 100000)
        self.sp_target.setValue(1000)
        self.sp_target.setSuffix(" KB")
        th.addWidget(self.cb_target)
        th.addWidget(self.sp_target)
        f.addRow(th)
        cap = QLabel("목록 순서대로 붙습니다. 순서는 사진 목록에서 ▲▼·끌어서 바꾸세요.", objectName="Caption")
        cap.setWordWrap(True)
        f.addRow(cap)
        left.setMinimumWidth(360)
        left.setMaximumWidth(400)
        root.addWidget(left)

        right = QFrame(objectName="Card")
        rv = QVBoxLayout(right)
        rv.setContentsMargins(12, 10, 12, 12)
        rv.addWidget(QLabel("미리보기", objectName="H2"))
        self.lb_prev = QLabel(objectName="Preview")
        self.lb_prev.setAlignment(Qt.AlignCenter)
        self.lb_prev.setMinimumSize(460, 420)
        rv.addWidget(self.lb_prev, 1)
        self.lb_size = QLabel("", objectName="Muted")
        rv.addWidget(self.lb_size)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("저장…")
        bb.button(QDialogButtonBox.Ok).setObjectName("Primary")
        bb.button(QDialogButtonBox.Cancel).setText("취소")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        rv.addWidget(bb)
        root.addWidget(right, 1)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self.update_preview)
        for w in (self.cb_dir, self.cb_fit, self.cb_bg, self.cb_fmt):
            w.currentIndexChanged.connect(lambda *_: self._timer.start())
        for w in (self.sp_cols, self.sp_gap, self.sp_margin):
            w.valueChanged.connect(lambda *_: self._timer.start())
        self.cb_bg.currentIndexChanged.connect(self._bg_fmt)
        self.update_preview()

    def _bg_fmt(self):
        if self.BGS[self.cb_bg.currentIndex()][1] is None and self.cb_fmt.currentText() == "JPG":
            self.cb_fmt.setCurrentText("PNG")          # 투명은 JPG 불가

    def options(self):
        io_ = self.io
        return io_.StitchOptions(self.DIRS[self.cb_dir.currentIndex()][1], self.sp_cols.value(),
                                 self.FITS[self.cb_fit.currentIndex()][1], self.sp_gap.value(),
                                 self.sp_margin.value(), self.BGS[self.cb_bg.currentIndex()][1])

    def update_preview(self):
        from app.ui.widgets import pil_thumb_pixmap
        o = self.options()
        self.sp_cols.setEnabled(o.direction == self.io.GRID)
        fmt = self.cb_fmt.currentText()
        (W, H), _b = self.io.stitch_layout(self.sizes, o)
        limit = min(o.max_side, self.io.FORMAT_MAX_SIDE.get(fmt, 20000))
        k = min(1.0, limit / max(W, H))
        note = f"  → {fmt} 한계로 {round(W * k)} × {round(H * k)} px 로 줄여 저장" if k < 1 else ""
        self.lb_size.setText(f"결과 크기 {W:,} × {H:,} px{note}")
        # 미리보기: 축소본으로 같은 배치 (간격·여백도 같은 비율)
        po = self.io.StitchOptions(o.direction, o.cols, o.fit, round(o.gap * self.k), round(o.margin * self.k),
                                   o.bg, 4000)
        im = self.io.stitch_images(self.thumbs, po)
        if im.mode == "RGBA":                        # 투명 = 체크무늬로 보여주기
            from PIL import Image
            bgc = Image.new("RGBA", im.size, (255, 255, 255, 255))
            for y in range(0, im.height, 12):
                for x in range((y // 12) % 2 * 12, im.width, 24):
                    bgc.paste((220, 220, 220, 255), (x, y, x + 12, y + 12))
            bgc.alpha_composite(im)
            im = bgc
        side = max(self.lb_prev.width(), self.lb_prev.height(), 420)
        self.lb_prev.setPixmap(pil_thumb_pixmap(im, side).scaled(
            self.lb_prev.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
