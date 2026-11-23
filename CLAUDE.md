# PDF·이미지 통합 편집기 (PdfImageEditor)

## 개요
- Windows 데스크톱 프로그램. PDF 편집 + 사진 편집 + 문서 변환 통합
- 사내(씨앤씨인터내셔널) 직원들에게 **설치파일(Setup.exe)로 배포** → 설치 시 바탕화면·시작메뉴 아이콘 생성
- 사용자는 비개발 실무자 → UI는 한국어, 버튼만 보고 바로 쓸 수 있게

## 작업 규칙 (반드시 준수)
- 답변: 결론 첫 줄 → 필요한 내용만. 설명 최소화, 코드 위주
- 코드 수정 시 부분 패치 설명 금지. 파일은 직접 수정하고, 사용자에게 보여줄 땐 완성본 기준
- 작업 완료 보고 전 아래 "검증 체크리스트" 전부 수행 후 결과 표로 보고
- 기능 추가/수정마다 `VERSION` 올림 (1.0.0 → 1.0.1 버그수정 / 1.1.0 기능추가)
- 커밋 메시지 한국어, 기능 단위로 커밋

## 환경
- Windows x64, Python 3.13 (`py` 런처), 가상환경 `.venv`
- PC에 MS Office 설치됨, AhnLab V3 설치됨 (PyInstaller exe 오탐 가능성 주의)
- 스택: PySide6 / PyMuPDF(`import pymupdf as fitz`) / Pillow / pillow-heif / openpyxl / pdf2docx / pywin32 / PyInstaller / Inno Setup 6

## 현재 상태 (v1.10.0) — 작업목록 1~5번 완료
- v1.10.0: 사진 이어붙이기(image_ops.stitch_* , dialogs.StitchDialog, 형식별 최대 변 FORMAT_MAX_SIDE), PDF→이미지 "전체 1장"(convert_ops.pdf_to_single_images), Qt 한국어 번역(theme.install_korean, 빌드에 qtbase_ko·qt_ko 만 남김, 저장 확인 창은 "저장 안 함" 직접 지정), 툴바 보기 영역 ViewBox 로 묶음
- 주의: Git Bash 로 파이썬 스크립트에 한글을 넘기면 cp949 로 깨짐 → 한글 포함 수정은 Edit 도구로
- v1.9.0: 자동 업데이트(app/core/updater.py, app/ui/updates.py, UPDATE_URL 또는 update_url.txt), PDF→Word(pdf2docx) 제거, 빌드는 tools/build_exe.py(모듈 제외·파일 정리·exe --selftest), tools/make_update_json.py, installer [InstallDelete] _internal + 조용한 설치 후 자동 재실행
- 배포(v1.9.3~): 저장소 https://github.com/zxalw1/PdfImageEditor (공개). UPDATE_URL = releases/latest/download/update.json
  새 버전 내는 법: 버전 올림(app/__init__.py·version_info.txt·installer.iss·build.bat) → release_notes.txt 수정 → 커밋 → `git push origin main` → `git tag vX.Y.Z` → `git push origin vX.Y.Z`
  → Actions 가 테스트·빌드·자가진단·설치파일·update.json·릴리스까지 자동. (예전 태그 v1.0.0~v1.9.2 는 로컬에만, 올리지 말 것: 태그마다 빌드 실행됨)
  설치된 앱은 시작 2.5초 뒤 확인 → 안내 → 받기·sha256 → /AUTOUPDATE=1 조용히 재설치 → 자동 재실행 (설치본 E2E 확인 완료)
  CI 콘솔은 cp1252 → tools 스크립트는 stdout UTF-8 고정, workflow 에 PYTHONUTF8=1
작업목록 4번 (v1.3.0~v1.8.0):
- 주석(v1.4): ObjectLayer 에 도형 종류 추가(highlight/underline/rect/arrow/note), 저장 시 실제 PDF 주석으로. 형광펜·밑줄은 글자 줄에 맞춤
- 페이지 꾸미기(v1.5): `app/core/page_deco.py` 페이지 번호·머리글/바닥글({page}{total}{date}{file})·워터마크(글자/이미지), 미리보기 대화상자
- 페이지 끌어오기(v1.6): PageList 가 놓은 위치를 직접 계산(movedTo/filesDroppedAt/pagesDroppedAt), 다른 PDF 페이지 창(PagePickerWindow)
- 용량 줄이기(v1.7): `app/core/compress.py` (MuPDF rewrite_images, 정수 배율 축소라 결과 DPI 는 목표의 ~1.2배까지)
- 보기(v1.8): Ctrl+휠 확대/축소, 연속 스크롤(페이지별 PageView, 보이는 것만 렌더, `pdf_tab.view` = 현재 페이지 뷰 속성)
- 툴바 폭이 1320px 에 꽉 참 → 새 버튼은 "더보기"/"삽입" 메뉴로
이미지·서명·도장 삽입(작업목록 4번 중 1번 + 4번의 객체 관리 일부): `app/core/overlay.py` ObjectLayer
(페이지 xref 기준·회전 후 좌표, 저장/추출/분할 시 flatten, 회전하는 페이지는 먼저 합침), 실행취소는 (PDF bytes, 레이어) 쌍.
UI: 툴바 "삽입" 메뉴(이미지 / 도장·서명 이미지 흰 배경 제거 / 서명 그리기 / 저장된 서명), 클릭=기본 크기·드래그=크기 지정,
선택 후 끌어 이동·모서리 크기조절(Shift 비율 무시)·Delete·오른쪽 클릭 메뉴. 저장된 서명: `%LOCALAPPDATA%\PdfImageEditor\signatures`

기존 텍스트 직접 수정(작업목록 3번 완료): `app/core/text_edit.py` (줄/문단 단위 추출, 원본 글꼴 재사용→기본14→맑은 고딕(굵게 유지) 대체,
배경·표 선 유지하며 글자만 지움), UI는 PDF 편집 툴바 "글자 수정"(Ctrl+E, ▾ 줄/문단). 찾아 바꾸기도 같은 엔진으로 줄 단위 재작성.
저장 시 글꼴 서브셋(사본에서 수행) → 맑은 고딕 전체(13MB) 내장 방지.
※ 서브셋 글꼴(대부분의 실제 PDF)은 유니코드 대응표가 없어 원본 글꼴 재사용 불가 → 맑은 고딕으로 대체됨(정상 동작)

진입점 `main.py` + `app/` 패키지 (작업목록 1번 구조, v1.0.0 단일 파일은 git 태그 `v1.0.0`).
`app/core`는 Qt 없음(pytest 대상), 무거운 작업은 `app/ui/workers.py`의 `run_task()`(QThread+진행률/취소).
UI(작업목록 2번 완료): `app/ui/theme.py` 색 토큰(LIGHT/DARK)·QSS·`bind_icon()`(테마 전환 시 자동 재착색), 다크모드 설정은 QSettings 저장.
아이콘은 `tools/make_icons.py` → `app/assets/icons/*.svg`, 앱 아이콘은 `tools/make_app_icon.py` → `app/assets/app.ico`.
좌측 내비게이션 3개 화면:
1. **PDF 편집**: 열기·병합(PDF/이미지)·저장, 회전, 페이지 삭제·순서변경(드래그/▲▼)·빈 페이지, 선택 추출, 분할(페이지별/N페이지/범위), 텍스트 추가(클릭), 영역 지우기(드래그 → redact), 찾아 바꾸기, 실행취소 15단계, 암호 PDF
2. **사진 편집**: 일괄 형식변환(JPG/PNG/WEBP/BMP/TIFF/GIF/ICO), 크기(%/가로/세로/지정), 품질, 목표 용량(KB) 이하 압축, 회전·반전, EXIF 방향 보정, HEIC
3. **변환** (하위 탭 4개): PDF→이미지 / 이미지→PDF / Excel·Word·PPT·한글→PDF (MS Office·한글 COM 우선, 없으면 LibreOffice) / PDF→Word·Excel(표 추출)·텍스트

빌드: `build.bat` → pytest → PyInstaller(onedir, --windowed, `main.py`) → `installer.iss`(Inno Setup, 사용자 폴더 설치·관리자 권한 불필요) → `dist\PdfImageEditor_Setup_v*.exe`
크래시 로그: `%LOCALAPPDATA%\PdfImageEditor\error.log`, `crash.log`

## 해결된 이슈
- exe 실행 안 됨 → `build\` 폴더의 중간 산출물을 실행한 것이 원인. 실행 파일은 반드시 `dist\PdfImageEditor\PdfImageEditor.exe`
  - `build.bat` 완료 메시지에 실행 경로(절대경로) 표시, `build\` 폴더는 빌드 후 자동 삭제 (v1.0.1 반영)

## 작업 목록
### 1. 코드 구조 분리
```
main.py
app/
  core/   pdf_ops.py  image_ops.py  convert_ops.py  office_com.py  utils.py
  ui/     main_window.py  pdf_tab.py  image_tab.py  convert_tab.py  widgets.py  dialogs.py  theme.py
  assets/ icons/*.svg  app.ico
build.bat  installer.iss  version_info.txt  requirements.txt
tests/    (core 함수 단위 테스트, pytest)
```
- core는 Qt 의존 없이 순수 함수로 → 테스트 가능하게
- 무거운 작업(변환, 일괄처리, 분할)은 `QThread` 워커 + 진행률/취소. UI 멈춤 금지

### 2. UI/아이콘 전면 리디자인 — 모던·심플
- 톤: 밝은 배경(#F7F8FA), 흰 카드, 라운드 8px, 얇은 구분선, 그림자 최소, 포인트 컬러 1개(파랑 #2563EB)
- 폰트: 맑은 고딕(Pretendard 있으면 우선), 본문 10pt
- 아이콘: **직접 만든 단색 라인 SVG**(24px, stroke 1.75, 라운드 캡) 세트를 `assets/icons`에 두고 테마 색으로 칠해서 사용. 외부 아이콘 폰트·저작권 있는 아이콘 사용 금지
- 상단 툴바 → 아이콘+짧은 라벨, 기능 그룹별 구분(파일 / 페이지 / 편집 / 보기). 자주 안 쓰는 기능은 "더보기" 메뉴
- 좌측 세로 내비게이션(PDF 편집 / 사진 편집 / 변환)으로 탭 대체 검토
- 빈 화면: 큰 드롭존("파일을 끌어다 놓거나 클릭해서 열기")
- 변환 탭: 변환 종류를 카드형 그리드로 선택 → 파일 목록 → 옵션 → 실행 흐름
- 하단 상태바: 파일명·페이지·배율·작업 결과 토스트
- 다크모드 토글 (선택)
- 앱 아이콘(app.ico)도 새 디자인에 맞게 심플하게 재제작 (16~256px 멀티사이즈)

### 3. PDF 기존 텍스트 직접 수정 (핵심 기능, 현재 없음)
- "텍스트 수정" 모드: 페이지 위 마우스 오버 시 텍스트 span 테두리 표시 → 클릭하면 그 자리에 편집 박스(기존 글자 채워진 상태)
- 확정 시: 원래 span 영역 redact(배경 흰색 or 주변색) → 같은 위치·크기·색상으로 새 텍스트 삽입
- `page.get_text("dict")`로 span의 bbox/size/color/font 추출. 원본 폰트가 임베드돼 있으면 재사용 시도, 불가하면 맑은 고딕 대체
- 줄 단위/문단 단위 선택 옵션, 여러 줄 편집 지원
- 스캔 PDF(텍스트 없음)는 "텍스트가 없는 페이지입니다" 안내
- 실행취소 연동

### 4. PDF 편집 추가 기능
- 이미지/서명/도장 삽입(드래그로 위치·크기, 투명 PNG 지원)
- 주석: 형광펜, 밑줄, 메모, 사각형/화살표
- 페이지 번호 넣기, 워터마크(텍스트/이미지), 머리글·바닥글
- 삽입한 객체 선택 후 이동·크기조절·삭제 (편집 레이어를 저장 전까지 객체로 관리)
- 썸네일 다중선택 후 드래그 이동, 다른 PDF에서 페이지 끌어오기
- PDF 용량 줄이기(이미지 재압축 DPI 선택)
- 확대/축소: Ctrl+휠, 페이지 연속 스크롤 보기

### 5. 배포
- 설치파일: Inno Setup, 바탕화면 아이콘, 시작메뉴, 제거 지원, 기존 버전 위 덮어 설치
- 자동 업데이트 확인: 시작 시 JSON 조회 → 새 버전이면 안내 후 Setup 다운로드·실행
  - JSON 구조: `{"version","downloadUrl","sha256","mandatory","releaseNotes"}` (Shorts Recorder와 동일)
  - sha256 검증 후 실행
- 용량 최적화: 불필요한 Qt 모듈 제외, pdf2docx는 선택 설치 옵션 검토
- GitHub Actions(`.github/workflows/build.yml`)로 태그 푸시 시 Setup.exe 자동 빌드

## 검증 체크리스트 (완료 보고 전 필수)
| 항목 | 방법 |
|---|---|
| 소스 실행 | `.venv\Scripts\python.exe main.py` 오류 없음 |
| 단위 테스트 | `pytest` 전체 통과 |
| PDF 기능 | 샘플 PDF로 열기→회전→삭제→순서변경→텍스트 수정→저장→재열기 결과 확인 |
| 한글 | 한글 텍스트 추가/수정 후 깨짐 없음 |
| 사진 | JPG·PNG·HEIC 변환, 목표 용량 이하 확인 |
| 변환 | Excel·Word·PPT→PDF (MS Office), PDF→Word·Excel |
| exe | 빌드 후 **exe 직접 실행**해서 창 뜨는 것 확인 |
| 설치 | Setup.exe 설치 → 바탕화면 아이콘 실행 → 제거까지 확인 |
| 보고 | 버전, 변경 파일, 체크리스트 결과 표 |
