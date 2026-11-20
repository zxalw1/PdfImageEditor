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
