; WhoSaid 윈도우 설치 프로그램 (Inno Setup 6)
; 관리자 권한 없이 사용자 폴더에 설치합니다.
; 목소리 지문·설정(%APPDATA%\WhoSaid)과 회의록(문서\WhoSaid)은 제거해도 남습니다.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6C1C6E7B-5B1D-4F0B-9F27-5B6F0E8C1A57}
AppName=WhoSaid
AppVersion={#AppVersion}
AppPublisher=WhoSaid
AppPublisherURL=https://github.com/R4NBBIT/whosaid
DefaultDirName={localappdata}\Programs\WhoSaid
DefaultGroupName=WhoSaid
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=WhoSaid-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\WhoSaid.exe

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕 화면에 바로 가기 만들기"; Flags: unchecked

[Files]
Source: "..\dist\WhoSaid\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\WhoSaid"; Filename: "{app}\WhoSaid.exe"
Name: "{group}\WhoSaid 제거"; Filename: "{uninstallexe}"
Name: "{autodesktop}\WhoSaid"; Filename: "{app}\WhoSaid.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\WhoSaid.exe"; Description: "WhoSaid 실행"; Flags: nowait postinstall skipifsilent
