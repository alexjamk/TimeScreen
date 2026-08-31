#define MyAppName "TimeScreen Control"
#define MyAppVersion "3.1"
#define MyAppPublisher "alexjamk"
#define MyAppExeName "TimeScreenControl.exe"
#define ServiceName "TimeScreenControl"
#define ReleaseDir "..\dist\Release"

[Setup]
AppId={{D149E496-1361-4BB1-A508-CF485F08BBE2}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\TimeScreenControl
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist\Installer
OutputBaseFilename=TimeScreenControl-Setup-{#MyAppVersion}
SetupIconFile=..\src\resources\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
LicenseFile=..\..\LICENSE
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
ShowLanguageDialog=auto

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Dirs]
Name: "{commonappdata}\TimeScreen"

[Files]
Source: "{#ReleaseDir}\TimeScreenControl.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ReleaseDir}\TimeScreenService\*"; DestDir: "{app}\TimeScreenService"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#ReleaseDir}\README.md"; DestDir: "{app}"; Flags: ignoreversion

[InstallDelete]
Type: filesandordirs; Name: "{app}\TimeScreenService"

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "TimeScreenTimer"; ValueData: """{app}\{#MyAppExeName}"" --timer-mode"; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; WorkingDir: "{app}"; Flags: postinstall nowait skipifsilent

[UninstallRun]
Filename: "{sys}\sc.exe"; Parameters: "stop {#ServiceName}"; Flags: runhidden waituntilterminated; RunOnceId: "StopTimeScreenService"
Filename: "{sys}\sc.exe"; Parameters: "delete {#ServiceName}"; Flags: runhidden waituntilterminated; RunOnceId: "DeleteTimeScreenService"
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM TimeScreenControl.exe"; Flags: runhidden waituntilterminated; RunOnceId: "StopTimeScreenGui"

[UninstallDelete]
Type: filesandordirs; Name: "{commonappdata}\TimeScreen"

[Code]
var
  ServiceWasVerified: Boolean;
  InstallationFailed: Boolean;

procedure FailInstallation(const ErrorText: String);
begin
  InstallationFailed := True;
  RaiseException(ErrorText);
end;

function RunHidden(const FileName, Parameters: String; var ResultCode: Integer): Boolean;
begin
  Log(Format('Executing: %s %s', [FileName, Parameters]));
  Result := Exec(FileName, Parameters, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  if Result then
    Log(Format('Exit code: %d', [ResultCode]))
  else
    Log(Format('Execution failed: %s', [SysErrorMessage(ResultCode)]));
end;

function RunRequired(const FileName, Parameters, ErrorText: String): Boolean;
var
  ResultCode: Integer;
begin
  Result := RunHidden(FileName, Parameters, ResultCode) and (ResultCode = 0);
  if not Result then
    FailInstallation(Format('%s (код %d)', [ErrorText, ResultCode]));
end;

function IsServiceRunning: Boolean;
var
  ResultCode: Integer;
  PowerShellParams: String;
begin
  PowerShellParams := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ' +
    '"$s=Get-Service -Name ''{#ServiceName}'' -ErrorAction SilentlyContinue; ' +
    'if (($null -ne $s) -and ($s.Status -eq ''Running'')) { exit 0 } else { exit 1 }"';
  Result := RunHidden(
    ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    PowerShellParams,
    ResultCode) and (ResultCode = 0);
end;

function IsServiceInstalled: Boolean;
var
  ResultCode: Integer;
  PowerShellParams: String;
begin
  PowerShellParams := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ' +
    '"$s=Get-Service -Name ''{#ServiceName}'' -ErrorAction SilentlyContinue; ' +
    'if ($null -ne $s) { exit 0 } else { exit 1 }"';
  Result := RunHidden(
    ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    PowerShellParams,
    ResultCode) and (ResultCode = 0);
end;

function IsServiceRegistryPresent: Boolean;
var
  ResultCode: Integer;
  PowerShellParams: String;
begin
  PowerShellParams := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ' +
    '"if (Test-Path ''Registry::HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Services\{#ServiceName}'') ' +
    '{ exit 0 } else { exit 1 }"';
  Result := RunHidden(
    ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    PowerShellParams,
    ResultCode) and (ResultCode = 0);
end;

function WaitForServiceRunning: Boolean;
var
  Attempt: Integer;
begin
  Result := False;
  for Attempt := 1 to 30 do
  begin
    if IsServiceRunning then
    begin
      Result := True;
      Exit;
    end;
    Sleep(500);
  end;
end;

function StopPreviousInstallation: Boolean;
var
  Attempt: Integer;
  ResultCode: Integer;
begin
  RunHidden(ExpandConstant('{sys}\sc.exe'), 'stop {#ServiceName}', ResultCode);
  Sleep(1000);
  RunHidden(ExpandConstant('{sys}\sc.exe'), 'delete {#ServiceName}', ResultCode);
  RunHidden(ExpandConstant('{sys}\taskkill.exe'), '/F /IM TimeScreenControl.exe', ResultCode);

  Result := False;
  for Attempt := 1 to 20 do
  begin
    if (not IsServiceInstalled) and (not IsServiceRegistryPresent) then
    begin
      Sleep(1000);
      Result := True;
      Exit;
    end;
    Sleep(500);
  end;
end;

function InstallServiceWithRetry: Boolean;
var
  Attempt: Integer;
  ResultCode: Integer;
begin
  Result := False;
  for Attempt := 1 to 10 do
  begin
    if RunHidden(
      ExpandConstant('{app}\TimeScreenService\TimeScreenService.exe'),
      '--startup auto install',
      ResultCode) and (ResultCode = 0) then
    begin
      Result := True;
      Exit;
    end;
    Log(Format('Service installation attempt %d failed with code %d', [Attempt, ResultCode]));
    Sleep(1000);
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  if StopPreviousInstallation then
    Result := ''
  else
    Result := 'Не удалось остановить предыдущую версию службы TimeScreen. ' +
      'Закройте программы TimeScreen, перезагрузите компьютер и повторите установку.';
end;

procedure InstallAndVerifyService;
var
  ConfigDir: String;
  AclParams: String;
  FileAclParams: String;
  ResultCode: Integer;
begin
  ConfigDir := ExpandConstant('{commonappdata}\TimeScreen');
  if not ForceDirectories(ConfigDir) then
    FailInstallation('Не удалось создать каталог конфигурации: ' + ConfigDir);

  RunRequired(
    ExpandConstant('{sys}\icacls.exe'),
    '"' + ConfigDir + '" /reset /T /C',
    'Не удалось сбросить устаревшие права на каталог конфигурации');

  FileAclParams := '"' + ConfigDir + '\*" /inheritance:r /grant:r ' +
    '*S-1-5-18:F *S-1-5-32-544:F *S-1-5-32-545:R /T /C';
  RunRequired(
    ExpandConstant('{sys}\icacls.exe'),
    FileAclParams,
    'Не удалось защитить существующие файлы конфигурации');

  AclParams := '"' + ConfigDir + '" /inheritance:r /grant:r ' +
    '*S-1-5-18:(OI)(CI)F *S-1-5-32-544:(OI)(CI)F *S-1-5-32-545:(OI)(CI)RX /C';
  RunRequired(
    ExpandConstant('{sys}\icacls.exe'),
    AclParams,
    'Не удалось защитить каталог конфигурации');

  if not InstallServiceWithRetry then
    FailInstallation('Не удалось зарегистрировать службу TimeScreen после 10 попыток');

  RunRequired(
    ExpandConstant('{sys}\sc.exe'),
    'failure {#ServiceName} reset= 86400 actions= restart/5000/restart/15000/restart/30000',
    'Не удалось настроить автоматическое восстановление службы');

  if not RunHidden(ExpandConstant('{sys}\sc.exe'), 'start {#ServiceName}', ResultCode) then
    FailInstallation('Не удалось выполнить запуск службы: ' + SysErrorMessage(ResultCode));
  if (ResultCode <> 0) and (ResultCode <> 1056) then
    FailInstallation(Format('Служба не запустилась (код %d)', [ResultCode]));

  if not WaitForServiceRunning then
  begin
    RunHidden(ExpandConstant('{sys}\sc.exe'), 'delete {#ServiceName}', ResultCode);
    FailInstallation('Служба TimeScreen не перешла в состояние Running за 15 секунд. Проверьте журнал установки.');
  end;

  ServiceWasVerified := True;
  Log('TimeScreen service successfully verified as Running');
end;

function GetCustomSetupExitCode: Integer;
begin
  if InstallationFailed then
    Result := 20
  else
    Result := 0;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    InstallAndVerifyService;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (CurPageID = wpFinished) and ServiceWasVerified then
    WizardForm.FinishedLabel.Caption :=
      'TimeScreen Control установлен.' + #13#10 +
      'Служба проверена и работает. Нажмите «Завершить».';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
  ConfigDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    RunHidden(ExpandConstant('{sys}\sc.exe'), 'delete {#ServiceName}', ResultCode);
    ConfigDir := ExpandConstant('{commonappdata}\TimeScreen');
    if DirExists(ConfigDir) then
    begin
      if DelTree(ConfigDir, True, True, True) then
        Log('Конфигурация TimeScreen полностью удалена.')
      else
        Log('Не удалось полностью удалить конфигурацию: ' + ConfigDir);
    end;
  end;
end;
