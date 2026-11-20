# -*- coding: utf-8 -*-
"""앱 스타일시트"""

STYLE = """
QWidget{font-family:'Malgun Gothic';font-size:9pt;}
QToolBar{spacing:2px;border:none;background:#f4f4f4;}
QToolButton{padding:4px 7px;border-radius:3px;}
QToolButton:hover{background:#dde8f5;}
QToolButton:checked{background:#2d6cdf;color:white;}
QGroupBox{font-weight:bold;border:1px solid #ccc;border-radius:4px;margin-top:8px;padding-top:6px;}
QGroupBox::title{subcontrol-origin:margin;left:8px;padding:0 3px;}
QPushButton{padding:4px 10px;}
QTabBar::tab{padding:7px 14px;}
QTabBar::tab:selected{font-weight:bold;}
"""


def apply_theme(app):
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
