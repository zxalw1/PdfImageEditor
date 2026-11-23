# -*- coding: utf-8 -*-
"""변환 탭: 변환 종류 카드 → 파일 목록 → 옵션 → 실행"""
import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLineEdit, QSpinBox, QComboBox, QCheckBox,
    QLabel, QStackedWidget, QFileDialog, QMessageBox,
)

from app import APP_NAME
from app.core.utils import IMG_EXT, PDF_EXT, IMG_FILTER, PDF_FILTER, parse_ranges, human, with_ext
from app.core import pdf_ops
from app.core.convert_ops import (
    PdfImageJob, pdf_to_images, pdf_to_single_images, images_to_pdf_each, images_to_pdf_single, office_to_pdf,
    pdfs_to_docs, PDF_DOC_TARGETS,
)
from app.core.office_com import OFFICE_EXT, OFFICE_FILTER, detect_engines
from app.ui.widgets import FilePanel, ChoiceCard, dir_row
from app.ui.dialogs import ask_password
from app.ui.workers import run_task


def _fail_text(errs, head="\n\n실패:\n"):
    return head + "\n".join(errs[:10]) if errs else ""


def _caption(text):
    lb = QLabel(text, objectName="Caption")
    lb.setWordWrap(True)
    return lb


class _Panel(FilePanel):
    def __init__(self, win=None, **kw):
        super().__init__(**kw)
        self.win = win

    def toast(self, text, ok=True):
        if self.win is not None:
            self.win.toast(text, error=not ok)


class Pdf2ImgPanel(_Panel):
    def __init__(self, win=None):
        super().__init__(win, exts=PDF_EXT, icon=32, thumbs=False, extra=False, run_text="이미지로 변환",
                         file_filter=PDF_FILTER, dialog_title="PDF 선택")
        f = self.form
        self.cb_mode = QComboBox()
        self.cb_mode.addItems(["페이지마다 이미지 1장씩", "PDF 전체를 이미지 1장으로 (세로로 이어붙이기)"])
        f.addRow("저장 방식", self.cb_mode)
        self.ed_pages = QLineEdit()
        self.ed_pages.setPlaceholderText("비우면 전체 (예: 1-3, 5)")
        f.addRow("페이지", self.ed_pages)
        self.sp_dpi = QSpinBox()
        self.sp_dpi.setRange(50, 600)
        self.sp_dpi.setValue(150)
        self.sp_dpi.setSuffix(" DPI")
        f.addRow("해상도", self.sp_dpi)
        self.cb_fmt = QComboBox()
        self.cb_fmt.addItems(["PNG", "JPG", "WEBP"])
        f.addRow("형식", self.cb_fmt)
        self.sp_q = QSpinBox()
        self.sp_q.setRange(10, 100)
        self.sp_q.setValue(90)
        f.addRow("품질(JPG/WEBP)", self.sp_q)
        row, self.ed_out = dir_row(self, "비우면 PDF 폴더\\PDF파일명 폴더")
        f.addRow("저장 위치", row)
        self.lb_mode = _caption("")
        self.extra_box.addWidget(self.lb_mode)
        self.cb_mode.currentIndexChanged.connect(self._mode_ui)
        self._mode_ui()

    @property
    def single(self):
        return self.cb_mode.currentIndex() == 1

    def _mode_ui(self):
        if self.single:
            self.ed_out.setPlaceholderText("비우면 PDF 와 같은 폴더")
            self.lb_mode.setText("PDF 하나당 이미지 1장(파일명_전체)으로 저장합니다. 페이지 사이에 옅은 구분 간격이 들어가고, "
                                 "너무 길면(JPG 65500px·WEBP 16383px 초과) 해상도를 자동으로 낮춥니다.")
        else:
            self.ed_out.setPlaceholderText("비우면 PDF 폴더\\PDF파일명 폴더")
            self.lb_mode.setText("")

    def run(self):
        paths = self.lst.paths()
        if not paths:
            QMessageBox.information(self, APP_NAME, "PDF 파일을 추가하세요.")
            return
        fmt, dpi, q = self.cb_fmt.currentText(), self.sp_dpi.value(), self.sp_q.value()
        single = self.single
        txt = self.ed_pages.text().strip()
        # 암호 입력·범위 검사는 UI 스레드에서 먼저 처리
        jobs, errs, last = [], [], ""
        for p in paths:
            name = os.path.basename(p)
            try:
                doc = pdf_ops.open_pdf(p, ask_password(self), bad_password_msg="암호 오류")
                n = doc.page_count
                pages = [i for g in parse_ranges(txt, n) for i in g] if txt else list(range(n))
                base = os.path.splitext(name)[0]
                out = self.ed_out.text().strip() or (os.path.dirname(p) if single else os.path.join(os.path.dirname(p), base))
                last = out
                jobs.append(PdfImageJob(doc, name, pages, out, base, max(3, len(str(n)))))
            except Exception as ex:
                errs.append(f"{name}: {ex}")
        total, notes = 0, []
        if jobs:
            if single:
                total, e2, notes = run_task(self, "변환 중...", sum(len(j.pages) for j in jobs),
                                            lambda t: pdf_to_single_images(jobs, fmt, dpi, q, task=t))
            else:
                total, e2 = run_task(self, "변환 중...", sum(len(j.pages) for j in jobs),
                                     lambda t: pdf_to_images(jobs, fmt, dpi, q, t))
            errs += e2
        what = f"PDF {total}개를 이미지 1장씩으로" if single else f"이미지 {total}개"
        self.toast(f"{what} 저장 완료", ok=total > 0 or not errs)
        msg = f"{what} 저장 완료" + (f"\n{last}" if last else "") + ("\n\n" + "\n".join(notes) if notes else "")
        QMessageBox.information(self, APP_NAME, msg + _fail_text(errs))


class Img2PdfPanel(_Panel):
    def __init__(self, win=None):
        super().__init__(win, exts=IMG_EXT, icon=48, thumbs=True, extra=True, run_text="PDF 만들기",
                         file_filter=IMG_FILTER, dialog_title="이미지 추가", folder=True)
        f = self.form
        self.cb_mode = QComboBox()
        self.cb_mode.addItems(["전체를 PDF 1개로", "이미지마다 PDF 1개"])
        f.addRow("만들기", self.cb_mode)
        self.cb_size = QComboBox()
        self.cb_size.addItems(["A4 (자동 방향)", "A4 세로", "A4 가로", "Letter (자동 방향)", "이미지 원본 크기"])
        f.addRow("페이지 크기", self.cb_size)
        self.sp_margin = QSpinBox()
        self.sp_margin.setRange(0, 50)
        self.sp_margin.setValue(5)
        self.sp_margin.setSuffix(" mm")
        f.addRow("여백", self.sp_margin)
        self.sp_q = QSpinBox()
        self.sp_q.setRange(10, 100)
        self.sp_q.setValue(85)
        f.addRow("이미지 품질", self.sp_q)
        self.extra_box.addWidget(_caption("목록 순서대로 페이지가 만들어집니다. ▲▼·이름순으로 정렬하세요."))

    def run(self):
        paths = self.lst.paths()
        if not paths:
            QMessageBox.information(self, APP_NAME, "이미지를 추가하세요.")
            return
        args = (self.cb_size.currentText(), self.sp_margin.value(), self.sp_q.value())
        if self.cb_mode.currentIndex() == 1:
            d = QFileDialog.getExistingDirectory(self, "저장 폴더", os.path.dirname(paths[0]))
            if not d:
                return
            ok, errs = run_task(self, "PDF 생성 중...", len(paths),
                                lambda t: images_to_pdf_each(paths, d, *args, task=t))
            self.toast(f"PDF {ok}개 생성 완료", ok=ok > 0)
            QMessageBox.information(self, APP_NAME, f"PDF {ok}개 생성 완료\n{d}" + _fail_text(errs))
            return
        first = os.path.splitext(os.path.basename(paths[0]))[0]
        dst, _ = QFileDialog.getSaveFileName(self, "PDF 저장",
                                             os.path.join(os.path.dirname(paths[0]), f"{first}.pdf"), PDF_FILTER)
        if not dst:
            return
        dst = with_ext(dst, '.pdf')
        n, errs = run_task(self, "PDF 생성 중...", len(paths),
                           lambda t: images_to_pdf_single(paths, dst, *args, task=t))
        if n == 0:
            QMessageBox.warning(self, APP_NAME, "생성된 페이지가 없습니다.\n" + "\n".join(errs[:10]))
            return
        self.toast(f"{n}페이지 PDF 생성 완료")
        msg = f"{n}페이지 PDF 생성 완료 ({human(os.path.getsize(dst))})\n{dst}"
        QMessageBox.information(self, APP_NAME, msg + _fail_text(errs))


class Office2PdfPanel(_Panel):
    def __init__(self, win=None):
        super().__init__(win, exts=OFFICE_EXT, icon=32, thumbs=False, extra=True, run_text="PDF로 변환",
                         file_filter=OFFICE_FILTER, dialog_title="문서 추가", folder=True)
        self.engines = None
        f = self.form
        self.cb_fit = QCheckBox("Excel: 시트 가로폭을 1페이지에 맞춤")
        self.cb_fit.setChecked(True)
        f.addRow(self.cb_fit)
        self.cb_merge = QCheckBox("변환 후 PDF 1개로 합치기 (목록 순서)")
        f.addRow(self.cb_merge)
        row, self.ed_out = dir_row(self, "비우면 원본 폴더\\변환 폴더")
        f.addRow("저장 위치", row)
        self.lb_eng = _caption("변환 프로그램 확인 중...")
        self.extra_box.addWidget(self.lb_eng)
        self.extra_box.addWidget(_caption("PC에 설치된 Office·한글·LibreOffice로 변환합니다. "
                                          "Office가 없으면 무료 LibreOffice 설치 시 사용 가능 (HWP는 한글 필수)"))

    def showEvent(self, e):
        super().showEvent(e)
        if self.engines is None:
            self.engines = detect_engines()
            e_ = self.engines

            def yn(b):
                return "✓" if b else "–"
            self.lb_eng.setText(
                f"Excel {yn(e_['excel'])}   Word {yn(e_['word'])}   PowerPoint {yn(e_['ppt'])}   "
                f"한글 {yn(e_['hwp'])}   LibreOffice {yn(bool(e_['soffice']))}")

    def run(self):
        paths = self.lst.paths()
        if not paths:
            QMessageBox.information(self, APP_NAME, "변환할 문서를 추가하세요.")
            return
        merged_dst = None
        if self.cb_merge.isChecked():
            first = os.path.splitext(os.path.basename(paths[0]))[0]
            merged_dst, _ = QFileDialog.getSaveFileName(self, "합친 PDF 저장",
                                                        os.path.join(os.path.dirname(paths[0]), f"{first}_합본.pdf"),
                                                        PDF_FILTER)
            if not merged_dst:
                return
            merged_dst = with_ext(merged_dst, '.pdf')
        engines = self.engines or detect_engines()
        fit, out_dir = self.cb_fit.isChecked(), self.ed_out.text().strip()
        try:
            outs, errs = run_task(self, "문서 변환 중...", len(paths),
                                  lambda t: office_to_pdf(paths, engines, fit, out_dir, merged_dst, t),
                                  busy_cursor=True)
        except Exception as ex:
            QMessageBox.warning(self, APP_NAME, f"변환 실패\n{ex}")
            return
        if merged_dst and outs:
            msg = f"{len(outs)}개 문서 → PDF 1개 합치기 완료\n{merged_dst}"
        else:
            msg = f"PDF {len(outs)}개 변환 완료" + (f"\n{os.path.dirname(outs[-1])}" if outs else "")
        self.toast(msg.splitlines()[0], ok=bool(outs))
        QMessageBox.information(self, APP_NAME, msg + _fail_text(errs))


class Pdf2DocPanel(_Panel):
    def __init__(self, win=None):
        super().__init__(win, exts=PDF_EXT, icon=32, thumbs=False, extra=False, run_text="문서로 변환",
                         file_filter=PDF_FILTER, dialog_title="PDF 선택")
        f = self.form
        self.cb_t = QComboBox()
        self.cb_t.addItems([t[0] for t in PDF_DOC_TARGETS])
        f.addRow("변환 형식", self.cb_t)
        row, self.ed_out = dir_row(self, "비우면 원본 폴더\\변환 폴더")
        f.addRow("저장 위치", row)
        self.extra_box.addWidget(_caption("텍스트가 있는 PDF만 가능 (스캔 이미지 PDF는 내용 추출 불가)"))
        self.extra_box.addWidget(_caption("Excel: 표를 찾아 시트별로 저장, 표가 없으면 텍스트를 줄 단위로 저장"))

    def run(self):
        paths = self.lst.paths()
        if not paths:
            QMessageBox.information(self, APP_NAME, "PDF 파일을 추가하세요.")
            return
        idx, out_dir = self.cb_t.currentIndex(), self.ed_out.text().strip()
        outs, errs = run_task(self, "변환 중...", len(paths),
                              lambda t: pdfs_to_docs(paths, idx, out_dir, t), busy_cursor=True)
        self.toast(f"{len(outs)}개 변환 완료", ok=bool(outs))
        msg = f"{len(outs)}개 변환 완료" + (f"\n{os.path.dirname(outs[-1])}" if outs else "")
        QMessageBox.information(self, APP_NAME, msg + _fail_text(errs))


KINDS = [("conv-pdf-img", "PDF → 이미지", "페이지를 PNG·JPG·WEBP로 저장"),
         ("conv-img-pdf", "이미지 → PDF", "사진 여러 장을 PDF 하나로"),
         ("conv-office-pdf", "문서 → PDF", "Excel·Word·PPT·한글을 PDF로"),
         ("conv-pdf-doc", "PDF → 문서", "Excel(표)·텍스트로 추출")]


class ConvertTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.setObjectName("Page")
        self.win = win
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(12)
        v.addWidget(QLabel("어떤 변환을 할까요?", objectName="H1"))
        v.addWidget(QLabel("①  변환 종류 선택    ›    ②  파일 추가    ›    ③  옵션    ›    ④  실행", objectName="Muted"))
        g = QGridLayout()
        g.setSpacing(14)
        self.cards = []
        for i, (ic, t, d) in enumerate(KINDS):
            c = ChoiceCard(ic, t, d)
            c.clicked.connect(lambda i=i: self.select(i))
            g.addWidget(c, 0, i)
            self.cards.append(c)
        v.addLayout(g)

        self.pdf2img = Pdf2ImgPanel(win)
        self.img2pdf = Img2PdfPanel(win)
        self.office2pdf = Office2PdfPanel(win)
        self.pdf2doc = Pdf2DocPanel(win)
        self.panels = [self.pdf2img, self.img2pdf, self.office2pdf, self.pdf2doc]
        self.stack = QStackedWidget(objectName="Pages")
        for p in self.panels:
            p.lst.countChanged.connect(lambda _n: self._status())
            self.stack.addWidget(p)
        v.addWidget(self.stack, 1)
        self.select(0)

    def select(self, i):
        for k, c in enumerate(self.cards):
            c.set_selected(k == i)
        self.stack.setCurrentIndex(i)
        self._status()

    def current_index(self):
        return self.stack.currentIndex()

    def status_text(self):
        i = self.stack.currentIndex()
        return f"변환: {KINDS[i][1]}    ·    파일 {self.panels[i].lst.count()}개"

    def _status(self):
        if self.win.stack.currentWidget() is self:
            self.win.set_doc_info(self.status_text())
