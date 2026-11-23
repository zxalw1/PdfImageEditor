; PDF·이미지 통합 편집기 설치 스크립트 (Inno Setup 6)
#define MyAppName "PDF·이미지 통합 편집기"
#define MyAppExeName "PdfImageEditor.exe"
#define MyAppVersion "1.10.2"

[Setup]
AppId={{D075CAF7-F477-469F-B683-E493FA2A8A0D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
DefaultDirName={autopf}\PdfImageEditor
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=dist
OutputBaseFilename=PdfImageEditor_Setup_v{#MyAppVersion}
SetupIconFile=app\assets\app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
VersionInfoVersion={#MyAppVersion}.0

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕화면에 아이콘 만들기"; GroupDescription: "추가 작업:"

[InstallDelete]
; 덮어 설치(업데이트) 시 이전 버전 라이브러리를 먼저 지움 — 안 쓰게 된 파일이 남아 용량이 커지는 것 방지
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "dist\PdfImageEditor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{#MyAppName} 제거"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{#MyAppName} 실행"; Flags: nowait postinstall skipifsilent
; 자동 업데이트(앱이 /AUTOUPDATE=1 로 실행)일 때만 설치 후 프로그램을 다시 실행 (일괄 무인 설치 때는 실행 안 함)
Filename: "{app}\{#MyAppExeName}"; Flags: nowait; Check: IsAutoUpdate

[Code]
function IsAutoUpdate: Boolean;
begin
  Result := ExpandConstant('{param:AUTOUPDATE|0}') = '1';
end;

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
