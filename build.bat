@echo off
chcp 65001 >nul
cd /d "%~dp0"
set APPNAME=PdfImageEditor
set VER=1.10.0

if not exist .venv (
    echo [1/6] 가상환경 생성
    py -3 -m venv .venv || python -m venv .venv
)
call .venv\Scripts\activate.bat

echo [2/6] 패키지 설치
python -m pip install --upgrade pip
pip install -r requirements.txt || goto :err

echo [3/6] 단위 테스트
python -m pytest -q tests || goto :err

echo [4/6] EXE 빌드 + 불필요 파일 제거 + 자가진단
rmdir /s /q dist 2>nul
python tools\build_exe.py || goto :err

echo [5/6] 설치 파일 생성
set ISCC=
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if "%ISCC%"=="" (
    echo Inno Setup 6 미설치 - 설치파일 생성 건너뜀
    echo 다운로드: https://jrsoftware.org/isdl.php
    goto :done
)
"%ISCC%" /Q installer.iss || goto :err

echo [6/6] 업데이트 정보(update.json) 생성
if exist release_notes.txt (
    python tools\make_update_json.py dist\%APPNAME%_Setup_v%VER%.exe --notes release_notes.txt || goto :err
) else (
    python tools\make_update_json.py dist\%APPNAME%_Setup_v%VER%.exe || goto :err
)
echo.
echo 배포 파일 (이 2개를 업데이트 주소와 같은 곳에 올리면 자동 업데이트):
echo   %~dp0dist\%APPNAME%_Setup_v%VER%.exe
echo   %~dp0dist\update.json

:done
echo.
echo 완료
echo 실행 파일: %~dp0dist\%APPNAME%\%APPNAME%.exe
pause
exit /b 0

:err
echo 빌드 실패
pause
exit /b 1
