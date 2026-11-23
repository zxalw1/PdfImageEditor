# -*- coding: utf-8 -*-
"""앱 테마: 색 토큰, 스타일시트, 단색 SVG 아이콘 착색, 라이트/다크 전환

사용법
    apply_theme(app)                  # 저장된 설정(라이트/다크)으로 적용
    apply_theme(app, dark=True)       # 전환 (설정에 저장, 등록된 아이콘 재착색)
    bind_icon(button, "save")         # 테마 색 아이콘 지정 + 테마 전환 시 자동 재착색
    C['accent']                       # 현재 테마 색
"""
import os
import tempfile
from functools import lru_cache

import shiboken6
from PySide6.QtCore import Qt, QByteArray, QRectF, QSettings
from PySide6.QtGui import QIcon, QPixmap, QPainter, QFontDatabase, QPalette, QColor
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QLabel

from app.core.utils import resource_path

LIGHT = dict(
    bg="#F7F8FA", surface="#FFFFFF", hover="#F1F3F6", border="#E5E7EB", border_strong="#CBD2DC",
    text="#111827", text2="#6B7280", text3="#A3AAB5",
    accent="#2563EB", accent_hover="#1D4ED8", accent_soft="#EAF1FF", on_accent="#FFFFFF",
    viewer="#ECEEF2", success="#16A34A", danger="#DC2626",
)
DARK = dict(
    bg="#0F1115", surface="#171A21", hover="#21252E", border="#272C36", border_strong="#3A414E",
    text="#E6E8EC", text2="#9AA2AF", text3="#5D6573",
    accent="#3B82F6", accent_hover="#60A5FA", accent_soft="#1B2840", on_accent="#FFFFFF",
    viewer="#0B0D11", success="#22C55E", danger="#F87171",
)

C = dict(LIGHT)          # 현재 테마 색 (apply_theme 이 갱신)
_state = {"dark": False}
_bound = []              # [(obj, icon_name, color_key, size)]


def settings():
    return QSettings("CnC", "PdfImageEditor")


def is_dark():
    return _state["dark"]


def ui_font_family():
    fams = set(QFontDatabase.families())
    for f in ("Pretendard", "Pretendard Variable", "Malgun Gothic", "맑은 고딕"):
        if f in fams:
            return f
    return "Malgun Gothic"


# ── QSS용 작은 SVG (체크, 화살표) ──
_QSS_SVG = {
    "check": ('<path d="M5 12.5l4.5 4.5L19 7.5"/>', 3),
    "chev-down": ('<path d="M7 10l5 5 5-5"/>', 2.2),
    "chev-up": ('<path d="M7 14l5-5 5 5"/>', 2.2),
    "dot": ('<circle cx="12" cy="12" r="5.5" fill="currentFill"/>', 0),
}


def _qss_svg(name, color):
    d = os.path.join(tempfile.gettempdir(), "PdfImageEditor_qss")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"{name}_{color.lstrip('#')}.svg")
    if not os.path.exists(p):
        body, sw = _QSS_SVG[name]
        body = body.replace("currentFill", color)
        with open(p, "w", encoding="utf-8") as f:
            f.write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
                    f'stroke="{color}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round">'
                    f'{body}</svg>')
    return p.replace("\\", "/")


def build_qss(c, font):
    chk = _qss_svg("check", c['on_accent'])
    dn = _qss_svg("chev-down", c['text2'])
    up = _qss_svg("chev-up", c['text2'])
    return f"""
* {{ font-family:'{font}'; font-size:10pt; color:{c['text']}; }}
QMainWindow, QWidget#Root, QWidget#Page, QStackedWidget#Pages {{ background:{c['bg']}; }}
QDialog, QMessageBox, QInputDialog, QProgressDialog {{ background:{c['surface']}; }}
QLabel {{ background:transparent; }}
QLabel#Muted {{ color:{c['text2']}; }}
QLabel#H1 {{ font-size:15pt; font-weight:600; }}
QLabel#H2 {{ font-size:11pt; font-weight:600; }}
QLabel#Caption {{ color:{c['text2']}; font-size:9pt; }}
QLabel#Preview {{ background:{c['viewer']}; border:1px solid {c['border']}; border-radius:8px; color:{c['text3']}; }}

QFrame#Card {{ background:{c['surface']}; border:1px solid {c['border']}; border-radius:8px; }}
QFrame#Card[clickable="true"]:hover {{ border-color:{c['accent']}; }}
QFrame#Card[selected="true"] {{ border:1.5px solid {c['accent']}; background:{c['accent_soft']}; }}
QLabel#CardIcon {{ background:{c['accent_soft']}; border-radius:10px; }}
QFrame#Card[selected="true"] QLabel#CardIcon {{ background:{c['surface']}; }}
QFrame#DropZone {{ background:{c['surface']}; border:2px dashed {c['border_strong']}; border-radius:12px; }}
QFrame#DropZone:hover, QFrame#DropZone[drag="true"] {{ border-color:{c['accent']}; background:{c['accent_soft']}; }}
QScrollArea#Viewer {{ background:{c['viewer']}; border:1px solid {c['border']}; border-radius:8px; }}
QScrollArea#Viewer > QWidget > QWidget {{ background:{c['viewer']}; }}
QLabel#PageView {{ background:{c['viewer']}; color:{c['text3']}; }}

QFrame#NavBar {{ background:{c['surface']}; border:none; border-right:1px solid {c['border']}; }}
QToolButton#Nav {{ border:none; border-radius:8px; padding:6px 2px; color:{c['text2']}; font-size:9pt; }}
QToolButton#Nav:hover {{ background:{c['hover']}; }}
QToolButton#Nav:checked {{ background:{c['accent_soft']}; color:{c['accent']}; font-weight:600; }}

QToolBar {{ background:{c['surface']}; border:none; border-bottom:1px solid {c['border']}; padding:4px 8px; spacing:2px; }}
QToolBar::separator {{ width:1px; background:{c['border']}; margin:8px 2px; }}
QToolButton {{ border:none; border-radius:6px; padding:4px 2px; background:transparent; }}
QToolButton:hover {{ background:{c['hover']}; }}
QToolButton:pressed {{ background:{c['border']}; }}
QToolButton:checked {{ background:{c['accent_soft']}; color:{c['accent']}; }}
QToolButton:disabled {{ color:{c['text3']}; }}
QToolButton::menu-indicator {{ image:none; width:0; }}
QToolButton[popupMode="1"] {{ padding-right:16px; }}
QToolButton::menu-button {{ border:none; background:transparent; width:14px; border-top-right-radius:6px; border-bottom-right-radius:6px; }}
QToolButton::menu-button:hover {{ background:{c['border']}; }}
QToolButton::menu-arrow {{ image:url({dn}); width:12px; height:12px; }}
QFrame#ViewBox {{ background:{c['surface']}; border:1px solid {c['border']}; border-radius:6px; }}
QFrame#ViewSep {{ background:{c['border']}; border:none; }}
QToolButton#ViewBtn {{ border-radius:4px; padding:0; margin:0 1px; }}
QToolButton#ViewBtn:checked {{ background:{c['accent_soft']}; }}
QComboBox#ZoomCombo {{ border:none; background:transparent; padding:0 2px 0 6px; min-height:22px; }}
QComboBox#ZoomCombo:hover {{ background:{c['hover']}; border-radius:4px; }}
QLabel#ToolCaption {{ font-size:10pt; background:transparent; }}
QLabel#ToolCaption:disabled {{ color:{c['text3']}; }}

QPushButton {{ background:{c['surface']}; border:1px solid {c['border']}; border-radius:6px; padding:6px 14px; }}
QPushButton:hover {{ background:{c['hover']}; }}
QPushButton:disabled {{ color:{c['text3']}; }}
QPushButton#Primary {{ background:{c['accent']}; color:{c['on_accent']}; border:none; font-weight:600; padding:9px 18px; }}
QPushButton#Primary:hover {{ background:{c['accent_hover']}; }}
QPushButton#Ghost {{ border:none; background:transparent; color:{c['text2']}; padding:5px 8px; }}
QPushButton#Ghost:hover {{ background:{c['hover']}; color:{c['text']}; }}

QLineEdit, QSpinBox, QComboBox {{ background:{c['surface']}; border:1px solid {c['border']}; border-radius:6px;
    padding:4px 8px; min-height:20px; selection-background-color:{c['accent']}; selection-color:{c['on_accent']}; }}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color:{c['accent']}; }}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{ color:{c['text3']}; background:{c['hover']}; }}
QSpinBox {{ padding-right:24px; }}
QSpinBox::up-button, QSpinBox::down-button {{ subcontrol-origin:border; width:22px; border:none; border-left:1px solid {c['border']}; background:transparent; }}
QSpinBox::up-button {{ subcontrol-position:top right; border-top-right-radius:6px; }}
QSpinBox::down-button {{ subcontrol-position:bottom right; border-bottom-right-radius:6px; }}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background:{c['hover']}; }}
QSpinBox::up-arrow {{ image:url({up}); width:14px; height:14px; }}
QSpinBox::down-arrow {{ image:url({dn}); width:14px; height:14px; }}
QComboBox::drop-down {{ border:none; width:24px; }}
QComboBox::down-arrow {{ image:url({dn}); width:14px; height:14px; }}
QComboBox QAbstractItemView {{ background:{c['surface']}; border:1px solid {c['border']}; padding:4px;
    selection-background-color:{c['accent_soft']}; selection-color:{c['text']}; outline:none; }}
QCheckBox, QRadioButton {{ spacing:8px; background:transparent; }}
QCheckBox:disabled, QRadioButton:disabled {{ color:{c['text3']}; }}
QCheckBox::indicator {{ width:16px; height:16px; border:1.5px solid {c['border_strong']}; border-radius:4px; background:{c['surface']}; }}
QCheckBox::indicator:hover {{ border-color:{c['accent']}; }}
QCheckBox::indicator:checked {{ background:{c['accent']}; border-color:{c['accent']}; image:url({chk}); }}
QCheckBox::indicator:disabled {{ background:{c['hover']}; border-color:{c['border']}; }}
QRadioButton::indicator {{ width:16px; height:16px; border:1.5px solid {c['border_strong']}; border-radius:9px; background:{c['surface']}; }}
QRadioButton::indicator:checked {{ border:1.5px solid {c['accent']}; background:{c['surface']}; image:url({_qss_svg("dot", c['accent'])}); }}
QSlider::groove:horizontal {{ height:4px; background:{c['border']}; border-radius:2px; }}
QSlider::sub-page:horizontal {{ background:{c['accent']}; border-radius:2px; }}
QSlider::handle:horizontal {{ width:16px; height:16px; margin:-6px 0; border-radius:8px; background:{c['surface']}; border:1.5px solid {c['accent']}; }}

QListWidget {{ background:{c['surface']}; border:1px solid {c['border']}; border-radius:8px; padding:4px; outline:none; }}
QListWidget::item {{ border-radius:6px; padding:4px; color:{c['text']}; }}
QListWidget::item:hover {{ background:{c['hover']}; }}
QListWidget::item:selected {{ background:{c['accent_soft']}; color:{c['text']}; }}

QGroupBox {{ background:{c['surface']}; border:1px solid {c['border']}; border-radius:8px; margin-top:0; padding:36px 12px 12px 12px; font-weight:600; }}
QGroupBox::indicator {{ width:16px; height:16px; border:1.5px solid {c['border_strong']}; border-radius:4px; background:{c['surface']}; }}
QGroupBox::indicator:checked {{ background:{c['accent']}; border-color:{c['accent']}; image:url({chk}); }}
QGroupBox[checkable="true"]:!checked {{ color:{c['text3']}; }}
QGroupBox::title {{ subcontrol-origin:padding; subcontrol-position:top left; left:14px; top:12px; padding:0; color:{c['text']}; font-size:10.5pt; background:transparent; }}

QStatusBar {{ background:{c['surface']}; border-top:1px solid {c['border']}; color:{c['text2']}; min-height:26px; }}
QStatusBar::item {{ border:none; }}
QStatusBar QLabel {{ color:{c['text2']}; padding:0 6px; }}
QStatusBar QLabel#Toast {{ background:{c['success']}; color:white; border-radius:10px; padding:2px 12px; font-size:9pt; }}
QStatusBar QLabel#ToastError {{ background:{c['danger']}; color:white; border-radius:10px; padding:2px 12px; font-size:9pt; }}

QMenu {{ background:{c['surface']}; border:1px solid {c['border']}; border-radius:8px; padding:4px; }}
QMenu::item {{ padding:6px 24px 6px 10px; border-radius:6px; }}
QMenu::item:selected {{ background:{c['hover']}; }}
QMenu::item:disabled {{ color:{c['text3']}; }}
QMenu::separator {{ height:1px; background:{c['border']}; margin:4px 6px; }}
QMenu::icon {{ padding-left:6px; }}

QScrollArea {{ border:none; background:transparent; }}
QScrollBar:vertical {{ background:transparent; width:10px; margin:2px; }}
QScrollBar:horizontal {{ background:transparent; height:10px; margin:2px; }}
QScrollBar::handle {{ background:{c['border_strong']}; border-radius:3px; min-height:30px; min-width:30px; }}
QScrollBar::handle:hover {{ background:{c['text3']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width:0; height:0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background:transparent; }}
QSplitter::handle {{ background:transparent; }}
QProgressBar {{ border:none; background:{c['hover']}; border-radius:4px; text-align:center; }}
QProgressBar::chunk {{ background:{c['accent']}; border-radius:4px; }}
QToolTip {{ background:{c['text']}; color:{c['surface']}; border:none; padding:4px 8px; }}
"""


def build_palette(c):
    p = QPalette()
    for role, key in [(QPalette.Window, 'bg'), (QPalette.Base, 'surface'), (QPalette.AlternateBase, 'hover'),
                      (QPalette.Button, 'surface'), (QPalette.Text, 'text'), (QPalette.WindowText, 'text'),
                      (QPalette.ButtonText, 'text'), (QPalette.Highlight, 'accent'),
                      (QPalette.HighlightedText, 'on_accent'), (QPalette.ToolTipBase, 'text'),
                      (QPalette.ToolTipText, 'surface'), (QPalette.PlaceholderText, 'text3'),
                      (QPalette.Mid, 'border'), (QPalette.Dark, 'border_strong'), (QPalette.Light, 'surface')]:
        p.setColor(role, QColor(c[key]))
    p.setColor(QPalette.Disabled, QPalette.Text, QColor(c['text3']))
    p.setColor(QPalette.Disabled, QPalette.WindowText, QColor(c['text3']))
    p.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(c['text3']))
    return p


_translators = []


def install_korean(app):
    """Qt 기본 버튼·대화상자(저장/취소/예/아니요 등)를 한국어로. 성공 여부 반환"""
    import sys
    from PySide6.QtCore import QTranslator, QLibraryInfo
    import PySide6
    dirs = [os.path.join(os.path.dirname(PySide6.__file__), "translations"),
            QLibraryInfo.path(QLibraryInfo.TranslationsPath)]
    if getattr(sys, "_MEIPASS", None):
        dirs.insert(0, os.path.join(sys._MEIPASS, "PySide6", "translations"))
    for d in dirs:
        t = QTranslator(app)
        if t.load("qtbase_ko", d):
            app.installTranslator(t)
            _translators.append(t)
            return True
    return False


def apply_theme(app, dark=None):
    """dark=None 이면 저장된 설정 사용"""
    if dark is None:
        dark = settings().value("dark", False, type=bool)
    _state["dark"] = bool(dark)
    C.clear()
    C.update(DARK if dark else LIGHT)
    settings().setValue("dark", bool(dark))
    app.setStyle("Fusion")
    app.setPalette(build_palette(C))
    app.setStyleSheet(build_qss(C, ui_font_family()))
    refresh_icons()


# ── 아이콘 ──
ICON_DIR = resource_path("app", "assets", "icons")


@lru_cache(maxsize=None)
def _svg_text(name):
    with open(os.path.join(ICON_DIR, name + ".svg"), encoding="utf-8") as f:
        return f.read()


def svg_pixmap(name, color, size=24, dpr=2.0):
    data = _svg_text(name).replace("currentColor", color)
    r = QSvgRenderer(QByteArray(data.encode("utf-8")))
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    r.render(p, QRectF(0, 0, pm.width(), pm.height()))
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def make_icon(name, color=None, size=24, checked_color=None, disabled_color=None):
    """색을 입힌 QIcon. 체크(On)·비활성 상태 색 포함"""
    color = color or C['text']
    ic = QIcon()
    ic.addPixmap(svg_pixmap(name, color, size), QIcon.Normal, QIcon.Off)
    ic.addPixmap(svg_pixmap(name, checked_color or C['accent'], size), QIcon.Normal, QIcon.On)
    ic.addPixmap(svg_pixmap(name, disabled_color or C['text3'], size), QIcon.Disabled, QIcon.Off)
    return ic


def _apply_icon(obj, name, key, size):
    if isinstance(obj, QLabel):
        obj.setPixmap(svg_pixmap(name, C[key], size))
    else:
        obj.setIcon(make_icon(name, C[key], size))


def bind_icon(obj, name, key='text', size=24):
    """obj(QAction/버튼/QLabel)에 테마 아이콘을 지정하고 테마 전환 시 다시 칠한다"""
    _apply_icon(obj, name, key, size)
    _bound.append((obj, name, key, size))
    return obj


def refresh_icons():
    alive = []
    for obj, name, key, size in _bound:
        if shiboken6.isValid(obj):
            _apply_icon(obj, name, key, size)
            alive.append((obj, name, key, size))
    _bound[:] = alive
