# -*- coding: utf-8 -*-
"""core 패키지는 Qt 없이 import 되어야 한다"""
import subprocess
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_core_has_no_qt_dependency():
    code = ("import sys; import app.core.utils, app.core.pdf_ops, app.core.image_ops, "
            "app.core.convert_ops, app.core.office_com; "
            "bad=[m for m in sys.modules if m.startswith('PySide6')]; "
            "assert not bad, bad")
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
