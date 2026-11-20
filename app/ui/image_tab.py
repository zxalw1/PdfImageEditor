# -*- coding: utf-8 -*-
"""사진 편집 탭 (일괄 변환)"""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QFormLayout, QPushButton, QLabel, QGroupBox, QComboBox,
    QSlider, QCheckBox, QSpinBox, QLineEdit, QFileDialog, QMessageBox,
)

from app import APP_NAME
from app.core.utils import HEIF, IMG_EXT, IMG_FILTER, SAVE_FORMATS, collect_files, human
from app.core.image_ops import open_image, batch_convert, TransformOptions
from app.ui.widgets import FileList, pil_thumb_pixmap, run_button
from app.ui.workers import run_task


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
        self.sp_pct = QSpinBox()
        self.sp_pct.setRange(1, 1000)
        self.sp_pct.setValue(50)
        self.sp_pct.setSuffix(" %")
        self.sp_w = QSpinBox()
        self.sp_w.setRange(1, 20000)
        self.sp_w.setValue(1920)
        self.sp_h = QSpinBox()
        self.sp_h.setRange(1, 20000)
        self.sp_h.setValue(1080)
        self.cb_keep = QCheckBox("비율 유지(범위 안에 맞춤)")
        self.cb_keep.setChecked(True)
        self.cb_noup = QCheckBox("원본보다 크게 확대 안 함")
        self.cb_noup.setChecked(True)
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

        right.addWidget(run_button("실행", self.run, font_px=14))
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

    def options(self):
        return TransformOptions(
            rotate=self.cb_rot.currentIndex(),
            flip_x=self.cb_fx.isChecked(),
            flip_y=self.cb_fy.isChecked(),
            resize_mode=self.cb_resize.currentIndex(),
            pct=self.sp_pct.value(),
            width=self.sp_w.value(),
            height=self.sp_h.value(),
            keep_ratio=self.cb_keep.isChecked(),
            no_upscale=self.cb_noup.isChecked(),
        )

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
        opts = self.options()
        res = run_task(self, "이미지 처리 중...", len(paths),
                       lambda t: batch_convert(paths, fsel, q, tkb, suffix, out_dir, opts, t))
        msg = f"완료 {res.ok}건 / 실패 {len(res.errors)}건\n용량: {human(res.before)} → {human(res.after)}"
        if res.before:
            msg += f" ({(1 - res.after / res.before) * 100:+.1f}% 감소)".replace("+-", "+").replace("% 감소", "%")
        if res.last_dir:
            msg += f"\n저장 위치: {res.last_dir}"
        if res.errors:
            msg += "\n\n" + "\n".join(res.errors[:10])
        QMessageBox.information(self, APP_NAME, msg)
