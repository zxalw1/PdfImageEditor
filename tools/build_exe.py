# -*- coding: utf-8 -*-
"""EXE 빌드 (build.bat · GitHub Actions 공용)
1) PyInstaller(onedir, windowed)  2) 안 쓰는 Qt·코덱 파일 제거(용량)  3) exe 자가진단(--selftest)
실행: python tools\\build_exe.py [--no-selftest]
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = "PdfImageEditor"
DIST = os.path.join(ROOT, "dist", NAME)
INTERNAL = os.path.join(DIST, "_internal")

EXCLUDE_MODULES = [
    # 쓰지 않는 Qt 모듈
    "PySide6.QtNetwork", "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtQuickWidgets", "PySide6.QtPdf",
    "PySide6.QtPdfWidgets", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtTest",
    "PySide6.QtSql", "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtBluetooth",
    "PySide6.QtPositioning", "PySide6.QtSerialPort", "PySide6.QtDesigner", "PySide6.QtHelp",
    # 쓰지 않는 파이썬 패키지 (v1.9.0 에서 PDF→Word(pdf2docx) 제거)
    "pdf2docx", "cv2", "numpy", "docx", "lxml", "fire", "tkinter", "pytest", "_pytest", "IPython",
]

# 빌드 후 지울 파일 (_internal 기준, glob) — 자가진단으로 영향 없음 확인
REMOVE_AFTER = [
    "PySide6/opengl32sw.dll",                   # 소프트웨어 OpenGL (20MB, 안 씀)
    "PySide6/Qt6Quick*.dll", "PySide6/Qt6Qml*.dll", "PySide6/Qt6VirtualKeyboard*.dll",
    "PySide6/Qt6Pdf*.dll", "PySide6/Qt6OpenGL*.dll", "PySide6/Qt6Network.dll",
    "PySide6/plugins/platforminputcontexts", "PySide6/plugins/imageformats/qpdf.dll",
    "PySide6/plugins/generic", "PySide6/plugins/networkinformation", "PySide6/plugins/tls",
    "PySide6/translations",
    # ※ libx265*.dll 은 지우면 안 됨: pillow_heif 가 직접 불러와 HEIC '읽기'까지 실패 (자가진단으로 확인)
]


def size_mb(path):
    total = 0
    for dp, _dn, fn in os.walk(path):
        for f in fn:
            total += os.path.getsize(os.path.join(dp, f))
    return total / 1024 / 1024


def pyinstaller():
    import PyInstaller.__main__
    os.chdir(ROOT)
    args = ["--noconfirm", "--clean", "--windowed", "--name", NAME,
            "--icon", r"app\assets\app.ico",
            "--add-data", r"app\assets;app\assets",
            "--version-file", "version_info.txt",
            "--hidden-import", "win32timezone", "--hidden-import", "fontTools.subset"]
    for m in EXCLUDE_MODULES:
        args += ["--exclude-module", m]
    args.append("main.py")
    PyInstaller.__main__.run(args)
    spec = os.path.join(ROOT, NAME + ".spec")
    if os.path.exists(spec):
        os.remove(spec)


def trim():
    before = size_mb(DIST)
    for pat in REMOVE_AFTER:
        for p in glob.glob(os.path.join(INTERNAL, pat)):
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            else:
                os.remove(p)
    print(f"[trim] {before:.0f}MB → {size_mb(DIST):.0f}MB")


def selftest():
    exe = os.path.join(DIST, NAME + ".exe")
    out = os.path.join(tempfile.gettempdir(), "pie_selftest.json")
    if os.path.exists(out):
        os.remove(out)
    r = subprocess.run([exe, "--selftest", out], timeout=600)
    if not os.path.exists(out):
        print("[selftest] 결과 파일 없음 (exe 실행 실패)", file=sys.stderr)
        return False
    with open(out, encoding="utf-8") as f:
        res = json.load(f)
    for it in res["results"]:
        print(f"[selftest] {'PASS' if it['ok'] else 'FAIL'} {it['name']}  {it['detail'].splitlines()[-1] if it['detail'] else ''}")
    return r.returncode == 0 and res["ok"]


def main():
    pyinstaller()
    shutil.rmtree(os.path.join(ROOT, "build"), ignore_errors=True)   # 중간 산출물(실행 불가) 혼동 방지
    trim()
    if "--no-selftest" not in sys.argv and not selftest():
        print("자가진단 실패 — 설치파일을 만들지 않습니다", file=sys.stderr)
        sys.exit(1)
    print(f"[done] {os.path.join(DIST, NAME + '.exe')}  ({size_mb(DIST):.0f}MB)")


if __name__ == "__main__":
    main()
