; IRIS Windows installer — payload is staged next to this file by build_iris_setup.ps1
#define MyAppName "IRIS"
#define MyAppVersion "0.1.10"
#define MyAppPublisher "IRIS"
#define MyAppURL "https://github.com/kwakminoo/Project-IRIS-Light"
#define MyAppExeName "IRIS.exe"
; Inno 출력은 IRIS-Setup.exe. 빌드 스크립트가 IRIS-Setup-<version>.exe 복사본도 만든다.
; 사이트는 latest.json 의 download_url(버전 파일명)을 쓰고, IRIS-Setup.exe 는 안정 별칭이다.
#define MyOutputName "IRIS-Setup"
; 가장 깊은 번들 파일(integrations\showui-aloha\...\trajectory_refiner.txt)의
; 설치 폴더 기준 상대 경로 길이. MAX_PATH(260) 계산의 근거다.
#define MyDeepestRelPath 117

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
OutputBaseFilename={#MyOutputName}
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
VersionInfoVersion={#MyAppVersion}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoProductName={#MyAppName}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} {#MyAppVersion} Setup

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

; setup.ps1 은 [Run] 이 아니라 [Code] 의 CurStepChanged 에서 실행한다.
; [Run] 은 종료 코드를 버려서, pip 이 끊겨도 설치 프로그램이 성공으로 끝났다.
[Run]
Filename: "{app}\dist\{#MyAppExeName}"; \
  Description: "Launch IRIS now"; \
  WorkingDir: "{app}"; \
  Flags: nowait postinstall skipifsilent; \
  Check: DependenciesReady

[UninstallDelete]
Type: filesandordirs; Name: "{app}\.venv"
Type: filesandordirs; Name: "{app}\.venv-voice"
Type: files; Name: "{app}\.env"
Type: files; Name: "{app}\setup-log.txt"
Type: files; Name: "{app}\setup-log-pip.txt"
Type: files; Name: "{app}\setup-fail-reason.txt"

[Code]
var
  DepsFailed: Boolean;

{ 설치 경로가 길면 가장 깊은 파일이 MAX_PATH(260)를 넘어, 설치가 중간에
  MoveFile code 3 으로 실패하고 통째로 롤백된다. 미리 막는다. }
function MaxDirLen(): Integer;
begin
  { 260 - '\' - 가장 깊은 상대 경로 - 여유 20자(설치 후 만들어지는 .venv 등) }
  Result := 260 - 1 - {#MyDeepestRelPath} - 20;
end;

function DirTooLongMessage(const Dir: String): String;
begin
  Result := '';
  if Length(Dir) > MaxDirLen() then
    Result :=
      'The install folder path is too long: ' + IntToStr(Length(Dir)) + ' characters.' + #13#10#13#10 +
      'IRIS bundles files nested up to ' + IntToStr({#MyDeepestRelPath}) + ' characters deep, and Windows' + #13#10 +
      'limits a full path to 260. Installing here would fail partway through' + #13#10 +
      'and roll the whole installation back.' + #13#10#13#10 +
      'Choose a folder whose path is ' + IntToStr(MaxDirLen()) + ' characters or fewer' + #13#10 +
      '(the default, ' + ExpandConstant('{localappdata}\Programs\IRIS') + ', is fine).';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Msg: String;
begin
  Result := True;
  if CurPageID = wpSelectDir then
  begin
    Msg := DirTooLongMessage(WizardDirValue);
    if Msg <> '' then
    begin
      SuppressibleMsgBox(Msg, mbError, MB_OK, IDOK);
      Result := False;
    end;
  end;
end;

{ /SILENT /DIR=... 로 설치할 때는 NextButtonClick 이 불리지 않는다. 마지막 방어선. }
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := DirTooLongMessage(ExpandConstant('{app}'));
  if Result <> '' then
    Log('Install folder path too long ('
        + IntToStr(Length(ExpandConstant('{app}'))) + ' chars); aborting before any file is copied.');
end;

function DependenciesReady(): Boolean;
begin
  Result := not DepsFailed;
end;

{ setup-fail-reason.txt (UTF-8) — Fail() 가 남긴 한 줄. 없으면 setup-log 폴백. }
function SetupFailureHint(): String;
var
  ReasonPath: String;
  LogPath: String;
  Lines: TArrayOfString;
  I: Integer;
  Line: String;
begin
  Result := '';
  ReasonPath := ExpandConstant('{app}\setup-fail-reason.txt');
  if FileExists(ReasonPath) then
  begin
    if LoadStringsFromFile(ReasonPath, Lines) and (GetArrayLength(Lines) > 0) then
    begin
      Result := Trim(Lines[0]);
      if Result <> '' then
        Exit;
    end;
  end;
  LogPath := ExpandConstant('{app}\setup-log.txt');
  if not FileExists(LogPath) then
    Exit;
  if not LoadStringsFromFile(LogPath, Lines) then
    Exit;
  for I := GetArrayLength(Lines) - 1 downto 0 do
  begin
    Line := Trim(Lines[I]);
    { ASCII fallback: transcript may be UTF-16 and unreadable here }
    if (Pos('설치 실패:', Line) = 1) or (Pos('FAIL:', Line) = 1) then
    begin
      Result := Line;
      Exit;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  Launched: Boolean;
  Hint: String;
  Detail: String;
begin
  if CurStep <> ssPostInstall then
    Exit;

  { SW_HIDE + -WindowStyle Hidden: 콘솔/Windows Terminal 창을 띄우지 않는다.
    진행 안내는 StatusLabel 만. 로그는 setup.ps1 의 Transcript / pip --log 에 남는다. }
  WizardForm.StatusLabel.Caption :=
    'Installing Python (if needed) and packages — needs internet, may take several minutes...';
  WizardForm.Refresh();

  Launched := Exec(
    ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    ExpandConstant('-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{app}\setup.ps1"'),
    ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode);

  if not Launched then
  begin
    DepsFailed := True;
    ResultCode := -1;
  end
  else
    DepsFailed := ResultCode <> 0;

  if not DepsFailed then
  begin
    Log('setup.ps1 finished successfully.');
    Exit;
  end;

  { /VERYSILENT /SUPPRESSMSGBOXES 로 깔면 아래 창이 안 뜬다. 로그에는 남겨 둔다. }
  Hint := SetupFailureHint();
  Log('setup.ps1 FAILED with exit code ' + IntToStr(ResultCode)
      + ' — IRIS will not start until setup.bat is run successfully.');
  if Hint <> '' then
    Log('setup failure hint: ' + Hint);

  Detail :=
    'IRIS was copied to your computer, but installing the Python packages' + #13#10 +
    'did not finish (exit code ' + IntToStr(ResultCode) + ').' + #13#10#13#10;
  if Hint <> '' then
    Detail := Detail + Hint + #13#10#13#10;
  Detail := Detail +
    'IRIS will not start until this step completes. Check your internet' + #13#10 +
    'connection, then open the install folder and double-click setup.bat:' + #13#10#13#10 +
    ExpandConstant('{app}\setup.bat') + #13#10#13#10 +
    'What went wrong is recorded in:' + #13#10 +
    ExpandConstant('{app}\setup-log.txt') + #13#10 +
    ExpandConstant('{app}\setup-log-pip.txt');

  SuppressibleMsgBox(Detail, mbError, MB_OK, IDOK);
end;
