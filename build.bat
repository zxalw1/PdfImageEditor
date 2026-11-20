@echo off
chcp 65001 >nul
cd /d "%~dp0"
set APPNAME=PdfImageEditor
set VER=1.0.0

if not exist .venv (
    echo [1/4] 가상환경 생성
    py -3 -m venv .venv || python -m venv .venv
)
call .venv\Scripts\activate.bat

echo [2/4] 패키지 설치
python -m pip install --upgrade pip
pip install -r requirements.txt || goto :err

echo [3/4] EXE 빌드
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
pyinstaller --noconfirm --clean --windowed ^
  --name "%APPNAME%" ^
  --icon app.ico ^
  --add-data "app.ico;." ^
  --version-file version_info.txt ^
  --hidden-import win32timezone ^
  --collect-submodules pdf2docx ^
  --exclude-module PySide6.QtWebEngineCore ^
  --exclude-module PySide6.QtWebEngineWidgets ^
  --exclude-module PySide6.Qt3DCore ^
  --exclude-module PySide6.QtQuick ^
  --exclude-module PySide6.QtQml ^
  --exclude-module PySide6.QtMultimedia ^
  --exclude-module tkinter ^
  pdf_image_editor.py || goto :err

echo [4/4] 설치 파일 생성
set ISCC=
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if "%ISCC%"=="" (
    echo Inno Setup 6 미설치 - 설치파일 생성 건너뜀
    echo 다운로드: https://jrsoftware.org/isdl.php
    echo EXE: dist\%APPNAME%\%APPNAME%.exe
    pause
    exit /b 0
)
"%ISCC%" installer.iss || goto :err

echo.
echo 완료
echo 설치파일: dist\%APPNAME%_Setup_v%VER%.exe  ^<- 이 파일만 배포
pause
exit /b 0

:err
echo 빌드 실패
pause
exit /b 1
