# -*- coding: utf-8 -*-
"""메인 창: 좌측 세로 내비게이션 + 페이지 스택 + 하단 상태바(문서 정보·토스트)"""
import os

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QHBoxLayout, QVBoxLayout, QToolButton, QLabel,
    QStackedWidget, QStatusBar, QButtonGroup, QMessageBox,
)

from app import APP_NAME, VERSION
from app.core.utils import resource_path, LOG_DIR
from app.ui import theme
from app.ui.theme import bind_icon
from app.ui.pdf_tab import PdfTab
from app.ui.image_tab import ImageTab
from app.ui.convert_tab import ConvertTab

NAV = [("pdf", "nav-pdf", "PDF 편집"), ("img", "nav-image", "사진 편집"), ("conv", "nav-convert", "변환")]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{VERSION}")
        self.resize(1320, 860)
        self.setMinimumSize(1000, 640)

        root = QWidget(objectName="Root")
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(self._build_nav())
        self.stack = QStackedWidget(objectName="Pages")
        h.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self._build_status()

        self.pdf = PdfTab(self)
        self.img = ImageTab(self)
        self.conv = ConvertTab(self)
        self.pages = {"pdf": self.pdf, "img": self.img, "conv": self.conv}
        for w in self.pages.values():
            self.stack.addWidget(w)
        self.go("pdf")
        from app.ui.updates import UpdateManager
        self.updates = UpdateManager(self)

    def about(self):
        from app.ui.updates import update_url
        u = update_url() or "설정 안 됨"
        QMessageBox.about(self, APP_NAME,
                          f"<b>{APP_NAME}</b><br>버전 v{VERSION}<br><br>"
                          f"업데이트 주소: {u}<br>오류 기록: {LOG_DIR}")

    # ── 내비게이션 ──
    def _build_nav(self):
        bar = QFrame(objectName="NavBar")
        bar.setFixedWidth(84)
        v = QVBoxLayout(bar)
        v.setContentsMargins(8, 12, 8, 12)
        v.setSpacing(4)
        logo = QLabel()
        logo.setAlignment(Qt.AlignCenter)
        ico = resource_path("app", "assets", "app.ico")
        if os.path.exists(ico):
            logo.setPixmap(QIcon(ico).pixmap(36, 36))
        logo.setToolTip(f"{APP_NAME} v{VERSION}")
        v.addWidget(logo)
        v.addSpacing(14)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_btns = {}
        for key, ic, text in NAV:
            b = QToolButton(objectName="Nav")
            bind_icon(b, ic, 'text2', 24)
            b.setIconSize(QSize(24, 24))
            b.setText(text)
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setCheckable(True)
            b.setFixedSize(68, 62)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.go(k))
            self.nav_group.addButton(b)
            self.nav_btns[key] = b
            v.addWidget(b, 0, Qt.AlignHCenter)
        v.addStretch()
        from PySide6.QtWidgets import QMenu
        self.btn_info = QToolButton(objectName="Nav")
        bind_icon(self.btn_info, "info", 'text2', 20)
        self.btn_info.setIconSize(QSize(20, 20))
        self.btn_info.setText("정보")
        self.btn_info.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.btn_info.setFixedSize(68, 52)
        self.btn_info.setCursor(Qt.PointingHandCursor)
        self.btn_info.setPopupMode(QToolButton.InstantPopup)
        m = QMenu(self)
        m.addAction("업데이트 확인", lambda: self.updates.check_async(manual=True))
        m.addAction("프로그램 정보", self.about)
        m.addAction("오류 기록 폴더 열기", lambda: os.startfile(LOG_DIR) if os.path.isdir(LOG_DIR) else None)
        self.btn_info.setMenu(m)
        v.addWidget(self.btn_info, 0, Qt.AlignHCenter)
        self.btn_theme = QToolButton(objectName="Nav")
        self.btn_theme.setIconSize(QSize(20, 20))
        self.btn_theme.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.btn_theme.setFixedSize(68, 52)
        self.btn_theme.setCursor(Qt.PointingHandCursor)
        self.btn_theme.clicked.connect(self.toggle_theme)
        v.addWidget(self.btn_theme, 0, Qt.AlignHCenter)
        self._update_theme_btn()
        return bar

    def go(self, key):
        self.stack.setCurrentWidget(self.pages[key])
        self.nav_btns[key].setChecked(True)
        if key == "pdf":
            self.pdf._update_state()
        else:
            self.set_doc_info(self.pages[key].status_text() if hasattr(self.pages[key], "status_text") else "")

    def current_key(self):
        w = self.stack.currentWidget()
        return next(k for k, v in self.pages.items() if v is w)

    # ── 테마 ──
    def _update_theme_btn(self):
        dark = theme.is_dark()
        self.btn_theme.setText("라이트" if dark else "다크")
        self.btn_theme.setToolTip("라이트 모드로 전환" if dark else "다크 모드로 전환")
        self.btn_theme.setIcon(theme.make_icon("sun" if dark else "moon", theme.C['text2'], 20))

    def toggle_theme(self):
        theme.apply_theme(QApplication.instance(), not theme.is_dark())
        self._update_theme_btn()
        self.pdf.on_theme_changed()

    # ── 상태바 ──
    def _build_status(self):
        sb = QStatusBar()
        sb.setSizeGripEnabled(False)
        self.lbl_doc = QLabel("")
        sb.addWidget(self.lbl_doc, 1)
        self.lbl_toast = QLabel("", objectName="Toast")
        self.lbl_toast.hide()
        sb.addPermanentWidget(self.lbl_toast)
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self.lbl_toast.hide)
        self.setStatusBar(sb)

    def set_status(self, text):
        self.set_doc_info(text)

    def set_doc_info(self, text):
        self.lbl_doc.setText(text)

    def toast(self, text, error=False, ms=4000):
        self.lbl_toast.setObjectName("ToastError" if error else "Toast")
        self.lbl_toast.style().unpolish(self.lbl_toast)
        self.lbl_toast.style().polish(self.lbl_toast)
        self.lbl_toast.setText(("✕  " if error else "✓  ") + text)
        self.lbl_toast.setToolTip(text)
        self.lbl_toast.show()
        self._toast_timer.start(ms)

    def closeEvent(self, e):
        if self.pdf.confirm_discard():
            e.accept()
        else:
            e.ignore()
