# -*- coding: utf-8 -*-
"""대화상자"""
import os

from PySide6.QtWidgets import (
    QDialog, QFormLayout, QHBoxLayout, QRadioButton, QButtonGroup, QSpinBox, QLineEdit,
    QLabel, QCheckBox, QDialogButtonBox, QInputDialog,
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
