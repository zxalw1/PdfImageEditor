# -*- coding: utf-8 -*-
"""무거운 작업을 QThread에서 실행 + 진행률/취소 대화상자"""
from PySide6.QtCore import Qt, QThread, Signal, QEventLoop
from PySide6.QtWidgets import QApplication, QProgressDialog

from app import APP_NAME


class TaskWorker(QThread):
    """core 함수에 task 인자로 전달됨 (report / cancelled 인터페이스)"""
    progressed = Signal(int, object)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.result = None
        self.error = None
        self._cancel = False

    # core 쪽에서 호출 (워커 스레드)
    def report(self, value, label=None):
        self.progressed.emit(value, label)

    def cancelled(self):
        return self._cancel

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            self.result = self.fn(self)
        except BaseException as ex:  # noqa: BLE001 - UI 스레드에서 다시 발생시킴
            self.error = ex


def run_task(parent, title, total, fn, busy_cursor=False):
    """fn(task)를 백그라운드 스레드에서 실행하고 끝날 때까지 이벤트 루프를 돌린다.
    UI는 멈추지 않으며, 진행률 대화상자(창 모달)에서 취소 가능. fn의 반환값을 돌려준다."""
    dlg = QProgressDialog(title, "취소", 0, max(0, total), parent)
    dlg.setWindowTitle(APP_NAME)
    dlg.setWindowModality(Qt.WindowModal)
    dlg.setMinimumDuration(300)
    dlg.setAutoClose(False)
    dlg.setAutoReset(False)
    dlg.setValue(0)

    worker = TaskWorker(fn)
    loop = QEventLoop()

    def on_progress(value, label):
        if label:
            dlg.setLabelText(label)
        if value is not None:
            dlg.setValue(min(value, dlg.maximum()) if dlg.maximum() else 0)

    worker.progressed.connect(on_progress)
    dlg.canceled.connect(worker.cancel)
    worker.finished.connect(loop.quit)
    if busy_cursor:
        QApplication.setOverrideCursor(Qt.WaitCursor)
    try:
        worker.start()
        loop.exec()
        worker.wait()
    finally:
        if busy_cursor:
            QApplication.restoreOverrideCursor()
        dlg.close()
        dlg.deleteLater()
    if worker.error is not None:
        raise worker.error
    return worker.result
