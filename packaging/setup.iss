#define AppVersion Trim(FileRead(FileOpen(AddBackslash(SourcePath) + "..\VERSION")))

[Setup]
AppId={{2F0A1255-6F4C-44E4-9088-35393E2E0B35}
AppName=어잉PDF
AppVersion={#AppVersion}
AppPublisher=Eoingtilab
DefaultDirName={localappdata}\Programs\EoingPDF
DefaultGroupName=어잉PDF
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\release
OutputBaseFilename=EoingPDF-{#AppVersion}-Setup-x64
SetupIconFile=..\assets\app_icon.ico
UninstallDisplayIcon={app}\EoingPDF.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
CloseApplications=yes
RestartApplications=no
ChangesAssociations=yes
VersionInfoVersion={#AppVersion}

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕 화면에 바로가기 만들기"; Flags: unchecked

[Files]
Source: "..\release\EoingPDF\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\어잉PDF"; Filename: "{app}\EoingPDF.exe"
Name: "{autodesktop}\어잉PDF"; Filename: "{app}\EoingPDF.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\EoingPDF.exe"; Parameters: "--register-shell"; Flags: runhidden waituntilterminated
Filename: "ms-settings:defaultapps?registeredAppUser=EoingPDF"; Description: "기본 PDF 앱 설정 열기"; Flags: shellexec postinstall skipifsilent unchecked
Filename: "{app}\EoingPDF.exe"; Description: "어잉PDF 실행"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\EoingPDF.exe"; Parameters: "--uninstall-menu"; Flags: runhidden waituntilterminated; RunOnceId: "UnregisterShell"
