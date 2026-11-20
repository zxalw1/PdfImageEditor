# -*- coding: utf-8 -*-
"""업데이트 정보 JSON 만들기 (설치파일 sha256 자동 계산)
사용: python tools\\make_update_json.py dist\\PdfImageEditor_Setup_v1.9.0.exe [--url 다운로드주소] [--notes 파일|문구] [--mandatory]

- --url 을 생략하면 downloadUrl 은 파일 이름(상대 경로) → update.json 과 같은 곳(공유폴더·GitHub 릴리스)에 두면 됨
- 결과: 설치파일 옆 update.json
"""
import argparse
import hashlib
import json
import os
import re
import sys


for _s in (sys.stdout, sys.stderr):      # CI(영문 Windows) 콘솔에서도 한글 출력
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("setup")
    ap.add_argument("--url", default="")
    ap.add_argument("--notes", default="")
    ap.add_argument("--mandatory", action="store_true")
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)
    m = re.search(r"_v(\d+(?:\.\d+)+)\.exe$", os.path.basename(a.setup))
    if not m:
        sys.exit("파일 이름에서 버전을 찾을 수 없습니다 (예: PdfImageEditor_Setup_v1.9.0.exe)")
    notes = a.notes
    if notes and os.path.isfile(notes):
        with open(notes, encoding="utf-8-sig") as f:
            notes = f.read().strip()
    info = {"version": m.group(1),
            "downloadUrl": a.url or os.path.basename(a.setup),
            "sha256": sha256(a.setup),
            "mandatory": a.mandatory,
            "releaseNotes": notes}
    out = a.out or os.path.join(os.path.dirname(os.path.abspath(a.setup)), "update.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    print(out)
    print(json.dumps(info, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
