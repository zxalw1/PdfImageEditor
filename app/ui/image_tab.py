# -*- coding: utf-8 -*-
"""사진 편집 탭 (일괄 변환)"""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QFormLayout, QLabel, QGroupBox, QComboBox, QSlider,
    QCheckBox, QSpinBox, QLineEdit, QFileDialog, QMessageBox, QScrollArea, QFrame,
)

from app import APP_NAME
from app.core.utils import HEIF, IMG_EXT, IMG_FILTER, SAVE_FORMATS, collect_files, human
from app.core.image_ops import open_image, batch_convert, TransformOptions
from app.ui.widgets import FileList, pil_thumb_pixmap, run_button, card, icon_button, dir_row
from app.ui.workers import run_task


class ImageTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.setObjectName("Page")
        self.win = win
        self._build()

    def status_text(self):
        n = self.lst.count()
        return f"사진 편집    ·    파일 {n}개" if n else "사진 편집    ·    사진을 추가하세요"

    def _build(self):
        h = QHBoxLayout(self)
        h.setContentsMargins(16, 16, 16, 16)
        h.setSpacing(14)

        # 왼쪽: 파일 목록 카드
        left, lv = card(margins=(14, 10, 14, 12), spacing=8)
        hh = QHBoxLayout()
        self.lb_count = QLabel("사진 0개", objectName="H2")
        hh.addWidget(self.lb_count)
        hh.addStretch()
        self.lst = FileList(IMG_EXT, 56, placeholder="사진·폴더를 여기로 끌어다 놓거나 ‘추가’를 누르세요")
        for t, ic, s in [("추가", "plus", self.add), ("폴더", "folder-add", self.add_folder),
                         ("삭제", "minus", lambda: self.lst.remove_selected()),
                         ("비우기", "trash", lambda: self.lst.clear())]:
            hh.addWidget(icon_button(t, ic, s))
        lv.addLayout(hh)
        self.lst.filesDropped.connect(self.lst.add_files)
        self.lst.currentItemChanged.connect(self.show_preview)
        self.lst.countChanged.connect(self._on_count)
        lv.addWidget(self.lst, 1)
        hint = QLabel("JPG·PNG·WEBP·BMP·TIFF·GIF·ICO" + (" ·HEIC" if HEIF else "  (HEIC: pip install pillow-heif)"),
                      objectName="Caption")
        lv.addWidget(hint)
        h.addWidget(left, 3)

        # 오른쪽: 미리보기 + 옵션 (스크롤)
        right = QWidget(objectName="Page")
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 6, 0)
        rv.setSpacing(10)
        self.preview = QLabel("미리보기", objectName="Preview")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(230)
        rv.addWidget(self.preview)
        self.info = QLabel("", objectName="Muted")
        self.info.setWordWrap(True)
        rv.addWidget(self.info)

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
        self.lb_q.setFixedWidth(28)
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
        rv.addWidget(g1)

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
        wh = QHBoxLayout()
        wh.addWidget(self.sp_w)
        wh.addWidget(QLabel("×"))
        wh.addWidget(self.sp_h)
        f2.addRow("가로×세로", wh)
        f2.addRow(self.cb_keep)
        f2.addRow(self.cb_noup)
        rv.addWidget(g2)

        g3 = QGroupBox("회전 / 반전")
        h3 = QHBoxLayout(g3)
        self.cb_rot = QComboBox()
        self.cb_rot.addItems(["회전 없음", "90° 우", "90° 좌", "180°"])
        self.cb_fx = QCheckBox("좌우반전")
        self.cb_fy = QCheckBox("상하반전")
        h3.addWidget(self.cb_rot)
        h3.addWidget(self.cb_fx)
        h3.addWidget(self.cb_fy)
        h3.addStretch()
        rv.addWidget(g3)

        g4 = QGroupBox("저장")
        f4 = QFormLayout(g4)
        oh, self.ed_out = dir_row(self, "비우면 원본 폴더\\변환 폴더에 저장")
        f4.addRow("출력 폴더", oh)
        self.ed_suffix = QLineEdit("")
        self.ed_suffix.setPlaceholderText("예: _변환")
        f4.addRow("파일명 뒤에", self.ed_suffix)
        self.cb_only_sel = QCheckBox("선택한 파일만")
        f4.addRow(self.cb_only_sel)
        rv.addWidget(g4)
        rv.addStretch()

        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sc.setWidget(right)
        col = QWidget(objectName="Page")
        cv = QVBoxLayout(col)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(10)
        cv.addWidget(sc, 1)
        cv.addWidget(run_button("변환 실행", self.run))
        col.setMinimumWidth(380)
        col.setMaximumWidth(460)
        h.addWidget(col, 2)
        self._resize_ui()

    def _on_count(self, n):
        self.lb_count.setText(f"사진 {n}개")
        if self.win.stack.currentWidget() is self:
            self.win.set_doc_info(self.status_text())

    def _resize_ui(self):
        i = self.cb_resize.currentIndex()
        self.sp_pct.setEnabled(i == 1)
        self.sp_w.setEnabled(i in (2, 4))
        self.sp_h.setEnabled(i in (3, 4))
        self.cb_keep.setEnabled(i == 4)
        self.cb_noup.setEnabled(i in (2, 3, 4))

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
            self.preview.clear()
            self.preview.setText("미리보기")
            self.info.setText("")
            return
        p = cur.data(Qt.UserRole)
        try:
            im = open_image(p)
            w, h = im.size
            fmt = im.format or os.path.splitext(p)[1][1:].upper()
            self.preview.setPixmap(pil_thumb_pixmap(im, 360))
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
        self.win.toast(f"사진 {res.ok}건 변환 완료", error=bool(res.errors) and not res.ok)
        QMessageBox.information(self, APP_NAME, msg)
