# -*- coding: utf-8 -*-
"""MS Office / 한글 COM, LibreOffice 변환 엔진 (Qt 의존 없음)

COM 객체는 생성한 스레드에서만 사용해야 하므로 OfficeConverter는
변환을 실행하는 스레드(워커) 안에서 만들어야 한다.
"""
import os
import shutil
import subprocess
import sys
import tempfile

EXCEL_EXT = {'.xlsx', '.xls', '.xlsm', '.csv', '.ods'}
WORD_EXT = {'.docx', '.doc', '.rtf', '.txt', '.odt'}
PPT_EXT = {'.pptx', '.ppt', '.odp'}
HWP_EXT = {'.hwp', '.hwpx'}
OFFICE_EXT = EXCEL_EXT | WORD_EXT | PPT_EXT | HWP_EXT
OFFICE_FILTER = "문서 (" + " ".join("*" + e for e in sorted(OFFICE_EXT)) + ")"
NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0


def com_available(progid):
    if sys.platform != 'win32':
        return False
    try:
        import winreg
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, progid))
        return True
    except OSError:
        return False


def find_soffice():
    p = shutil.which('soffice')
    if p:
        return p
    for base in (os.environ.get('ProgramFiles', r'C:\Program Files'),
                 os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')):
        c = os.path.join(base, 'LibreOffice', 'program', 'soffice.exe')
        if os.path.exists(c):
            return c
    return None


def detect_engines():
    return {
        'excel': com_available('Excel.Application'),
        'word': com_available('Word.Application'),
        'ppt': com_available('PowerPoint.Application'),
        'hwp': com_available('HWPFrame.HwpObject'),
        'soffice': find_soffice(),
    }


class OfficeConverter:
    """MS Office / 한글 COM 우선, 없으면 LibreOffice 사용"""

    def __init__(self, engines, fit_width=False):
        self.e = engines
        self.fit = fit_width
        self.apps = {}
        self._com = False
        if sys.platform == 'win32':
            try:
                import pythoncom
                pythoncom.CoInitialize()
                self._com = True
            except Exception:
                pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def _app(self, progid):
        if progid in self.apps:
            return self.apps[progid]
        import win32com.client
        app = win32com.client.DispatchEx(progid)
        if progid == 'Excel.Application':
            app.Visible = False
            app.DisplayAlerts = False
            app.ScreenUpdating = False
        elif progid == 'Word.Application':
            app.Visible = False
            app.DisplayAlerts = 0
        elif progid == 'HWPFrame.HwpObject':
            try:
                app.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
            except Exception:
                pass
            try:
                app.XHwpWindows.Item(0).Visible = False
            except Exception:
                pass
        self.apps[progid] = app
        return app

    def close(self):
        for progid, app in self.apps.items():
            try:
                if progid == 'HWPFrame.HwpObject':
                    app.Clear(1)
                app.Quit()
            except Exception:
                pass
        self.apps.clear()
        if self._com:
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except Exception:
                pass
            self._com = False

    def convert(self, src, dst):
        src, dst = os.path.abspath(src), os.path.abspath(dst)
        ext = os.path.splitext(src)[1].lower()
        if ext in HWP_EXT:
            if not self.e['hwp']:
                raise RuntimeError("한글(HWP) 프로그램이 설치된 PC에서만 변환 가능합니다.")
            return self._hwp(src, dst)
        kind = 'excel' if ext in EXCEL_EXT else 'word' if ext in WORD_EXT else 'ppt'
        err = None
        if self.e[kind]:
            try:
                return getattr(self, '_' + kind)(src, dst)
            except Exception as ex:
                err = ex
        if self.e['soffice']:
            return self._soffice(src, dst)
        if err:
            raise err
        raise RuntimeError("MS Office 또는 LibreOffice가 설치되어 있어야 합니다.")

    def _excel(self, src, dst):
        app = self._app('Excel.Application')
        wb = app.Workbooks.Open(src, 0, True)
        try:
            if self.fit:
                for ws in wb.Worksheets:
                    try:
                        ps = ws.PageSetup
                        ps.Zoom = False
                        ps.FitToPagesWide = 1
                        ps.FitToPagesTall = False
                    except Exception:
                        pass
            wb.ExportAsFixedFormat(0, dst)
        finally:
            wb.Close(False)

    def _word(self, src, dst):
        app = self._app('Word.Application')
        doc = app.Documents.Open(src, False, True)
        try:
            doc.ExportAsFixedFormat(dst, 17)
        finally:
            doc.Close(0)

    def _ppt(self, src, dst):
        app = self._app('PowerPoint.Application')
        pres = app.Presentations.Open(src, True, False, False)
        try:
            pres.SaveAs(dst, 32)
        finally:
            pres.Close()

    def _hwp(self, src, dst):
        hwp = self._app('HWPFrame.HwpObject')
        if not hwp.Open(src, "", "forceopen:true"):
            raise RuntimeError("한글 파일을 열 수 없습니다.")
        try:
            hwp.SaveAs(dst, "PDF", "")
        finally:
            hwp.Clear(1)
        if not os.path.exists(dst):
            raise RuntimeError("한글 PDF 저장 실패")

    def _soffice(self, src, dst):
        tmp = tempfile.mkdtemp()
        try:
            subprocess.run([self.e['soffice'], '--headless', '--convert-to', 'pdf', '--outdir', tmp, src],
                           timeout=300, capture_output=True, creationflags=NO_WINDOW)
            out = os.path.join(tmp, os.path.splitext(os.path.basename(src))[0] + '.pdf')
            if not os.path.exists(out):
                raise RuntimeError("LibreOffice 변환 실패")
            shutil.move(out, dst)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
