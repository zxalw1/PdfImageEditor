# -*- coding: utf-8 -*-
"""
PDF·이미지 통합 편집기 - 진입점
설치: pip install -r requirements.txt
실행: .venv\\Scripts\\python.exe main.py [파일.pdf]
빌드: build.bat
"""
import os
import sys

from app import APP_NAME, APP_ID
from app.core.utils import LOG_DIR, resource_path


def setup_crash_log():
    import traceback
    import faulthandler
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        log = os.path.join(LOG_DIR, 'error.log')
        fh = open(os.path.join(LOG_DIR, 'crash.log'), 'w', encoding='utf-8')
        faulthandler.enable(fh)
    except Exception:
        log = None

    def hook(et, ev, tb):
        msg = ''.join(traceback.format_exception(et, ev, tb))
        try:
            if log:
                with open(log, 'a', encoding='utf-8') as f:
                    f.write(msg + '\n')
        except Exception:
            pass
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox
            if QApplication.instance():
                QMessageBox.critical(None, APP_NAME, f"오류가 발생했습니다.\n\n{ev}\n\n로그: {log}")
            elif sys.platform == 'win32':
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, msg[-1500:], APP_NAME, 0x10)
        except Exception:
            pass
    sys.excepthook = hook


def main():
    setup_crash_log()
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:
            pass
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication
    from app.ui.theme import apply_theme
    from app.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    apply_theme(app)
    if len(sys.argv) > 2 and sys.argv[1] == "--selftest":      # 빌드 검증용
        from app.selftest import run
        sys.exit(run(sys.argv[2]))
    ico = resource_path("app", "assets", "app.ico")
    if os.path.exists(ico):
        app.setWindowIcon(QIcon(ico))
    w = MainWindow()
    w.show()
    if len(sys.argv) > 1 and sys.argv[1].lower().endswith('.pdf') and os.path.isfile(sys.argv[1]):
        w.pdf.load(sys.argv[1])
    from PySide6.QtCore import QTimer
    from app.ui.updates import show_updated_toast
    show_updated_toast(w)
    QTimer.singleShot(2500, w.updates.check_async)      # 시작 후 조용히 업데이트 확인
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
