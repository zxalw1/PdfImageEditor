# -*- coding: utf-8 -*-
"""자동 업데이트 UI: 시작 시 조용히 확인 → 새 버전이면 안내 → 받기(진행률·취소) → sha256 확인 → 설치 실행 후 종료"""
import os
import sys
import traceback

from PySide6.QtCore import Qt, QObject, QThread, Signal, QTimer
from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QMessageBox,
)

from app import APP_NAME, VERSION, UPDATE_URL
from app.core import updater
from app.core.utils import LOG_DIR
from app.ui import theme
from app.ui.workers import run_task


def app_dir():
    return os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else None


def update_url():
    return updater.configured_url(UPDATE_URL, app_dir())


class _CheckThread(QThread):
    done = Signal(object, object)       # (UpdateInfo 또는 None, 오류 또는 None)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            self.done.emit(updater.check(self.url, VERSION), None)
        except Exception as ex:          # noqa: BLE001
            self.done.emit(None, ex)


class UpdateDialog(QDialog):
    LATER, UPDATE, SKIP, QUIT = range(4)

    def __init__(self, info, parent=None):
        super().__init__(parent)
        self.choice = self.LATER
        self.setWindowTitle("업데이트")
        self.setMinimumWidth(460)
        v = QVBoxLayout(self)
        v.setSpacing(10)
        v.addWidget(QLabel(f"새 버전 v{info.version} 이 있습니다", objectName="H1"))
        v.addWidget(QLabel(f"현재 버전 v{VERSION}" + (" · 필수 업데이트입니다" if info.mandatory else ""),
                           objectName="Muted"))
        if info.notes.strip():
            notes = QTextBrowser()
            notes.setPlainText(info.notes)
            notes.setMaximumHeight(180)
            v.addWidget(notes)
        v.addWidget(QLabel("업데이트하면 설치 후 프로그램이 다시 실행됩니다. 작업 중인 문서는 먼저 저장하세요.",
                           objectName="Caption"))
        h = QHBoxLayout()
        if not info.mandatory:
            b_skip = QPushButton("이 버전 건너뛰기", objectName="Ghost")
            b_skip.clicked.connect(lambda: self._done(self.SKIP))
            h.addWidget(b_skip)
        h.addStretch()
        b_later = QPushButton("프로그램 종료" if info.mandatory else "나중에")
        b_later.clicked.connect(lambda: self._done(self.QUIT if info.mandatory else self.LATER))
        h.addWidget(b_later)
        b_up = QPushButton("지금 업데이트", objectName="Primary")
        b_up.clicked.connect(lambda: self._done(self.UPDATE))
        b_up.setDefault(True)
        h.addWidget(b_up)
        v.addLayout(h)

    def _done(self, c):
        self.choice = c
        self.accept()


class UpdateManager(QObject):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self._thread = None
        self.dialog_cls = UpdateDialog       # 테스트에서 바꿔 끼울 수 있게

    # ── 확인 ──
    def check_async(self, manual=False):
        url = update_url()
        if not url:
            if manual:
                QMessageBox.information(self.win, APP_NAME,
                                        "업데이트 주소가 설정되지 않았습니다.\n"
                                        f"설치 폴더 또는 {LOG_DIR} 에 {updater.CONFIG_NAME} 파일로 지정할 수 있습니다.")
            return
        if self._thread is not None and self._thread.isRunning():
            return
        self._thread = _CheckThread(url)
        self._thread.done.connect(lambda info, err: self._on_checked(info, err, manual))
        self._thread.start()
        if manual:
            self.win.toast("업데이트 확인 중...")

    def _on_checked(self, info, err, manual):
        if err is not None:
            _log(f"업데이트 확인 실패: {err}")
            if manual:
                QMessageBox.warning(self.win, APP_NAME, str(err))
            return
        if info is None:
            if manual:
                QMessageBox.information(self.win, APP_NAME, f"최신 버전입니다 (v{VERSION})")
            return
        if not manual and not info.mandatory and theme.settings().value("skip_version", "") == info.version:
            return
        self.offer(info)

    # ── 안내 → 받기 → 설치 ──
    def offer(self, info):
        dlg = self.dialog_cls(info, self.win)
        dlg.exec()
        c = dlg.choice
        if c == UpdateDialog.SKIP:
            theme.settings().setValue("skip_version", info.version)
            self.win.toast(f"v{info.version} 업데이트를 건너뜁니다 (메뉴에서 직접 확인 가능)")
        elif c == UpdateDialog.QUIT:
            QApplication.instance().quit()
        elif c == UpdateDialog.UPDATE:
            self.install(info)

    def install(self, info):
        if not self.win.pdf.confirm_discard():
            return False
        try:
            path = run_task(self.win, "새 버전 받는 중...", 100, lambda t: updater.download(info, task=t))
        except updater.UpdateError as ex:
            QMessageBox.warning(self.win, APP_NAME, str(ex))
            return False
        except Exception as ex:          # noqa: BLE001
            _log(traceback.format_exc())
            QMessageBox.warning(self.win, APP_NAME, f"업데이트 실패\n{ex}")
            return False
        theme.settings().setValue("updated_from", VERSION)
        try:
            updater.launch_installer(path, verify_sha=info.sha256)
        except Exception as ex:          # noqa: BLE001
            QMessageBox.warning(self.win, APP_NAME, f"설치 프로그램을 실행하지 못했습니다\n{ex}")
            return False
        self.win.pdf.modified = False    # 이미 저장 여부를 물었음
        QTimer.singleShot(0, QApplication.instance().quit)
        return True


def show_updated_toast(win):
    """업데이트 후 첫 실행이면 알림"""
    s = theme.settings()
    prev = s.value("updated_from", "")
    if prev and prev != VERSION:
        win.toast(f"v{prev} → v{VERSION} 업데이트 완료", ms=6000)
    if prev:
        s.remove("updated_from")


def _log(msg):
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(os.path.join(LOG_DIR, "error.log"), "a", encoding="utf-8") as f:
            f.write(msg.rstrip() + "\n")
    except OSError:
        pass
