# -*- coding: utf-8 -*-
"""PDF 편집 탭"""
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QIcon, QColor, QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QToolBar, QLabel, QSpinBox, QPushButton, QComboBox,
    QSplitter, QScrollArea, QListWidgetItem, QMessageBox, QFileDialog, QInputDialog,
    QColorDialog, QDialog,
)

from app import APP_NAME
from app.core import pdf_ops
from app.core.utils import (
    fitz, IMG_EXT, PDF_EXT, PDF_FILTER, collect_files, human, korean_font, with_ext,
)
from app.ui.widgets import PageList, PageView, pix_to_qimage
from app.ui.dialogs import SplitDialog, ReplaceDialog, ask_password
from app.ui.workers import run_task

UNDO_LIMIT = 15
EMPTY_TEXT = "PDF 파일을 열거나 여기로 끌어다 놓으세요"


class PdfTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.doc = None
        self.path = None
        self.modified = False
        self.undo_stack = []
        self.zoom = 1.0
        self.color = (0, 0, 0)
        self.font = korean_font()
        self._build()
        self._update_state()

    # ── UI ──
    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(4, 4, 4, 4)
        tb = QToolBar()
        tb.setToolButtonStyle(Qt.ToolButtonTextOnly)
        v.addWidget(tb)

        def act(text, slot, sc=None, checkable=False):
            a = QAction(text, self)
            a.setCheckable(checkable)
            if sc:
                a.setShortcut(QKeySequence(sc))
            a.triggered.connect(slot)
            tb.addAction(a)
            return a

        act("열기", self.open_pdf, "Ctrl+O")
        act("PDF/이미지 추가(병합)", lambda: self.merge_files())
        self.a_save = act("저장", self.save, "Ctrl+S")
        self.a_saveas = act("다른 이름 저장", self.save_as, "Ctrl+Shift+S")
        tb.addSeparator()
        self.a_undo = act("실행취소", self.undo, "Ctrl+Z")
        tb.addSeparator()
        self.a_rl = act("⟲ 좌회전", lambda: self.rotate(-90), "Ctrl+L")
        self.a_rr = act("⟳ 우회전", lambda: self.rotate(90), "Ctrl+R")
        self.a_del = act("페이지 삭제", self.delete_pages, "Delete")
        self.a_blank = act("빈 페이지", self.insert_blank)
        self.a_up = act("▲ 위로", lambda: self.move(-1))
        self.a_dn = act("▼ 아래로", lambda: self.move(1))
        tb.addSeparator()
        self.a_ext = act("선택 페이지 추출", self.extract)
        self.a_split = act("분할", self.split)
        tb.addSeparator()
        self.a_text = act("텍스트 추가", lambda c: self.set_mode('text' if c else None), checkable=True)
        self.a_white = act("영역 지우기", lambda c: self.set_mode('white' if c else None), checkable=True)
        self.a_repl = act("찾아 바꾸기", self.replace_text, "Ctrl+H")
        tb.addSeparator()
        tb.addWidget(QLabel(" 글자 "))
        self.sp_font = QSpinBox()
        self.sp_font.setRange(4, 200)
        self.sp_font.setValue(12)
        tb.addWidget(self.sp_font)
        self.btn_color = QPushButton("■")
        self.btn_color.setFixedWidth(30)
        self.btn_color.setStyleSheet("color:#000;font-size:16px;")
        self.btn_color.clicked.connect(self.pick_color)
        tb.addWidget(self.btn_color)
        tb.addWidget(QLabel(" 배율 "))
        self.cb_zoom = QComboBox()
        self.cb_zoom.addItems(["폭 맞춤", "50%", "75%", "100%", "125%", "150%", "200%"])
        self.cb_zoom.setCurrentText("폭 맞춤")
        self.cb_zoom.currentTextChanged.connect(lambda _: self.render_preview())
        tb.addWidget(self.cb_zoom)

        sp = QSplitter()
        self.pages = PageList()
        self.pages.setMinimumWidth(190)
        self.pages.currentRowChanged.connect(lambda _: self.render_preview())
        self.pages.reordered.connect(self.on_reordered)
        sp.addWidget(self.pages)

        self.scroll = QScrollArea()
        self.scroll.setAlignment(Qt.AlignCenter)
        self.scroll.setStyleSheet("QScrollArea{background:#6b6b6b;}")
        self.view = PageView()
        self.view.clicked.connect(self.on_text_click)
        self.view.dragged.connect(self.on_white_drag)
        self.scroll.setWidget(self.view)
        self.scroll.setWidgetResizable(False)
        sp.addWidget(self.scroll)
        sp.setStretchFactor(1, 1)
        sp.setSizes([210, 900])
        v.addWidget(sp)

        self.setAcceptDrops(True)
        self.edit_actions = [self.a_save, self.a_saveas, self.a_rl, self.a_rr, self.a_del, self.a_blank,
                             self.a_up, self.a_dn, self.a_ext, self.a_split, self.a_text, self.a_white,
                             self.a_repl]

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        files = collect_files([u.toLocalFile() for u in e.mimeData().urls()], PDF_EXT | IMG_EXT)
        if not files:
            return
        if self.doc is None and os.path.splitext(files[0])[1].lower() == '.pdf':
            self.load(files[0])
            files = files[1:]
        if files:
            self.merge_files(files)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.cb_zoom.currentText() == "폭 맞춤":
            self.render_preview()

    # ── 상태 ──
    def _update_state(self):
        has = self.doc is not None
        for a in self.edit_actions:
            a.setEnabled(has)
        self.a_undo.setEnabled(bool(self.undo_stack))
        name = os.path.basename(self.path) if self.path else ("새 문서" if has else "")
        info = f"{name}{' *' if self.modified else ''}"
        if has:
            info += f"  |  {self.doc.page_count}페이지"
        self.win.set_status(info)

    def snapshot(self):
        self.undo_stack.append(self.doc.tobytes())
        if len(self.undo_stack) > UNDO_LIMIT:
            self.undo_stack.pop(0)
        self.modified = True

    def undo(self):
        if not self.undo_stack:
            return
        cur = self.pages.currentRow()
        self.doc = pdf_ops.doc_from_bytes(self.undo_stack.pop())
        self.refresh([min(max(cur, 0), self.doc.page_count - 1)])

    def sel_rows(self):
        rows = sorted({self.pages.row(i) for i in self.pages.selectedItems()})
        if not rows and self.pages.currentRow() >= 0:
            rows = [self.pages.currentRow()]
        return rows

    def confirm_discard(self):
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
        else:
            self.snapshot()
        start = self.doc.page_count
        for name, ex in pdf_ops.merge_into(self.doc, files, ask_password(self)):
            QMessageBox.warning(self, APP_NAME, f"{name} 추가 실패\n{ex}")
        self.modified = True
        self.refresh([min(start, self.doc.page_count - 1)])

    def save(self):
        if self.doc is None:
            return False
        if not self.path:
            return self.save_as()
        return self._write(self.path)

    def save_as(self):
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
        try:
            size = pdf_ops.write_doc(self.doc, path)
        except Exception as ex:
            QMessageBox.warning(self, APP_NAME, f"저장 실패\n{ex}")
            return False
        self.modified = False
        self._update_state()
        self.win.statusBar().showMessage(f"저장 완료: {path} ({human(size)})", 5000)
        return True

    # ── 화면 ──
    def refresh(self, select=None):
        self.pages.blockSignals(True)
        self.pages.clear()
        if self.doc is not None:
            for i, page in enumerate(self.doc):
                pix = page.get_pixmap(matrix=fitz.Matrix(0.2, 0.2), alpha=False)
                it = QListWidgetItem(QIcon(QPixmap.fromImage(pix_to_qimage(pix))), f"{i + 1}")
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

    def render_preview(self):
        page = self.current_page()
        if page is None:
            self.view.clear()
            self.view.setText(EMPTY_TEXT)
            self.view.setStyleSheet("color:#eee;font-size:14px;")
            self.view.resize(500, 200)
            return
        self.view.setStyleSheet("")
        z = self.cb_zoom.currentText()
        if z == "폭 맞춤":
            w = max(200, self.scroll.viewport().width() - 30)
            self.zoom = w / page.rect.width
        else:
            self.zoom = int(z.rstrip('%')) / 100
        pix = page.get_pixmap(matrix=fitz.Matrix(self.zoom, self.zoom), alpha=False)
        pm = QPixmap.fromImage(pix_to_qimage(pix))
        self.view.setPixmap(pm)
        self.view.resize(pm.size())

    def to_pdf_point(self, page, qp, dy=0.0):
        return pdf_ops.view_to_pdf_point(page, qp.x(), qp.y(), self.zoom, dy)

    # ── 페이지 조작 ──
    def rotate(self, ang):
        rows = self.sel_rows()
        if not rows:
            return
        self.snapshot()
        pdf_ops.rotate_pages(self.doc, rows, ang)
        self.refresh(rows)

    def delete_pages(self):
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

    def _base_name(self):
        return os.path.splitext(os.path.basename(self.path or "문서.pdf"))[0]

    def extract(self):
        rows = self.sel_rows()
        if not rows:
            return
        p, _ = QFileDialog.getSaveFileName(self, "추출 파일 저장", f"{self._base_name()}_추출.pdf", PDF_FILTER)
        if not p:
            return
        pdf_ops.extract_pages(self.doc, rows, p)
        self.win.statusBar().showMessage(f"{len(rows)}페이지 추출 완료: {p}", 5000)

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
        try:
            run_task(self, "분할 중...", len(groups),
                     lambda t: pdf_ops.split_doc(self.doc, groups, out, base, t))
        except Exception as ex:
            QMessageBox.warning(self, APP_NAME, f"분할 실패\n{ex}")
            return
        QMessageBox.information(self, APP_NAME, f"{len(groups)}개 파일로 분할 완료\n{out}")

    # ── 내용 편집 ──
    def set_mode(self, m):
        self.a_text.setChecked(m == 'text')
        self.a_white.setChecked(m == 'white')
        self.view.set_mode(m)

    def pick_color(self):
        c = QColorDialog.getColor(QColor(*[int(x * 255) for x in self.color]), self, "글자 색")
        if c.isValid():
            self.color = (c.redF(), c.greenF(), c.blueF())
            self.btn_color.setStyleSheet(f"color:{c.name()};font-size:16px;")

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
