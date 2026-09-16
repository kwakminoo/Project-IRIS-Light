; IRIS Windows installer — payload is staged next to this file by build_iris_setup.ps1
#define MyAppName "IRIS"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "IRIS"
#define MyAppURL "https://github.com/kwakminoo/Project-IRIS-Light"
#define MyAppExeName "IRIS.exe"

[Setup]
AppId={{8F3C2A91-4B17-4E6D-9C21-A1B2C3D4E5F6}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}-light
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={localappdata}\Programs\IRIS
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=IRIS-Setup-{#MyAppVersion}
SetupIconFile=..\iris\assets\iris_icon.ico
UninstallDisplayIcon={app}\iris\assets\iris_icon.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
InfoAfterFile=InfoAfter.txt
LicenseFile=..\LICENSE

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: checkedonce

[Files]
Source: "payload\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\dist\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\iris\assets\iris_icon.ico"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\dist\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\iris\assets\iris_icon.ico"; Tasks: desktopicon

[Run]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\setup.ps1"""; \
  WorkingDir: "{app}"; \
  StatusMsg: "Creating Python venv and installing packages (needs internet)..."; \
  Flags: waituntilterminated
Filename: "{app}\dist\{#MyAppExeName}"; \
  Description: "Launch IRIS now"; \
  WorkingDir: "{app}"; \
  Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\.venv"
Type: filesandordirs; Name: "{app}\.venv-voice"
Type: files; Name: "{app}\.env"
