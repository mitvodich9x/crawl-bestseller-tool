; Bo cai dat Inno Setup 6 (giong walmart-scanner-tool). Chay qua build_installer.bat.
; Giu file nay thuan ASCII.
#define AppName "Bestseller Crawler"
#define AppExeName "BestsellerCrawler.exe"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define SourceDir "..\dist\BestsellerCrawler"

[Setup]
AppId={{B18E4A49-7ABF-4548-8C41-499702BDD7F5}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=VGP
DefaultDirName={localappdata}\Programs\BestsellerCrawler
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\release
OutputBaseFilename=BestsellerCrawlerSetup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; cai vao thu muc cua user, khong can quyen admin; thu muc data (database, phien dang nhap) ghi duoc
PrivilegesRequired=lowest
SetupIconFile=..\app_icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
CloseApplications=yes
CloseApplicationsFilter={#AppExeName}
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[InstallDelete]
; Xoa thu vien cua ban cu truoc khi chep ban moi, tranh file thua gay loi.
; Chi xoa _internal - thu muc data (database, cai dat, phien dang nhap watchcount) giu nguyen.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Excludes: "data\*"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
; khong co skipifsilent: cap nhat tu dong chay installer /SILENT va can mo lai app sau khi cai
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall
