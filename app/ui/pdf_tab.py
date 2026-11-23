# -*- coding: utf-8 -*-
"""PDF 편집 탭"""
import os

from PySide6.QtCore import Qt, QSize, QRectF, QPoint
from PySide6.QtGui import QPixmap, QColor, QAction, QKeySequence, QPainter, QIcon
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QToolBar, QToolButton, QLabel, QSpinBox,
    QComboBox, QScrollArea, QListWidgetItem, QMessageBox, QFileDialog, QInputDialog, QColorDialog,
    QDialog, QMenu, QStackedWidget, QSizePolicy, QFrame,
)

from app import APP_NAME
from app.core import pdf_ops, text_edit, overlay as ov
from app.core.utils import (
    fitz, IMG_EXT, PDF_EXT, PDF_FILTER, IMG_FILTER, collect_files, human, korean_font, with_ext,
)
from app.ui import theme
from app.ui.theme import bind_icon
from app.ui.widgets import (
    PageList, PageView, DropZone, InlineTextEditor, pix_to_qimage, plain_icon, framed, icon_button,
    paint_shape,
)
from app.ui.dialogs import (
    SplitDialog, ReplaceDialog, SignatureDialog, PageDecoDialog, PagePickerWindow, CompressDialog, ask_password,
)
from app.ui.workers import run_task

UNDO_LIMIT = 15
ANNOT_COLORS = [("노랑", (1.0, 0.9, 0.0)), ("초록", (0.3, 0.85, 0.35)), ("분홍", (1.0, 0.45, 0.7)),
                ("하늘", (0.35, 0.75, 1.0)), ("빨강", (0.86, 0.15, 0.15)), ("파랑", (0.15, 0.35, 0.9)),
                ("검정", (0.1, 0.1, 0.1))]
FIT = "폭 맞춤"
ZOOMS = [FIT, "25%", "50%", "75%", "100%", "125%", "150%", "200%", "300%", "400%"]


class PdfTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.setObjectName("Page")
        self.win = win
        self.doc = None
        self.path = None
        self.modified = False
        self.undo_stack = []
        self.zoom = 1.0
        self.color = (0, 0, 0)
        self.font = korean_font()
        self.layer = ov.ObjectLayer()   # 삽입 이미지·서명·도장 (저장 시 PDF 에 합침)
        self.sel_obj = None
        self._obj_pix = {}              # 객체 id → QPixmap
        self._pending = None            # 배치 대기 중인 (data, px_size, kind)
        self._build()
        self._update_state()

    # ── UI ──
    def _act(self, icon, text, slot, sc=None, checkable=False, tip=None, toolbar=True):
        a = QAction(text, self)
        bind_icon(a, icon, 'text', 20)
        a.setCheckable(checkable)
        if sc:
            a.setShortcut(QKeySequence(sc))
        a.setToolTip(f"{tip or text}" + (f"  ({sc})" if sc else ""))
        a.triggered.connect(slot)
        if toolbar:
            self.tb.addAction(a)
        else:
            self.addAction(a)   # 메뉴에만 있는 동작도 단축키가 먹도록
        return a

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.tb = tb = QToolBar()
        tb.setIconSize(QSize(20, 20))
        tb.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        tb.setMovable(False)
        v.addWidget(tb)

        # 파일
        self.a_open = self._act("open", "열기", self.open_pdf, "Ctrl+O", tip="PDF 열기")
        self.a_merge = self._act("merge", "추가", lambda: self.merge_files(), tip="PDF/이미지 추가(병합)")
        self.a_save = self._act("save", "저장", self.save, "Ctrl+S")
        tb.addSeparator()
        self.a_undo = self._act("undo", "실행취소", self.undo, "Ctrl+Z")
        tb.addSeparator()
        # 페이지
        self.a_rl = self._act("rotate-left", "왼쪽", lambda: self.rotate(-90), "Ctrl+L", tip="왼쪽으로 회전")
        self.a_rr = self._act("rotate-right", "오른쪽", lambda: self.rotate(90), "Ctrl+R", tip="오른쪽으로 회전")
        self.a_del = self._act("trash", "삭제", self.delete_pages, "Delete", tip="페이지 삭제")
        self.a_up = self._act("arrow-up", "위로", lambda: self.move(-1), tip="페이지 위로")
        self.a_dn = self._act("arrow-down", "아래로", lambda: self.move(1), tip="페이지 아래로")
        tb.addSeparator()
        # 편집
        self.a_text = self._act("text-add", "텍스트", lambda c: self.set_mode('text' if c else None),
                                checkable=True, tip="텍스트 추가 (페이지를 클릭)")
        # 글자 수정 (기존 텍스트 직접 수정) + 단위 선택 메뉴
        self.a_edit = QAction("글자 수정", self)
        bind_icon(self.a_edit, "text-edit", 'text', 20)
        self.a_edit.setCheckable(True)
        self.a_edit.setShortcut(QKeySequence("Ctrl+E"))
        self.a_edit.setToolTip("기존 글자 수정 (Ctrl+E) · 글자를 클릭하면 그 자리에서 고칩니다")
        self.a_edit.triggered.connect(lambda c: self.set_mode('edit' if c else None))
        self.edit_level = text_edit.LINE
        lv_menu = QMenu(self)
        self.a_lv_line = lv_menu.addAction("줄 단위로 선택", lambda: self.set_edit_level(text_edit.LINE))
        self.a_lv_block = lv_menu.addAction("문단 단위로 선택", lambda: self.set_edit_level(text_edit.BLOCK))
        for a in (self.a_lv_line, self.a_lv_block):
            a.setCheckable(True)
        self.a_lv_line.setChecked(True)
        self.btn_edit = QToolButton()
        self.btn_edit.setDefaultAction(self.a_edit)
        self.btn_edit.setMenu(lv_menu)
        self.btn_edit.setPopupMode(QToolButton.MenuButtonPopup)
        self.btn_edit.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.btn_edit.setIconSize(QSize(20, 20))
        tb.addWidget(self.btn_edit)
        # 삽입 (이미지·서명·도장)
        self.ins_menu = QMenu(self)
        self.ins_menu.aboutToShow.connect(self._build_insert_menu)
        self.btn_insert = QToolButton()
        self.btn_insert.setText("삽입")
        self.btn_insert.setToolTip("이미지·서명·도장 넣기 (넣은 뒤 끌어서 이동, 모서리로 크기조절, Delete로 삭제)")
        bind_icon(self.btn_insert, "insert-image", 'text', 20)
        self.btn_insert.setIconSize(QSize(20, 20))
        self.btn_insert.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.btn_insert.setPopupMode(QToolButton.InstantPopup)
        self.btn_insert.setMenu(self.ins_menu)
        tb.addWidget(self.btn_insert)
        # 주석 (형광펜·밑줄·사각형·화살표·메모)
        self.annot_kind = None
        self.annot_color = None         # None = 종류별 기본색
        self.ann_menu = QMenu(self)
        self.ann_actions = {}
        for k, icon in [("highlight", "annotate"), ("underline", "underline"), ("rect", "shape-rect"),
                        ("arrow", "shape-arrow"), ("note", "note")]:
            a = self.ann_menu.addAction(ov.SHAPE_KINDS[k], lambda k=k: self.start_annot(k))
            bind_icon(a, icon, 'text', 18)
            a.setCheckable(True)
            self.ann_actions[k] = a
        self.ann_menu.addSeparator()
        cm = self.ann_menu.addMenu("색")
        self.color_actions = []
        for name, col in [("종류별 기본색", None)] + ANNOT_COLORS:
            a = cm.addAction(name, lambda col=col: self.set_annot_color(col))
            a.setCheckable(True)
            if col:
                pm = QPixmap(14, 14)
                pm.fill(QColor.fromRgbF(*col))
                a.setIcon(QIcon(pm))
            self.color_actions.append((a, col))
        self.color_actions[0][0].setChecked(True)
        self.btn_annot = QToolButton()
        self.btn_annot.setText("주석")
        self.btn_annot.setToolTip("형광펜·밑줄·사각형·화살표·메모 (드래그해서 그리기, Esc 끝내기)")
        bind_icon(self.btn_annot, "annotate", 'text', 20)
        self.btn_annot.setIconSize(QSize(20, 20))
        self.btn_annot.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.btn_annot.setPopupMode(QToolButton.InstantPopup)
        self.btn_annot.setCheckable(True)
        self.btn_annot.setMenu(self.ann_menu)
        tb.addWidget(self.btn_annot)
        self.a_white = self._act("eraser", "지우기", lambda c: self.set_mode('white' if c else None),
                                 checkable=True, tip="영역 지우기 (드래그)")
        self.a_repl = self._act("replace", "찾아 바꾸기", self.replace_text, "Ctrl+H", tip="텍스트 찾아 바꾸기",
                                toolbar=False)
        # 글자 크기·색
        self.font_box = QWidget()
        fh = QHBoxLayout(self.font_box)
        fh.setContentsMargins(6, 0, 4, 0)
        fh.setSpacing(4)
        self.sp_font = QSpinBox()
        self.sp_font.setRange(4, 200)
        self.sp_font.setValue(12)
        self.sp_font.setSuffix(" pt")
        self.sp_font.setToolTip("글자 크기")
        self.sp_font.setFixedWidth(70)
        fh.addWidget(self.sp_font)
        self.btn_color = QToolButton()
        self.btn_color.setToolTip("글자 색")
        self.btn_color.setIconSize(QSize(20, 20))
        self.btn_color.clicked.connect(self.pick_color)
        fh.addWidget(self.btn_color)
        self._paint_color_btn()
        tb.addWidget(self.font_box)
        tb.addSeparator()
        # 더보기
        self.a_saveas = self._act("save-as", "다른 이름 저장", self.save_as, "Ctrl+Shift+S", toolbar=False)
        self.a_deco = self._act("page-deco", "페이지 번호·머리글·워터마크…", self.page_deco, toolbar=False)
        self.a_pick = self._act("merge", "다른 PDF에서 페이지 가져오기…", self.open_page_picker, toolbar=False)
        self.a_compress = self._act("compress", "용량 줄이기…", self.compress_pdf, toolbar=False)
        self.a_blank = self._act("page-add", "빈 페이지 넣기", self.insert_blank, toolbar=False)
        self.a_ext = self._act("extract", "선택 페이지 추출", self.extract, toolbar=False)
        self.a_split = self._act("split", "PDF 분할", self.split, toolbar=False)
        menu = QMenu(self)
        menu.addAction(self.a_saveas)
        menu.addAction(self.a_compress)
        menu.addSeparator()
        menu.addAction(self.a_repl)
        menu.addAction(self.a_deco)
        menu.addAction(self.a_pick)
        menu.addAction(self.a_blank)
        menu.addAction(self.a_ext)
        menu.addAction(self.a_split)
        self.btn_more = QToolButton()
        self.btn_more.setText("더보기")
        bind_icon(self.btn_more, "more", 'text', 20)
        self.btn_more.setIconSize(QSize(20, 20))
        self.btn_more.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.btn_more.setPopupMode(QToolButton.InstantPopup)
        self.btn_more.setMenu(menu)
        tb.addWidget(self.btn_more)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)
        # 보기
        # 보기: [이어보기] | [−] [배율 ▾] [+] 를 테두리 상자 하나로 묶고, 아래에 다른 버튼처럼 라벨
        self.a_cont = self._act("scroll-view", "이어보기", lambda c: self.set_continuous(c), checkable=True,
                                tip="페이지 이어서 보기 (연속 스크롤)", toolbar=False)
        self.a_zout = self._act("zoom-out", "축소", lambda: self.step_zoom(-1), "Ctrl+-", tip="축소", toolbar=False)
        self.a_zin = self._act("zoom-in", "확대", lambda: self.step_zoom(1), "Ctrl+=", tip="확대", toolbar=False)
        self.cb_zoom = QComboBox(objectName="ZoomCombo")
        self.cb_zoom.addItems(ZOOMS)
        self.cb_zoom.setCurrentText(FIT)
        self.cb_zoom.setFixedWidth(84)
        self.cb_zoom.setToolTip("배율 (Ctrl+휠로도 조절)")
        self.cb_zoom.currentTextChanged.connect(lambda _: (setattr(self, "_jump", True), self.render_preview()))
        self.view_box = QWidget()
        vb = QVBoxLayout(self.view_box)
        vb.setContentsMargins(4, 2, 4, 0)
        vb.setSpacing(3)
        box = QFrame(objectName="ViewBox")
        box.setFixedHeight(30)
        hb = QHBoxLayout(box)
        hb.setContentsMargins(2, 1, 2, 1)
        hb.setSpacing(0)

        def vbtn(action):
            b = QToolButton(objectName="ViewBtn")
            b.setDefaultAction(action)
            b.setToolButtonStyle(Qt.ToolButtonIconOnly)
            b.setIconSize(QSize(18, 18))
            b.setFixedSize(30, 26)
            return b

        def vsep():
            s = QFrame(objectName="ViewSep")
            s.setFixedSize(1, 18)
            return s
        hb.addWidget(vbtn(self.a_cont))
        hb.addWidget(vsep())
        hb.addWidget(vbtn(self.a_zout))
        hb.addWidget(self.cb_zoom)
        hb.addWidget(vbtn(self.a_zin))
        vb.addWidget(box)
        cap = QLabel("보기 · 배율", objectName="ToolCaption")
        cap.setAlignment(Qt.AlignHCenter)
        vb.addWidget(cap)
        tb.addWidget(self.view_box)

        # 본문: 빈 화면(드롭존) / 편집 화면
        self.body = QStackedWidget()
        new_btn = icon_button("이미지·PDF로 새로 만들기", "page-add", lambda: self.merge_files(), kind=None)
        open_btn = icon_button("PDF 열기", "open", self.open_pdf, kind="Primary")
        self.drop = DropZone(PDF_EXT | IMG_EXT, "파일을 끌어다 놓거나 클릭해서 열기",
                             "PDF 또는 이미지(JPG·PNG·HEIC) · 여러 개를 놓으면 하나로 합칩니다",
                             [open_btn, new_btn])
        self.drop.clicked.connect(self.open_pdf)
        self.drop.filesDropped.connect(self.open_files)
        dw = QWidget(objectName="Page")
        dl = QVBoxLayout(dw)
        dl.setContentsMargins(32, 28, 32, 28)
        dl.addWidget(self.drop)
        self.body.addWidget(dw)

        ed = QWidget(objectName="Page")
        eh = QHBoxLayout(ed)
        eh.setContentsMargins(12, 12, 12, 12)
        eh.setSpacing(12)
        self.pages = PageList()
        self.pages.setFixedWidth(184)
        self._jump = False
        self.pages.currentRowChanged.connect(lambda _: (setattr(self, "_jump", True), self.render_preview()))
        self.pages.movedTo.connect(self.on_moved_to)
        self.pages.filesDroppedAt.connect(self.on_files_dropped_at)
        self.pages.pagesDroppedAt.connect(self.on_pages_dropped_at)
        self._sources = {}              # 다른 PDF 토큰 → 문서
        self._picker = None
        eh.addWidget(self.pages)
        # 미리보기: 캔버스 위에 PageView 들 (한 페이지 보기 = 1개, 연속 보기 = 페이지 수만큼, 보이는 것만 그림)
        self.scroll = QScrollArea(objectName="Viewer")
        self.scroll.setWidgetResizable(True)
        self.canvas = QWidget(objectName="Canvas")
        self.canvas_lay = QVBoxLayout(self.canvas)
        self.canvas_lay.setContentsMargins(20, 20, 20, 20)
        self.canvas_lay.setSpacing(16)
        self.canvas_lay.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.scroll.setWidget(self.canvas)
        self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.scroll.viewport().installEventFilter(self)
        self._views = []
        self._render_gen = 0            # 문서 내용이 바뀔 때마다 증가 → 다시 그림
        self._scroll_sync = False
        self._view_mode = None
        self.continuous = theme.settings().value("continuous", False, type=bool)
        self.a_cont.setChecked(self.continuous)
        self._make_views(1)
        self.pages.itemPressed.connect(lambda _it: self._deselect_object())
        self._editor = None             # InlineTextEditor
        self._edit_unit = None
        eh.addWidget(self.scroll, 1)
        self.body.addWidget(ed)
        v.addWidget(self.body, 1)

        self.setAcceptDrops(True)
        self.edit_actions = [self.a_save, self.a_saveas, self.a_rl, self.a_rr, self.a_del, self.a_blank,
                             self.a_up, self.a_dn, self.a_ext, self.a_split, self.a_text, self.a_white,
                             self.a_repl, self.a_zin, self.a_zout, self.a_edit, self.a_deco, self.a_pick,
                             self.a_compress, self.a_cont]
        self.edit_widgets = [self.font_box, self.view_box, self.btn_edit, self.btn_insert, self.btn_annot]

    def _paint_color_btn(self):
        """물방울(테마 글자색) + 아래 막대(선택한 글자 색). 검정도 다크모드에서 보이도록 막대에 테두리"""
        col = QColor(*[int(x * 255) for x in self.color])
        pm = QPixmap(48, 48)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.drawPixmap(8, 0, theme.svg_pixmap("color", theme.C['text'], 32, 1.0))
        p.setPen(QColor(theme.C['text3']))
        p.setBrush(col)
        p.drawRoundedRect(6, 38, 36, 8, 3, 3)
        p.end()
        pm.setDevicePixelRatio(2.0)
        self.btn_color.setIcon(QIcon(pm))
        self.btn_color.setToolTip(f"글자 색 ({col.name()})")

    def on_theme_changed(self):
        self._paint_color_btn()
        if self.doc is not None:   # 썸네일 테두리 색 갱신
            self.refresh(self.sel_rows())

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        self.open_files(collect_files([u.toLocalFile() for u in e.mimeData().urls()], PDF_EXT | IMG_EXT))

    def open_files(self, files):
        if not files:
            return
        if self.doc is None and os.path.splitext(files[0])[1].lower() == '.pdf':
            self.load(files[0])
            files = files[1:]
        if files:
            self.merge_files(files)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.cb_zoom.currentText() == FIT:
            self.render_preview()

    # ── 상태 ──
    def status_text(self):
        if self.doc is None:
            return "열린 파일 없음"
        name = os.path.basename(self.path) if self.path else "새 문서"
        cur = max(self.pages.currentRow(), 0) + 1
        s = (f"{name}{' *' if self.modified else ''}    ·    페이지 {cur} / {self.doc.page_count}"
             f"    ·    배율 {round(self.zoom * 100)}%")
        if len(self.layer):
            s += f"    ·    삽입·주석 {len(self.layer)}개 (저장 시 PDF에 반영)"
        return s

    def _update_state(self):
        has = self.doc is not None
        for a in self.edit_actions:
            a.setEnabled(has)
        for w in self.edit_widgets:
            w.setEnabled(has)
        self.btn_more.setEnabled(has)
        self.a_undo.setEnabled(bool(self.undo_stack))
        self.body.setCurrentIndex(1 if has else 0)
        if self.win.stack.currentWidget() in (None, self):
            self.win.set_doc_info(self.status_text())

    def snapshot(self):
        """실행취소 지점: PDF + 삽입 객체 레이어"""
        self.undo_stack.append((self.doc.tobytes(), self.layer.copy()))
        if len(self.undo_stack) > UNDO_LIMIT:
            self.undo_stack.pop(0)
        self.modified = True

    def _restore(self, state):
        data, layer = state
        self.doc = pdf_ops.doc_from_bytes(data)
        self.layer = layer

    def undo(self):
        self.finish_edit(commit=False)
        if not self.undo_stack:
            return
        cur = self.pages.currentRow()
        self._restore(self.undo_stack.pop())
        if self.layer.get(self.sel_obj) is None:
            self.sel_obj = None
        self.refresh([min(max(cur, 0), self.doc.page_count - 1)])

    def sel_rows(self):
        rows = sorted({self.pages.row(i) for i in self.pages.selectedItems()})
        if not rows and self.pages.currentRow() >= 0:
            rows = [self.pages.currentRow()]
        return rows

    def confirm_discard(self):
        self.finish_edit(commit=True)
        if self.doc is None or not self.modified:
            return True
        mb = QMessageBox(QMessageBox.Question, APP_NAME, "변경 내용을 저장할까요?",
                         QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, self)
        mb.button(QMessageBox.Save).setText("저장")
        mb.button(QMessageBox.Discard).setText("저장 안 함")      # Qt 번역은 '무시'라 어색
        mb.button(QMessageBox.Cancel).setText("취소")
        mb.setDefaultButton(QMessageBox.Save)
        mb.exec()
        r = mb.standardButton(mb.clickedButton())
        if r == QMessageBox.Save:
            return self.save()
        return r == QMessageBox.Discard

    # ── 파일 ──
    def open_pdf(self):
        if not self.confirm_discard():
            return
        p, _ = QFileDialog.getOpenFileName(self, "PDF 열기", "", PDF_FILTER)
        if p:
            self.load(p)

    def load(self, path):
        try:
            self.doc = pdf_ops.open_pdf(path, ask_password(self))
        except Exception as ex:
            QMessageBox.warning(self, APP_NAME, f"열기 실패\n{ex}")
            return
        self.path = path
        self.modified = False
        self.undo_stack.clear()
        self.layer = ov.ObjectLayer()
        self.sel_obj = None
        self._obj_pix.clear()
        self.refresh([0])

    def merge_files(self, files=None):
        if not files:
            files, _ = QFileDialog.getOpenFileNames(self, "추가할 파일", "",
                                                    f"PDF/이미지 (*.pdf {' '.join('*' + e for e in IMG_EXT)})")
        if not files:
            return
        if self.doc is None:
            self.doc = pdf_ops.new_doc()
            self.path = None
            self.layer = ov.ObjectLayer()
            self.sel_obj = None
        else:
            self.snapshot()
        start = self.doc.page_count
        for name, ex in pdf_ops.merge_into(self.doc, files, ask_password(self)):
            QMessageBox.warning(self, APP_NAME, f"{name} 추가 실패\n{ex}")
        if self.doc.page_count == 0:
            self.doc = None
            self.refresh()
            return
        self.modified = True
        self.refresh([min(start, self.doc.page_count - 1)])

    def save(self):
        self.finish_edit(commit=True)
        if self.doc is None:
            return False
        if not self.path:
            return self.save_as()
        return self._write(self.path)

    def save_as(self):
        self.finish_edit(commit=True)
        if self.doc is None:
            return False
        p, _ = QFileDialog.getSaveFileName(self, "다른 이름 저장", self.path or "편집본.pdf", PDF_FILTER)
        if not p:
            return False
        p = with_ext(p, '.pdf')
        if self._write(p):
            self.path = p
            self._update_state()
            return True
        return False

    def _write(self, path):
        merged = len(self.layer)
        if merged:                      # 삽입 객체를 PDF 에 합침 (실행취소로 되돌릴 수 있게 지점 저장)
            self.snapshot()
            self.layer.flatten(self.doc)
            self.sel_obj = None
        try:
            size = pdf_ops.write_doc(self.doc, path)
        except Exception as ex:
            QMessageBox.warning(self, APP_NAME, f"저장 실패\n{ex}")
            return False
        self.modified = False
        if merged:
            self.refresh(self.sel_rows())
        self._update_state()
        self.win.toast(f"저장 완료 · {os.path.basename(path)} ({human(size)})"
                       + (f" · 삽입·주석 {merged}개 반영" if merged else ""))
        return True

    # ── 화면 ──
    def refresh(self, select=None):
        self._render_gen += 1                # 내용이 바뀜 → 미리보기 다시 그림
        self.pages.blockSignals(True)
        self.pages.clear()
        if self.doc is not None:
            for i, page in enumerate(self.doc):
                pix = page.get_pixmap(matrix=fitz.Matrix(0.2, 0.2), alpha=False)
                pm = QPixmap.fromImage(pix_to_qimage(pix))
                objs = self.layer.on_page(page.xref)
                if objs:                # 썸네일에도 삽입 객체 표시
                    p = QPainter(pm)
                    p.setRenderHint(QPainter.SmoothPixmapTransform)
                    for o in objs:
                        it = self._obj_item(o, 0.2)
                        if o.is_image:
                            p.drawPixmap(it['rect'], it['pix'], QRectF(it['pix'].rect()))
                        else:
                            if o.kind == "note":
                                it['rect'] = QRectF(it['rect'].x(), it['rect'].y(), 5, 5)
                            paint_shape(p, it, it['rect'], 0.2)
                    p.end()
                it = QListWidgetItem(plain_icon(framed(pm)), f"{i + 1}")
                it.setData(Qt.UserRole, i)
                self.pages.addItem(it)
                if i % 20 == 0:
                    QApplication.processEvents()
        self.pages.blockSignals(False)
        if self.doc is not None and self.doc.page_count:
            sel = [r for r in (select or [0]) if 0 <= r < self.doc.page_count] or [0]
            self.pages.setCurrentRow(sel[0])
            for r in sel:
                self.pages.item(r).setSelected(True)
        self.render_preview()
        self._update_state()

    def current_page(self):
        r = self.pages.currentRow()
        if self.doc is None or r < 0 or r >= self.doc.page_count:
            return None
        return self.doc[r]

    def step_zoom(self, d):
        i = self.cb_zoom.currentIndex()
        if self.cb_zoom.currentText() == FIT:
            # 현재 배율에서 가장 가까운 다음 단계로
            pct = [int(z.rstrip('%')) for z in ZOOMS[1:]]
            cur = self.zoom * 100
            nxt = [k for k, p in enumerate(pct) if (p > cur + 1 if d > 0 else p < cur - 1)]
            i = (nxt[0] if d > 0 else nxt[-1]) + 1 if nxt else (len(ZOOMS) - 1 if d > 0 else 1)
        else:
            i = min(max(1, i + d), len(ZOOMS) - 1)
        self.cb_zoom.setCurrentIndex(i)

    # ── 미리보기 (한 페이지 / 연속 스크롤) ──
    @property
    def view(self):
        """현재 페이지의 PageView"""
        if self.continuous and len(self._views) > 1:
            r = self.pages.currentRow()
            if 0 <= r < len(self._views):
                return self._views[r]
        return self._views[0]

    def _make_views(self, n):
        for v in self._views:
            self.canvas_lay.removeWidget(v)
            v.hide()
            v.deleteLater()
        self._views = []
        for i in range(max(1, n)):
            v = PageView()
            v.index = i
            v.rendered_key = None
            self._connect_view(v)
            v.set_mode(self._view_mode)
            for k in ("annot_kind", "annot_color", "place_aspect"):
                if hasattr(self, "_va_" + k):
                    setattr(v, k, getattr(self, "_va_" + k))
            self.canvas_lay.addWidget(v)
            self._views.append(v)

    def _connect_view(self, v):
        def route(slot):
            def f(*a):
                self._make_current(v)        # 다른 페이지를 건드리면 그 페이지가 현재 페이지
                return slot(*a)
            return f
        v.clicked.connect(route(self.on_text_click))
        v.dragged.connect(route(self.on_white_drag))
        v.editRequested.connect(route(self.start_edit))
        v.emptyClicked.connect(route(self.on_edit_empty_click))
        v.objectSelected.connect(route(self.on_object_selected))
        v.objectChanged.connect(route(self.on_object_changed))
        v.objectMenu.connect(route(self.on_object_menu))
        v.placeRequested.connect(route(self.on_place))
        v.annotDrawn.connect(route(self.on_annot_drawn))
        v.objectDoubleClicked.connect(route(self.on_object_double_clicked))
        v.escapePressed.connect(self.on_escape)

    def _set_view_attr(self, name, value):
        setattr(self, "_va_" + name, value)
        for v in self._views:
            setattr(v, name, value)

    def _make_current(self, v):
        if not self.continuous or v.index == self.pages.currentRow():
            return
        self.finish_edit(commit=True)
        self.pages.blockSignals(True)
        self.pages.setCurrentRow(v.index)
        self.pages.clearSelection()
        self.pages.item(v.index).setSelected(True)
        self.pages.blockSignals(False)
        self.pages.scrollToItem(self.pages.item(v.index))
        self._after_current_changed()

    def _after_current_changed(self):
        cur = self.view
        for v in self._views:
            if v is not cur:
                v.set_edit_items([])
                if v.sel_id is not None:
                    v.sel_id = None
                    v.update()
        self._update_status_only()
        self._load_edit_items()
        page = self.current_page()
        if page is not None and (self.layer.get(self.sel_obj) is None
                                 or self.layer.get(self.sel_obj).page_xref != page.xref):
            self.sel_obj = None

    def set_continuous(self, on):
        self.finish_edit(commit=True)
        self.continuous = bool(on)
        self.a_cont.setChecked(self.continuous)
        theme.settings().setValue("continuous", self.continuous)
        self._make_views(self.doc.page_count if (self.continuous and self.doc is not None) else 1)
        self.render_preview()
        self.win.toast("연속 스크롤 보기" if self.continuous else "한 페이지씩 보기")

    def _compute_zoom(self, page):
        z = self.cb_zoom.currentText()
        if z == FIT:
            w = max(200, self.scroll.viewport().width() - 44)
            self.zoom = w / page.rect.width
        else:
            self.zoom = int(z.rstrip('%')) / 100

    def _render_view(self, v):
        if self.doc is None or v.index >= self.doc.page_count:
            return
        key = (self._render_gen, round(self.zoom, 5), v.index, self.doc.page_count)
        if v.rendered_key == key:
            return
        page = self.doc[v.index]
        pix = page.get_pixmap(matrix=fitz.Matrix(self.zoom, self.zoom), alpha=False)
        pm = QPixmap.fromImage(pix_to_qimage(pix))
        v.setPixmap(pm)
        v.setFixedSize(pm.size())
        v.rendered_key = key
        self._load_objects_for(v, with_sel=(v is self.view))

    def _layout_tops(self):
        """연속 보기에서 각 페이지의 캔버스 안 위쪽 위치·높이 (위젯이 아직 안 그려져도 계산 가능)"""
        m, gap = self.canvas_lay.contentsMargins().top(), self.canvas_lay.spacing()
        tops, y = [], m
        for i in range(self.doc.page_count):
            h = int(self.doc[i].rect.height * self.zoom)
            tops.append((y, h))
            y += h + gap
        self._tops = tops
        return tops

    def _render_visible(self):
        top = self.scroll.verticalScrollBar().value()
        h = self.scroll.viewport().height()
        tops = getattr(self, "_tops", None) or self._layout_tops()
        for v in self._views:
            if v.index < len(tops):
                y, ph = tops[v.index]
                if y + ph >= top - h // 2 and y <= top + h + h // 2:
                    self._render_view(v)

    def _on_scroll(self, _value):
        if not self.continuous or self.doc is None or len(self._views) < 2 or self._scroll_sync:
            if self.continuous and self.doc is not None and len(self._views) > 1:
                self._render_visible()
            return
        self._render_visible()
        line = self.scroll.verticalScrollBar().value() + self.scroll.viewport().height() / 3
        tops = self._tops
        idx = next((i for i, (y, ph) in enumerate(tops) if y <= line <= y + ph + self.canvas_lay.spacing()), None)
        if idx is not None and idx != self.pages.currentRow():
            self._scroll_sync = True
            self._make_current(self._views[idx])
            self._scroll_sync = False

    def eventFilter(self, obj, e):
        from PySide6.QtCore import QEvent
        if obj is self.scroll.viewport() and e.type() == QEvent.Wheel and e.modifiers() & Qt.ControlModifier:
            if self.doc is not None:                      # Ctrl+휠 = 확대/축소
                self.step_zoom(1 if e.angleDelta().y() > 0 else -1)
            return True
        return super().eventFilter(obj, e)

    def render_preview(self):
        self.finish_edit(commit=True)      # 페이지·배율이 바뀌면 열린 편집은 반영하고 닫음
        page = self.current_page()
        if page is None:
            if len(self._views) > 1:
                self._make_views(1)
            v = self._views[0]
            v.clear()
            v.rendered_key = None
            v.set_edit_items([])
            v.set_objects([])
            if self.doc is None:
                self._update_status_only()
            return
        self._compute_zoom(page)
        if self.continuous:
            n = self.doc.page_count
            if len(self._views) != n:
                self._make_views(n)
            z = self.zoom
            for v in self._views:                         # 자리만 먼저 잡고, 보이는 것만 그림
                r = self.doc[v.index].rect
                if v.rendered_key is None or v.rendered_key[1:] != (round(z, 5), v.index, n):
                    v.clear()
                    v.setFixedSize(int(r.width * z), int(r.height * z))
            tops = self._layout_tops()
            self.canvas.setMinimumHeight(tops[-1][0] + tops[-1][1] + self.canvas_lay.contentsMargins().bottom())
            cur = self.view
            cy, ch = tops[cur.index]
            sb = self.scroll.verticalScrollBar()
            sb.setMaximum(max(sb.maximum(), self.canvas.minimumHeight() - self.scroll.viewport().height()))
            vis_top, vis_bot = sb.value(), sb.value() + self.scroll.viewport().height()
            off_screen = cy + ch < vis_top or cy > vis_bot
            # 썸네일 클릭·배율 변경 때, 또는 현재 페이지가 화면 밖일 때만 그 페이지로 이동 (편집 중엔 화면 유지)
            if not self._scroll_sync and (self._jump or off_screen):
                self._scroll_sync = True             # 아래 setValue 가 현재 페이지를 바꾸지 않게
                sb.setValue(max(0, cy - 12))
                self._scroll_sync = False
            self._jump = False
            self._render_view(cur)
            self._render_visible()
        else:
            if len(self._views) != 1:
                self._make_views(1)
            self.canvas.setMinimumHeight(0)
            v = self._views[0]
            v.index = self.pages.currentRow()
            self._render_view(v)
        self._update_status_only()
        self._load_edit_items()
        self._load_objects()

    # ── 삽입 객체 (이미지·서명·도장) ──
    def _pix(self, o):
        pm = self._obj_pix.get(o.id)
        if pm is None:
            pm = QPixmap()
            pm.loadFromData(o.data)
            self._obj_pix[o.id] = pm
        return pm

    def _load_objects(self):
        page = self.current_page()
        if page is None:
            self.view.set_objects([])
            return
        if self.layer.get(self.sel_obj) is None or self.layer.get(self.sel_obj).page_xref != page.xref:
            self.sel_obj = None
        self._load_objects_for(self.view, with_sel=True)

    def _load_objects_for(self, v, with_sel=False):
        if self.doc is None or v.index >= self.doc.page_count:
            v.set_objects([])
            return
        page = self.doc[v.index]
        items = [self._obj_item(o, self.zoom) for o in self.layer.on_page(page.xref)]
        v.set_objects(items, self.sel_obj if with_sel else None)

    def _obj_item(self, o, z):
        """PageView 에 넘길 표시용 정보 (z: 배율)"""
        r = o.frect()
        if o.kind == "note":                     # 메모 아이콘은 배율과 무관하게 일정 크기
            rect = QRectF(r.x0 * z, r.y0 * z, 22, 22)
        else:
            rect = QRectF(r.x0 * z, r.y0 * z, r.width * z, r.height * z)
        d = {'id': o.id, 'rect': rect, 'aspect': o.aspect, 'resizable': o.resizable, 'kind': o.kind,
             'color': o.color, 'flip': o.flip, 'width': o.width, 'scale': z, 'text': o.text}
        d['pix'] = self._pix(o) if o.is_image else None
        return d

    # ── 주석 ──
    def start_annot(self, kind):
        if self.doc is None:
            return
        self.set_mode('annot')
        self.annot_kind = kind
        for k, a in self.ann_actions.items():
            a.setChecked(k == kind)
        self.btn_annot.setChecked(True)
        self._set_view_attr("annot_kind", kind)
        self._set_view_attr("annot_color", self.annot_color or ov.DEFAULT_COLORS[kind])
        how = "클릭해서 메모 붙이기" if kind == "note" else "드래그해서 그리기"
        self.win.toast(f"{ov.SHAPE_KINDS[kind]}: {how} · 계속 그릴 수 있습니다 (Esc 끝내기)", ms=8000)

    def set_annot_color(self, col):
        self.annot_color = col
        for a, c in self.color_actions:
            a.setChecked(c == col)
        if self.annot_kind:
            self._set_view_attr("annot_color", col or ov.DEFAULT_COLORS[self.annot_kind])

    def on_annot_drawn(self, s, e):
        page = self.current_page()
        kind = self.annot_kind
        if page is None or kind is None:
            return
        z = self.zoom
        s, e = (s.x() / z, s.y() / z), (e.x() / z, e.y() / z)
        color = self.annot_color or ov.DEFAULT_COLORS[kind]
        text = ""
        if kind == "note":
            text, ok = QInputDialog.getMultiLineText(self, "메모", "메모 내용:")
            if not ok or not text.strip():
                return
            s = (e[0], e[1])
        else:
            if abs(e[0] - s[0]) < 4 and abs(e[1] - s[1]) < 4:
                return                                   # 너무 작음(그냥 클릭)
            if kind in ("highlight", "underline"):
                r = ov.snap_to_text(page, fitz.Rect(s, e).normalize())
                if kind == "underline" and r == fitz.Rect(s, e).normalize():
                    r = fitz.Rect(min(s[0], e[0]), e[1] - 1, max(s[0], e[0]), e[1] + 1)
                s, e = (r.x0, r.y0), (r.x1, r.y1)
        self.snapshot()
        self.layer.add_shape(page.xref, kind, s, e, color, text)
        self.refresh([self.pages.currentRow()])

    def on_object_double_clicked(self, oid):
        o = self.layer.get(oid)
        if o is not None and o.kind == "note":
            self.edit_note(oid)

    def edit_note(self, oid):
        o = self.layer.get(oid)
        text, ok = QInputDialog.getMultiLineText(self, "메모", "메모 내용:", o.text)
        if ok and text != o.text:
            self.snapshot()
            self.layer.get(oid).text = text
            self.refresh([self.pages.currentRow()])

    def set_object_color(self, oid, col):
        if self.layer.get(oid) is None:
            return
        self.snapshot()
        self.layer.get(oid).color = col
        self.refresh([self.pages.currentRow()])

    def _build_insert_menu(self):
        m = self.ins_menu
        m.clear()
        a = m.addAction("이미지 파일 넣기…", lambda: self.insert_image_file(False))
        bind_icon(a, "insert-image", 'text', 18)
        a = m.addAction("도장·서명 이미지 넣기 (흰 배경 투명하게)…", lambda: self.insert_image_file(True))
        bind_icon(a, "stamp", 'text', 18)
        m.addAction(self.a_deco)
        m.addSeparator()
        a = m.addAction("서명 그리기…", self.draw_signature)
        bind_icon(a, "signature", 'text', 18)
        saved = ov.list_signatures()
        sub = m.addMenu("저장된 서명")
        sub.setEnabled(bool(saved))
        for p in saved[:8]:
            pm = QPixmap(p)
            act = sub.addAction(QIcon(pm.scaled(96, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation)),
                                os.path.splitext(os.path.basename(p))[0],
                                lambda p=p: self._insert_from_file(p, "signature"))
            act.setIconVisibleInMenu(True)
        sub.setStyleSheet("QMenu{icon-size:96px 40px;}")
        if saved:
            sub.addSeparator()
            sub.addAction("저장된 서명 폴더 열기", lambda: os.startfile(ov.signature_dir()))

    def insert_image_file(self, remove_bg=False):
        p, _ = QFileDialog.getOpenFileName(self, "도장·서명 이미지 선택" if remove_bg else "이미지 선택", "", IMG_FILTER)
        if p:
            self._insert_from_file(p, "stamp" if remove_bg else "image", remove_bg)

    def _insert_from_file(self, path, kind, remove_bg=False):
        try:
            data, size = ov.prepare_image(path, remove_bg=remove_bg)
        except Exception as ex:
            QMessageBox.warning(self, APP_NAME, f"이미지를 열 수 없습니다\n{ex}")
            return
        self.begin_place(data, size, kind)

    def draw_signature(self):
        dlg = SignatureDialog(self)
        if dlg.exec() != QDialog.Accepted or not dlg.result_png:
            return
        data, size = dlg.result_png
        if dlg.cb_save.isChecked():
            try:
                ov.save_signature(data)
            except Exception:
                pass
        self.begin_place(data, size, "signature")

    def begin_place(self, data, size, kind):
        if self.doc is None:
            return
        self._pending = (data, size, kind)
        self.set_mode('place')
        self._set_view_attr("place_aspect", size[0] / size[1])
        self.win.toast(f"{ov.KINDS[kind]}: 페이지를 클릭하거나 드래그해서 위치·크기를 정하세요 (Esc 취소)", ms=8000)

    def on_place(self, qr):
        page = self.current_page()
        if page is None or self._pending is None:
            return
        data, size, kind = self._pending
        z = self.zoom
        if qr.width() == 0:
            rect = ov.default_rect(page.rect, size, center=(qr.x() / z, qr.y() / z))
        else:
            rect = ov.rect_from_drag(qr.left() / z, qr.top() / z, qr.right() / z, qr.bottom() / z, size[0] / size[1])
        self._pending = None
        self.snapshot()
        o = self.layer.add(page.xref, rect, data, size, kind)
        self.sel_obj = o.id
        self.set_mode(None)
        self.refresh([self.pages.currentRow()])
        self.win.toast(f"{ov.KINDS[kind]} 넣음 · 끌어서 이동, 모서리로 크기조절(Shift: 비율 무시), Delete 삭제")

    def on_escape(self):
        if self.view.mode == 'annot':
            self.set_mode(None)
            self.win.toast("주석 그리기 끝")
        elif self.view.mode == 'place':
            self._pending = None
            self.set_mode(None)
            self.win.toast("넣기 취소")
        elif self.sel_obj is not None:
            self._deselect_object()

    def _deselect_object(self):
        if self.sel_obj is not None:
            self.sel_obj = None
            self.view.set_objects(self.view.objects, None)

    def on_object_selected(self, oid):
        self.sel_obj = oid

    def on_object_changed(self, oid, qr):
        page = self.current_page()
        o = self.layer.get(oid)
        if page is None or o is None:
            return
        z = self.zoom
        self.snapshot()
        o.rect = (qr.left() / z, qr.top() / z, qr.right() / z, qr.bottom() / z)
        if o.kind == "note":                             # 메모는 크기 고정
            o.rect = (o.rect[0], o.rect[1], o.rect[0] + ov.NOTE_SIZE, o.rect[1] + ov.NOTE_SIZE)
        self.layer.move(oid, 0, 0, bounds=page.rect)      # 페이지 밖으로 나가지 않게
        self.sel_obj = oid
        self.refresh([self.pages.currentRow()])

    def on_object_menu(self, oid, gpos):
        o = self.layer.get(oid)
        m = QMenu(self)
        if o.kind == "note":
            m.addAction("메모 내용 수정…", lambda: self.edit_note(oid))
        if not o.is_image:
            cm = m.addMenu("색 바꾸기")
            for name, col in ANNOT_COLORS:
                pm = QPixmap(14, 14)
                pm.fill(QColor.fromRgbF(*col))
                cm.addAction(QIcon(pm), name, lambda col=col: self.set_object_color(oid, col))
        else:
            m.addAction("원래 비율로 맞추기", lambda: self.reset_aspect(oid))
        m.addSeparator()
        a = m.addAction("삭제", lambda: self.delete_object(oid))
        a.setShortcut(QKeySequence("Delete"))
        bind_icon(a, "trash", 'text', 18)
        m.exec(gpos)

    def reset_aspect(self, oid):
        o = self.layer.get(oid)
        if o is None or not o.aspect:
            return
        self.snapshot()
        r = o.frect()
        o.rect = (r.x0, r.y0, r.x1, r.y0 + r.width / o.aspect)
        self.refresh([self.pages.currentRow()])

    def delete_object(self, oid):
        if self.layer.get(oid) is None:
            return
        self.snapshot()
        self.layer.remove(oid)
        self._obj_pix.pop(oid, None)
        self.sel_obj = None
        self.refresh([self.pages.currentRow()])
        self.win.toast("삭제했습니다 (Ctrl+Z로 되돌리기)")

    # ── 기존 글자 수정 ──
    def _view_rect(self, page, rect):
        r = fitz.Rect(rect) * page.rotation_matrix * fitz.Matrix(self.zoom, self.zoom)
        return QRectF(r.x0, r.y0, r.width, r.height)

    def _load_edit_items(self):
        page = self.current_page()
        if self.view.mode != 'edit' or page is None:
            self.view.set_edit_items([])
            return
        units = text_edit.text_units(page, self.edit_level)
        self.view.set_edit_items([(self._view_rect(page, u.bbox), u) for u in units])
        if not units:
            self.win.toast("텍스트가 없는 페이지입니다 (스캔 이미지는 글자 수정 불가)", error=True)

    def set_edit_level(self, level):
        self.edit_level = level
        self.a_lv_line.setChecked(level == text_edit.LINE)
        self.a_lv_block.setChecked(level == text_edit.BLOCK)
        if self.view.mode != 'edit':
            self.set_mode('edit')
        else:
            self.finish_edit(commit=True)
            self._load_edit_items()

    def on_edit_empty_click(self):
        if self._editor is not None:
            self.finish_edit(commit=True)
            return
        page = self.current_page()
        if page is not None and not text_edit.page_has_text(page):
            QMessageBox.information(self, APP_NAME,
                                    "텍스트가 없는 페이지입니다.\n스캔한 이미지 PDF는 글자를 수정할 수 없습니다.")

    def start_edit(self, unit):
        if self._editor is not None:
            same = unit is self._edit_unit
            self.finish_edit(commit=True)
            if same:
                return
            # 반영 후 페이지가 다시 그려졌으므로 같은 위치의 새 단위를 찾는다
            page = self.current_page()
            c = unit.bbox
            unit = text_edit.unit_at(text_edit.text_units(page, self.edit_level), (c.x0 + c.x1) / 2, (c.y0 + c.y1) / 2)
            if unit is None:
                return
        page = self.current_page()
        vr = self._view_rect(page, unit.bbox)
        col = QColor(*[int(x * 255) for x in unit.color]).name()
        ed = InlineTextEditor(self.view, unit.text, unit.size * self.zoom, col,
                              theme.ui_font_family(), vr.width() + 24)
        ed.committed.connect(lambda _t: self.finish_edit(commit=True))
        ed.cancelled.connect(lambda: self.finish_edit(commit=False))
        x = int(max(0, min(vr.x() - 6, self.view.width() - ed.width())))
        y = int(max(0, vr.y() - 6))
        ed.move(x, y)
        self._editor, self._edit_unit = ed, unit
        ed.focus()
        p = self.view.mapTo(self.canvas, QPoint(x + ed.width() // 2, y + ed.height()))
        self.scroll.ensureVisible(p.x(), p.y(), 40, 40)

    def finish_edit(self, commit=True):
        ed, unit = self._editor, self._edit_unit
        if ed is None:
            return
        self._editor = self._edit_unit = None
        new = ed.ed.toPlainText()
        ed.hide()
        ed.deleteLater()
        if not commit or new.rstrip("\n") == unit.text:
            return
        page = self.doc[unit.page_no]
        self.snapshot()
        try:
            desc = text_edit.replace_unit(self.doc, page, unit, new, self.font)
        except Exception as ex:
            self._restore(self.undo_stack.pop())
            QMessageBox.warning(self, APP_NAME, f"글자 수정 실패\n{ex}")
            desc = None
        self.refresh([unit.page_no])
        if desc:
            self.win.toast(f"글자 수정 완료 · {desc}")

    def _update_status_only(self):
        if self.win.stack.currentWidget() in (None, self):
            self.win.set_doc_info(self.status_text())

    def to_pdf_point(self, page, qp, dy=0.0):
        return pdf_ops.view_to_pdf_point(page, qp.x(), qp.y(), self.zoom, dy)

    # ── 페이지 조작 ──
    def rotate(self, ang):
        rows = self.sel_rows()
        if not rows:
            return
        self.snapshot()
        xrefs = {self.doc[r].xref for r in rows}
        fixed = sum(1 for o in self.layer.items if o.page_xref in xrefs)
        if fixed:                       # 회전하는 페이지의 삽입 객체는 먼저 PDF 에 합쳐서 함께 회전
            self.layer.flatten(self.doc, xrefs)
            self.sel_obj = None
        pdf_ops.rotate_pages(self.doc, rows, ang)
        self.refresh(rows)
        if fixed:
            self.win.toast(f"회전한 페이지의 삽입 객체 {fixed}개는 PDF에 합쳐졌습니다 (실행취소 가능)")

    def delete_pages(self):
        if self.sel_obj is not None and self.layer.get(self.sel_obj) is not None:
            self.delete_object(self.sel_obj)     # 선택된 삽입 객체가 있으면 그것을 삭제
            return
        rows = self.sel_rows()
        if not rows:
            return
        if len(rows) >= self.doc.page_count:
            QMessageBox.information(self, APP_NAME, "모든 페이지는 삭제할 수 없습니다.")
            return
        if QMessageBox.question(self, APP_NAME, f"{len(rows)}개 페이지를 삭제할까요?") != QMessageBox.Yes:
            return
        self.snapshot()
        pdf_ops.delete_pages(self.doc, rows)
        self.layer.drop_missing(self.doc)
        self.refresh([min(rows[0], self.doc.page_count - 1)])

    def insert_blank(self):
        r = max(self.pages.currentRow(), 0)
        self.snapshot()
        self.refresh([pdf_ops.insert_blank(self.doc, r)])

    def move(self, d):
        rows = self.sel_rows()
        order = pdf_ops.move_order(self.doc.page_count, rows, d)
        if order is None:
            return
        self.snapshot()
        pdf_ops.reorder(self.doc, order)
        self.refresh([r + d for r in rows])

    def on_moved_to(self, rows, target):
        """썸네일 여러 장을 끌어서 target 위치로"""
        order = pdf_ops.move_rows_to(self.doc.page_count, rows, target)
        if order is None:
            self.refresh(rows)
            return
        self.snapshot()
        pdf_ops.reorder(self.doc, order)
        self.refresh([order.index(r) for r in sorted(rows)])
        self.win.toast(f"{len(rows)}페이지 이동")

    def on_files_dropped_at(self, files, row):
        """탐색기에서 PDF·이미지를 썸네일 목록의 원하는 위치에 놓기"""
        if self.doc is None:
            self.open_files(files)
            return
        self.snapshot()
        n, errs = pdf_ops.insert_files_at(self.doc, files, row, ask_password(self))
        for name, ex in errs:
            QMessageBox.warning(self, APP_NAME, f"{name} 추가 실패\n{ex}")
        if n == 0:
            self._restore(self.undo_stack.pop())
            return
        self.refresh(list(range(row, row + n)))
        self.win.toast(f"{n}페이지를 {row + 1}번째 위치에 넣음")

    # ── 다른 PDF 에서 페이지 가져오기 ──
    def open_page_picker(self):
        if self._picker is None:
            self._picker = PagePickerWindow(self)
            self._picker.openRequested.connect(self._picker_open)
            self._picker.insertRequested.connect(
                lambda tok, pages: self.on_pages_dropped_at(tok, pages, max(self.pages.currentRow(), 0) + 1))
        self._picker.show()
        self._picker.raise_()
        if self._picker.token is None:
            self._picker_open()

    def _picker_open(self, path=None):
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self._picker, "페이지를 가져올 PDF", "", PDF_FILTER)
        if not path:
            return
        try:
            src = pdf_ops.open_pdf(path, ask_password(self._picker))
        except Exception as ex:
            QMessageBox.warning(self._picker, APP_NAME, f"열기 실패\n{ex}")
            return
        token = f"src{len(self._sources) + 1}"
        self._sources[token] = src
        pms = [QPixmap.fromImage(pix_to_qimage(pg.get_pixmap(matrix=fitz.Matrix(0.18, 0.18), alpha=False)))
               for pg in src]
        self._picker.set_source(token, os.path.basename(path), pms)

    def on_pages_dropped_at(self, token, pages, row):
        src = self._sources.get(token)
        if src is None or self.doc is None or not pages:
            return
        self.snapshot()
        at = pdf_ops.insert_pages_from(self.doc, src, pages, row)
        self.refresh(list(range(at, at + len(pages))))
        self.win.toast(f"다른 PDF에서 {len(pages)}페이지를 {at + 1}번째 위치에 넣음")

    def compress_pdf(self):
        from app.core import compress as cp
        size_txt = human(len(self.doc.tobytes())) + " (저장 전 기준)" if self.path is None else \
            human(os.path.getsize(self.path)) + " (파일 크기)" if os.path.exists(self.path) else ""
        dlg = CompressDialog(size_txt, self)
        if dlg.exec() != QDialog.Accepted:
            return
        dpi, q, gray = dlg.values()
        doc = self.doc
        try:
            res = run_task(self, "용량 줄이는 중...", 2, lambda t: cp.compress(doc, dpi, q, gray, t), busy_cursor=True)
        except Exception as ex:
            QMessageBox.warning(self, APP_NAME, f"용량 줄이기 실패\n{ex}")
            return
        if res.after >= res.before:
            QMessageBox.information(self, APP_NAME, f"더 줄일 이미지가 없습니다.\n현재 {human(res.before)}")
            return
        msg = (f"{human(res.before)} → {human(res.after)}  ({res.saved_pct:.0f}% 감소)\n\n"
               "이대로 적용할까요? (저장해야 파일에 반영, Ctrl+Z로 되돌리기 가능)")
        if QMessageBox.question(self, "PDF 용량 줄이기", msg) != QMessageBox.Yes:
            return
        self.snapshot()
        new = pdf_ops.doc_from_bytes(res.data)
        self.layer.remap(self.doc, new)
        self.doc = new
        self.refresh(self.sel_rows())
        self.win.toast(f"용량 줄이기 적용 · {human(res.before)} → {human(res.after)}")

    def page_deco(self):
        from app.core import page_deco as pdc
        dlg = PageDecoDialog(self.doc, max(self.pages.currentRow(), 0), pdc.filename_of(self.path), self)
        if dlg.exec() != QDialog.Accepted:
            return
        o = dlg.options()
        n = len(pdc.target_pages(o, self.doc.page_count))
        self.snapshot()
        try:
            run_task(self, "페이지 꾸미는 중...", n, lambda t: pdc.decorate(self.doc, o, t))
        except Exception as ex:
            self._restore(self.undo_stack.pop())
            QMessageBox.warning(self, APP_NAME, f"적용 실패\n{ex}")
            return
        self.refresh(self.sel_rows())
        what = [w for w, on in (("페이지 번호", o.numbers.enabled), ("머리글·바닥글", o.hf.enabled),
                                ("워터마크", o.wm.enabled)) if on]
        self.win.toast(f"{n}페이지에 {'·'.join(what)} 적용 (Ctrl+Z로 되돌리기)")

    def _output_doc(self):
        """추출·분할용: 삽입 객체가 있으면 합쳐진 사본 (편집 중 레이어는 그대로)"""
        return ov.flattened_copy(self.doc, self.layer) if len(self.layer) else self.doc

    def _base_name(self):
        return os.path.splitext(os.path.basename(self.path or "문서.pdf"))[0]

    def extract(self):
        rows = self.sel_rows()
        if not rows:
            return
        p, _ = QFileDialog.getSaveFileName(self, "추출 파일 저장", f"{self._base_name()}_추출.pdf", PDF_FILTER)
        if not p:
            return
        pdf_ops.extract_pages(self._output_doc(), rows, p)
        self.win.toast(f"{len(rows)}페이지 추출 완료 · {os.path.basename(p)}")

    def split(self):
        dlg = SplitDialog(self.doc.page_count, self)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            groups = dlg.groups()
        except ValueError as ex:
            QMessageBox.warning(self, APP_NAME, str(ex))
            return
        if not groups:
            return
        out = QFileDialog.getExistingDirectory(self, "저장 폴더",
                                               os.path.dirname(self.path) if self.path else "")
        if not out:
            return
        base = self._base_name()
        src = self._output_doc()
        try:
            run_task(self, "분할 중...", len(groups),
                     lambda t: pdf_ops.split_doc(src, groups, out, base, t))
        except Exception as ex:
            QMessageBox.warning(self, APP_NAME, f"분할 실패\n{ex}")
            return
        QMessageBox.information(self, APP_NAME, f"{len(groups)}개 파일로 분할 완료\n{out}")

    # ── 내용 편집 ──
    def set_mode(self, m):
        self.finish_edit(commit=True)
        if m != 'place':
            self._pending = None
        if m is not None:
            self.sel_obj = None
        if m != 'annot':
            self.annot_kind = None
            for a in self.ann_actions.values():
                a.setChecked(False)
            self.btn_annot.setChecked(False)
        self.a_text.setChecked(m == 'text')
        self.a_white.setChecked(m == 'white')
        self.a_edit.setChecked(m == 'edit')
        self._view_mode = m
        for v in self._views:
            v.set_mode(m)
        self._load_edit_items()
        if self.doc is not None:
            self._load_objects()

    def pick_color(self):
        c = QColorDialog.getColor(QColor(*[int(x * 255) for x in self.color]), self, "글자 색")
        if c.isValid():
            self.color = (c.redF(), c.greenF(), c.blueF())
            self._paint_color_btn()

    def on_text_click(self, qp):
        page = self.current_page()
        if page is None:
            return
        text, ok = QInputDialog.getMultiLineText(self, "텍스트 추가", "입력할 내용:")
        if not ok or not text.strip():
            return
        size = self.sp_font.value()
        self.snapshot()
        try:
            pdf_ops.insert_text(page, self.to_pdf_point(page, qp, size), text, size, self.color, self.font)
        except Exception as ex:
            QMessageBox.warning(self, APP_NAME, f"텍스트 추가 실패\n{ex}")
        self.refresh([self.pages.currentRow()])

    def on_white_drag(self, qr):
        page = self.current_page()
        if page is None:
            return
        p1 = self.to_pdf_point(page, qr.topLeft())
        p2 = self.to_pdf_point(page, qr.bottomRight())
        self.snapshot()
        pdf_ops.redact_rect(page, fitz.Rect(p1, p2).normalize())
        self.refresh([self.pages.currentRow()])

    def replace_text(self):
        dlg = ReplaceDialog(self)
        if dlg.exec() != QDialog.Accepted or not dlg.ed_old.text():
            return
        old, new = dlg.ed_old.text(), dlg.ed_new.text()
        rows = range(self.doc.page_count) if dlg.cb_all.isChecked() else [self.pages.currentRow()]
        self.snapshot()
        cnt = pdf_ops.replace_text(self.doc, rows, old, new, self.font)
        if cnt == 0:
            self.undo_stack.pop()
            QMessageBox.information(self, APP_NAME, "찾는 내용이 없습니다.")
            return
        self.refresh([max(self.pages.currentRow(), 0)])
        QMessageBox.information(self, APP_NAME, f"{cnt}건 변경 완료")
