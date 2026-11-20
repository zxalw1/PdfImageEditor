# -*- coding: utf-8 -*-
"""자가진단: 빌드된 exe 안에서 핵심 기능이 실제로 동작하는지 확인
실행: PdfImageEditor.exe --selftest 결과.json   (종료 코드 0 = 전부 통과)
※ 빌드 시 모듈을 빼서 용량을 줄였으므로, 빠진 것 때문에 깨지는 기능이 없는지 이걸로 검증한다.
"""
import io
import json
import os
import tempfile
import time
import traceback


def run(out_path):
    from PySide6.QtGui import QImageReader, QPixmap
    from PySide6.QtWidgets import QApplication
    from app import VERSION
    from app.core.utils import fitz, korean_font, resource_path
    results = []

    def check(name, fn):
        t = time.time()
        try:
            detail = fn()
            results.append({"name": name, "ok": True, "detail": str(detail or ""), "sec": round(time.time() - t, 2)})
        except Exception:                      # noqa: BLE001
            results.append({"name": name, "ok": False, "detail": traceback.format_exc()[-800:]})

    app = QApplication.instance()
    work = tempfile.mkdtemp(prefix="pie_selftest_")
    kf = korean_font()
    FK = dict(fontname="kf", fontfile=kf) if kf else dict(fontname="helv")   # CI 등 한글 글꼴 없는 환경
    T = (lambda ko, en: ko) if kf else (lambda ko, en: en)

    def formats():
        f = {bytes(x).decode() for x in QImageReader.supportedImageFormats()}
        need = {"svg", "jpg", "png", "ico"}
        assert need <= f, f"없음: {need - f}"
        return ",".join(sorted(f))
    check("Qt 이미지 형식(svg/jpg/png/ico)", formats)

    def icons():
        from app.ui import theme
        pm = theme.svg_pixmap("save", "#000000", 24)
        assert not pm.isNull()
        chk = theme._qss_svg("check", "#FFFFFF")
        assert not QPixmap(chk).isNull()
        n = len(os.listdir(resource_path("app", "assets", "icons")))
        assert n >= 50
        return f"아이콘 {n}개"
    check("아이콘·스타일 이미지", icons)

    def window():
        from app.ui.main_window import MainWindow
        w = MainWindow()
        w.show()
        app.processEvents()
        src = os.path.join(work, "t.pdf")
        d = fitz.open()
        for i in range(3):
            d.new_page().insert_text((72, 100), T(f"자가진단 {i + 1} 원본", f"selftest {i + 1}"), fontsize=16, **FK)
        d.save(src)
        w.pdf.load(src)
        app.processEvents()
        assert w.pdf.doc.page_count == 3 and not w.view_pixmap_null()
        w.pdf.set_continuous(True)
        app.processEvents()
        w.pdf.set_continuous(False)
        w.pdf.modified = False
        w.close()
        return "창·미리보기·연속보기"
    from app.ui.main_window import MainWindow
    MainWindow.view_pixmap_null = lambda self: self.pdf.view.pixmap() is None or self.pdf.view.pixmap().isNull()
    check("메인 창 + PDF 열기", window)

    def text_edit():
        from app.core import text_edit as te, pdf_ops
        d = fitz.open()
        p = d.new_page()
        p.insert_text((72, 100), T("수정 전 글자", "before"), fontsize=14, **FK)
        u = te.text_units(p)[0]
        te.replace_unit(d, p, u, T("수정 후 한글 글자", "after edit"), kf)
        data = pdf_ops.doc_to_bytes(d)              # 글꼴 서브셋(fontTools)
        r = fitz.open(stream=data, filetype="pdf")
        assert T("수정 후 한글 글자", "after edit") in r[0].get_text() and len(data) < 2_000_000
        return f"{len(data) // 1024}KB"
    check("글자 수정 + 글꼴 서브셋", text_edit)

    def annots_deco_compress():
        from app.core import overlay as ov, page_deco as pd, compress as cp
        from PIL import Image
        d = fitz.open()
        p = d.new_page()
        p.insert_text((72, 100), T("주석 시험", "annot"), fontsize=14, **FK)
        b = io.BytesIO()
        Image.effect_noise((1600, 1200), 50).convert("RGB").save(b, "JPEG", quality=95)
        p.insert_image(fitz.Rect(72, 200, 300, 370), stream=b.getvalue())
        L = ov.ObjectLayer()
        L.add_shape(p.xref, "highlight", (60, 80), (300, 110))
        L.add_shape(p.xref, "note", (400, 80), text="메모")
        L.flatten(d)
        pd.decorate(d, pd.DecoOptions(numbers=pd.NumberOpts(True), wm=pd.WatermarkOpts(True, text=T("대외비", "CONFIDENTIAL"))))
        res = cp.compress(d, 96, 60)
        assert len(list(d[0].annots())) == 2 and T("대외비", "CONFIDENTIAL") in d[0].get_text() and res.after < res.before
        return f"압축 {res.before // 1024}KB→{res.after // 1024}KB"
    check("주석·페이지꾸미기·용량줄이기", annots_deco_compress)

    def images():
        from app.core.image_ops import open_image, save_image
        im = open_image(resource_path("app", "assets", "selftest", "sample.heic"))
        assert im.size == (64, 48)
        for fmt in ("JPG", "PNG", "WEBP", "ICO", "TIFF"):
            save_image(im, os.path.join(work, "o." + fmt.lower()), fmt, 80)
        return "HEIC 읽기, JPG/PNG/WEBP/ICO/TIFF 저장"
    check("사진 변환(HEIC 포함)", images)

    def convert():
        from app.core import convert_ops as cv
        src = os.path.join(work, "t.pdf")
        outs, errs = cv.pdfs_to_docs([src], 0, os.path.join(work, "x"))
        outs2, errs2 = cv.pdfs_to_docs([src], 1, os.path.join(work, "x"))
        assert outs and outs2 and not errs and not errs2
        n, e = cv.images_to_pdf_single([resource_path("app", "assets", "selftest", "sample.heic")],
                                       os.path.join(work, "i.pdf"), "A4 (자동 방향)", 5, 80)
        assert n == 1
        return "PDF→Excel·텍스트, 이미지→PDF"
    check("변환(Excel·텍스트·이미지)", convert)

    def office():
        from app.core.office_com import detect_engines
        from app.core import convert_ops as cv
        e = detect_engines()
        if not e["excel"]:
            return f"Excel 없음(건너뜀) {e}"
        from openpyxl import Workbook
        wb = Workbook()
        wb.active.append(["항목", 1])
        x = os.path.join(work, "a.xlsx")
        wb.save(x)
        outs, errs = cv.office_to_pdf([x], e, True, os.path.join(work, "o"))
        assert outs and not errs, errs
        return "Excel→PDF (COM)"
    check("Office COM 변환", office)

    def update():
        import hashlib
        from app.core import updater as up
        payload = b"MZ-selftest" * 100
        exe = os.path.join(work, "PdfImageEditor_Setup_v99.0.0.exe")
        with open(exe, "wb") as f:
            f.write(payload)
        j = os.path.join(work, "update.json")
        with open(j, "w", encoding="utf-8") as f:
            json.dump({"version": "99.0.0", "downloadUrl": os.path.basename(exe),
                       "sha256": hashlib.sha256(payload).hexdigest(), "mandatory": False, "releaseNotes": "t"}, f)
        info = up.check(j, VERSION)
        p = up.download(info, os.path.join(work, "dl"))
        assert info and up.sha256_file(p) == info.sha256
        return "로컬 JSON 확인·다운로드·sha256"
    check("자동 업데이트(로컬)", update)

    ok = all(r["ok"] for r in results)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"version": VERSION, "ok": ok, "results": results}, f, ensure_ascii=False, indent=1)
    return 0 if ok else 1
