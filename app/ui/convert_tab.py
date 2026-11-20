# -*- coding: utf-8 -*-
"""변환 탭 (PDF→이미지 / 이미지→PDF / Office→PDF / PDF→문서)"""
import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLineEdit, QSpinBox, QComboBox, QCheckBox, QLabel,
    QTabWidget, QFileDialog, QMessageBox,
)

from app import APP_NAME
from app.core.utils import IMG_EXT, PDF_EXT, IMG_FILTER, PDF_FILTER, parse_ranges, human, with_ext
from app.core import pdf_ops
from app.core.convert_ops import (
    PdfImageJob, pdf_to_images, images_to_pdf_each, images_to_pdf_single, office_to_pdf,
    pdfs_to_docs, PDF_DOC_TARGETS,
)
from app.core.office_com import OFFICE_EXT, OFFICE_FILTER, detect_engines
from app.ui.widgets import FileList, dir_row, list_bar, run_button
from app.ui.dialogs import ask_password
from app.ui.workers import run_task


def _fail_text(errs, head="\n\n실패:\n"):
    return head + "\n".join(errs[:10]) if errs else ""


class Pdf2ImgPanel(QWidget):
    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        self.lst = FileList(PDF_EXT, 32, thumbs=False)
        self.lst.filesDropped.connect(self.lst.add_files)
        v.addLayout(list_bar(self.lst, self.add, extra=False))
        v.addWidget(self.lst)
        f = QFormLayout()
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
        f.addRow("출력 폴더", row)
        v.addLayout(f)
        v.addWidget(run_button("PDF → 이미지 변환", self.run))

    def add(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "PDF 선택", "", PDF_FILTER)
        if fs:
            self.lst.add_files(fs)

    def run(self):
        paths = self.lst.paths()
        if not paths:
            QMessageBox.information(self, APP_NAME, "PDF 파일을 추가하세요.")
            return
        fmt, dpi, q = self.cb_fmt.currentText(), self.sp_dpi.value(), self.sp_q.value()
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
                out = self.ed_out.text().strip() or os.path.join(os.path.dirname(p), base)
                last = out
                jobs.append(PdfImageJob(doc, name, pages, out, base, max(3, len(str(n)))))
            except Exception as ex:
                errs.append(f"{name}: {ex}")
        total = 0
        if jobs:
            total, e2 = run_task(self, "변환 중...", sum(len(j.pages) for j in jobs),
                                 lambda t: pdf_to_images(jobs, fmt, dpi, q, t))
            errs += e2
        msg = f"이미지 {total}개 저장 완료" + (f"\n{last}" if last else "")
        QMessageBox.information(self, APP_NAME, msg + _fail_text(errs))


class Img2PdfPanel(QWidget):
    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        self.lst = FileList(IMG_EXT, 48)
        self.lst.filesDropped.connect(self.lst.add_files)
        v.addLayout(list_bar(self.lst, self.add))
        v.addWidget(self.lst)
        f = QFormLayout()
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
        v.addLayout(f)
        v.addWidget(run_button("이미지 → PDF 만들기", self.run))

    def add(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "이미지 추가", "", IMG_FILTER)
        if fs:
            self.lst.add_files(fs)

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
        msg = f"{n}페이지 PDF 생성 완료 ({human(os.path.getsize(dst))})\n{dst}"
        QMessageBox.information(self, APP_NAME, msg + _fail_text(errs))


class Office2PdfPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.engines = None
        v = QVBoxLayout(self)
        self.lb_eng = QLabel("변환 프로그램 확인 중...")
        self.lb_eng.setWordWrap(True)
        self.lb_eng.setStyleSheet("background:#f6f8fb;border:1px solid #d6dde8;padding:6px;")
        v.addWidget(self.lb_eng)
        self.lst = FileList(OFFICE_EXT, 32, thumbs=False)
        self.lst.filesDropped.connect(self.lst.add_files)
        v.addLayout(list_bar(self.lst, self.add))
        v.addWidget(self.lst)
        f = QFormLayout()
        self.cb_fit = QCheckBox("Excel: 시트 가로폭을 1페이지에 맞춤")
        self.cb_fit.setChecked(True)
        f.addRow(self.cb_fit)
        self.cb_merge = QCheckBox("변환 후 PDF 1개로 합치기 (목록 순서)")
        f.addRow(self.cb_merge)
        row, self.ed_out = dir_row(self, "비우면 원본 폴더\\변환 폴더")
        f.addRow("출력 폴더", row)
        v.addLayout(f)
        v.addWidget(run_button("문서 → PDF 변환", self.run))

    def showEvent(self, e):
        super().showEvent(e)
        if self.engines is None:
            self.engines = detect_engines()
            e_ = self.engines

            def yn(b):
                return "✔" if b else "✘"
            self.lb_eng.setText(
                f"MS Excel {yn(e_['excel'])}   MS Word {yn(e_['word'])}   MS PowerPoint {yn(e_['ppt'])}   "
                f"한글(HWP) {yn(e_['hwp'])}   LibreOffice {yn(bool(e_['soffice']))}\n"
                "※ PC에 설치된 Office/한글/LibreOffice로 변환합니다. Office가 없으면 무료 LibreOffice 설치 시 사용 가능 (HWP는 한글 필수)")

    def add(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "문서 추가", "", OFFICE_FILTER)
        if fs:
            self.lst.add_files(fs)

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
        QMessageBox.information(self, APP_NAME, msg + _fail_text(errs))


class Pdf2DocPanel(QWidget):
    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        self.lst = FileList(PDF_EXT, 32, thumbs=False)
        self.lst.filesDropped.connect(self.lst.add_files)
        v.addLayout(list_bar(self.lst, self.add, extra=False))
        v.addWidget(self.lst)
        f = QFormLayout()
        self.cb_t = QComboBox()
        self.cb_t.addItems([t[0] for t in PDF_DOC_TARGETS])
        f.addRow("변환 형식", self.cb_t)
        f.addRow(QLabel("※ 텍스트가 있는 PDF만 가능 (스캔 이미지 PDF는 내용 추출 불가)\n"
                        "※ Excel 변환: 표를 찾아 시트별로 저장, 표가 없으면 텍스트를 줄 단위로 저장"))
        row, self.ed_out = dir_row(self, "비우면 원본 폴더\\변환 폴더")
        f.addRow("출력 폴더", row)
        v.addLayout(f)
        v.addWidget(run_button("PDF → 문서 변환", self.run))

    def add(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "PDF 선택", "", PDF_FILTER)
        if fs:
            self.lst.add_files(fs)

    def run(self):
        paths = self.lst.paths()
        if not paths:
            QMessageBox.information(self, APP_NAME, "PDF 파일을 추가하세요.")
            return
        idx, out_dir = self.cb_t.currentIndex(), self.ed_out.text().strip()
        outs, errs = run_task(self, "변환 중...", len(paths),
                              lambda t: pdfs_to_docs(paths, idx, out_dir, t), busy_cursor=True)
        msg = f"{len(outs)}개 변환 완료" + (f"\n{os.path.dirname(outs[-1])}" if outs else "")
        QMessageBox.information(self, APP_NAME, msg + _fail_text(errs))


class ConvertTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        v = QVBoxLayout(self)
        v.setContentsMargins(4, 4, 4, 4)
        t = QTabWidget()
        t.setDocumentMode(True)
        self.pdf2img = Pdf2ImgPanel()
        self.img2pdf = Img2PdfPanel()
        self.office2pdf = Office2PdfPanel()
        self.pdf2doc = Pdf2DocPanel()
        t.addTab(self.pdf2img, "PDF → 이미지")
        t.addTab(self.img2pdf, "이미지 → PDF")
        t.addTab(self.office2pdf, "Excel·Word·PPT·한글 → PDF")
        t.addTab(self.pdf2doc, "PDF → Word·Excel·텍스트")
        v.addWidget(t)
