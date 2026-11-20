# -*- coding: utf-8 -*-
"""메인 창"""
from PySide6.QtWidgets import QMainWindow, QTabWidget, QStatusBar, QLabel

from app import APP_NAME, VERSION
from app.ui.pdf_tab import PdfTab
from app.ui.image_tab import ImageTab
from app.ui.convert_tab import ConvertTab


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
