# -*- coding: utf-8 -*-
"""PDF 편집 탭"""
import os

from PySide6.QtCore import Qt, QSize, QRectF
from PySide6.QtGui import QPixmap, QColor, QAction, QKeySequence, QPainter, QIcon
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QToolBar, QToolButton, QLabel, QSpinBox,
    QComboBox, QScrollArea, QListWidgetItem, QMessageBox, QFileDialog, QInputDialog, QColorDialog,
    QDialog, QMenu, QStackedWidget, QSizePolicy,
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
)
from app.ui.dialogs import SplitDialog, ReplaceDialog, SignatureDialog, ask_password
from app.ui.workers import run_task

UNDO_LIMIT = 15
FIT = "폭 맞춤"
ZOOMS = [FIT, "50%", "75%", "100%", "125%", "150%", "200%"]


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
        self.a_white =self._act("eraser", "지우기", lambda c: self.set_mode('white' if c else None),
                                 checkable=True, tip="영역 지우기 (드래그)")
        self.a_repl = self._act("replace", "바꾸기", self.replace_text, "Ctrl+H", tip="텍스트 찾아 바꾸기")
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
        self.a_blank = self._act("page-add", "빈 페이지 넣기", self.insert_blank, toolbar=False)
        self.a_ext = self._act("extract", "선택 페이지 추출", self.extract, toolbar=False)
        self.a_split = self._act("split", "PDF 분할", self.split, toolbar=False)
        menu = QMenu(self)
        menu.addAction(self.a_saveas)
        menu.addSeparator()
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
        self.a_zout = self._act("zoom-out", "", lambda: self.step_zoom(-1), "Ctrl+-", tip="축소")
        self.cb_zoom = QComboBox()
        self.cb_zoom.addItems(ZOOMS)
        self.cb_zoom.setCurrentText(FIT)
        self.cb_zoom.setFixedWidth(92)
        self.cb_zoom.currentTextChanged.connect(lambda _: self.render_preview())
        tb.addWidget(self.cb_zoom)
        self.a_zin = self._act("zoom-in", "", lambda: self.step_zoom(1), "Ctrl+=", tip="확대")

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
        self.pages.currentRowChanged.connect(lambda _: self.render_preview())
        self.pages.reordered.connect(self.on_reordered)
        eh.addWidget(self.pages)
        self.scroll = QScrollArea(objectName="Viewer")
        self.scroll.setAlignment(Qt.AlignCenter)
        self.view = PageView()
        self.view.clicked.connect(self.on_text_click)
        self.view.dragged.connect(self.on_white_drag)
        self.view.editRequested.connect(self.start_edit)
        self.view.emptyClicked.connect(self.on_edit_empty_click)
        self.view.objectSelected.connect(self.on_object_selected)
        self.view.objectChanged.connect(self.on_object_changed)
        self.view.objectMenu.connect(self.on_object_menu)
        self.view.placeRequested.connect(self.on_place)
        self.view.escapePressed.connect(self.on_escape)
        self.pages.itemPressed.connect(lambda _it: self._deselect_object())
        self._editor = None             # InlineTextEditor
        self._edit_unit = None
        self.scroll.setWidget(self.view)
        self.scroll.setWidgetResizable(False)
        eh.addWidget(self.scroll, 1)
        self.body.addWidget(ed)
        v.addWidget(self.body, 1)

        self.setAcceptDrops(True)
        self.edit_actions = [self.a_save, self.a_saveas, self.a_rl, self.a_rr, self.a_del, self.a_blank,
                             self.a_up, self.a_dn, self.a_ext, self.a_split, self.a_text, self.a_white,
                             self.a_repl, self.a_zin, self.a_zout, self.a_edit]
        self.edit_widgets = [self.font_box, self.cb_zoom, self.btn_edit, self.btn_insert]

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
            s += f"    ·    삽입 객체 {len(self.layer)}개 (저장 시 PDF에 합쳐짐)"
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
        r = QMessageBox.question(self, APP_NAME, "변경 내용을 저장할까요?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
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
                       + (f" · 삽입 객체 {merged}개 합침" if merged else ""))
        return True

    # ── 화면 ──
    def refresh(self, select=None):
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
                        r = o.frect() * 0.2
                        p.drawPixmap(QRectF(r.x0, r.y0, r.width, r.height), self._pix(o), QRectF(self._pix(o).rect()))
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

    def render_preview(self):
        self.finish_edit(commit=True)      # 페이지·배율이 바뀌면 열린 편집은 반영하고 닫음
        page = self.current_page()
        if page is None:
            self.view.clear()
            self.view.set_edit_items([])
            self.view.set_objects([])
            if self.doc is None:
                self._update_status_only()
            return
        z = self.cb_zoom.currentText()
        if z == FIT:
            w = max(200, self.scroll.viewport().width() - 40)
            self.zoom = w / page.rect.width
        else:
            self.zoom = int(z.rstrip('%')) / 100
        pix = page.get_pixmap(matrix=fitz.Matrix(self.zoom, self.zoom), alpha=False)
        pm = QPixmap.fromImage(pix_to_qimage(pix))
        self.view.setPixmap(pm)
        self.view.resize(pm.size())
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
        z = self.zoom
        items = [{'id': o.id, 'pix': self._pix(o), 'aspect': o.aspect,
                  'rect': QRectF(o.rect[0] * z, o.rect[1] * z, (o.rect[2] - o.rect[0]) * z, (o.rect[3] - o.rect[1]) * z)}
                 for o in self.layer.on_page(page.xref)]
        if self.layer.get(self.sel_obj) is None or self.layer.get(self.sel_obj).page_xref != page.xref:
            self.sel_obj = None
        self.view.set_objects(items, self.sel_obj)

    def _build_insert_menu(self):
        m = self.ins_menu
        m.clear()
        a = m.addAction("이미지 파일 넣기…", lambda: self.insert_image_file(False))
        bind_icon(a, "insert-image", 'text', 18)
        a = m.addAction("도장·서명 이미지 넣기 (흰 배경 투명하게)…", lambda: self.insert_image_file(True))
        bind_icon(a, "stamp", 'text', 18)
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
        self.view.place_aspect = size[0] / size[1]
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
        if self.view.mode == 'place':
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
        self.layer.move(oid, 0, 0, bounds=page.rect)      # 페이지 밖으로 나가지 않게
        self.sel_obj = oid
        self.refresh([self.pages.currentRow()])

    def on_object_menu(self, oid, gpos):
        m = QMenu(self)
        a = m.addAction("삭제", lambda: self.delete_object(oid))
        a.setShortcut(QKeySequence("Delete"))
        bind_icon(a, "trash", 'text', 18)
        m.addAction("원래 비율로 맞추기", lambda: self.reset_aspect(oid))
        m.exec(gpos)

    def reset_aspect(self, oid):
        o = self.layer.get(oid)
        if o is None:
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
        self.win.toast("삽입 객체 삭제")

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
        self.scroll.ensureVisible(x + ed.width() // 2, y + ed.height(), 40, 40)

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

    def on_reordered(self):
        order = [self.pages.item(i).data(Qt.UserRole) for i in range(self.pages.count())]
        if order == list(range(len(order))):
            return
        sel = self.sel_rows()
        self.snapshot()
        pdf_ops.reorder(self.doc, order)
        self.refresh(sel)

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
        self.a_text.setChecked(m == 'text')
        self.a_white.setChecked(m == 'white')
        self.a_edit.setChecked(m == 'edit')
        self.view.set_mode(m)
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
