[Setup]
AppName=SuperPicky CUDA Patch
AppVersion=4.1.0-0e7bc32
DefaultDirName={commonpf}\SuperPicky
DefaultGroupName=SuperPicky
AppPublisherURL=https://superpicky.app/
OutputBaseFilename=SuperPicky_CUDA_Patch_Win64_4.1.0_0e7bc32
Compression=lzma2/ultra64
LZMAUseSeparateProcess=yes
LZMADictionarySize=1048576
LZMANumFastBytes=273
LZMAUseSeparateProcess=yes
SolidCompression=yes
CreateAppDir=yes
Uninstallable=no
SetupIconFile=img\icon.ico
WizardStyle=modern
DisableProgramGroupPage=yes
DisableDirPage=no
DisableReadyPage=no
DisableFinishedPage=no
DirExistsWarning=no
VersionInfoCompany=https://superpicky.app/
WizardImageFile=img\icon.png
WizardSmallImageFile=img\icon.png
AlwaysShowComponentsList=no
AlwaysShowGroupOnReadyPage=no
WindowVisible=yes

[Registry]
Root: HKLM; Subkey: SOFTWARE\SuperPicky; ValueType: string; ValueName: InstallDir; ValueData: {app}; Flags: uninsdeletevalue
Root: HKLM; Subkey: SOFTWARE\SuperPicky; ValueType: string; ValueName: Version; ValueData: {#SetupSetting("AppVersion")}; Flags: uninsdeletevalue
Root: HKLM; Subkey: SOFTWARE\SuperPicky; ValueType: string; ValueName: CUDA_Patch_Installed; ValueData: "1"; Flags: uninsdeletevalue

[Code]
var
  OldInstallDir: string;

function InitializeSetup(): Boolean;
var
  dummy: Integer;
begin
  Result := True;
  // 检查是否已安装旧版本并获取安装目录
  if RegValueExists(HKLM, 'SOFTWARE\SuperPicky', 'InstallDir') then
  begin
    // 读取旧安装目录
    RegQueryStringValue(HKLM, 'SOFTWARE\SuperPicky', 'InstallDir', OldInstallDir);
    // 停止正在运行的进程
    Exec('taskkill.exe', '/f /im SuperPicky.exe', '', SW_HIDE, ewWaitUntilTerminated, dummy);
  end;
end;

procedure InitializeWizard;
begin
  // 在向导初始化后设置默认目录
  if OldInstallDir <> '' then
  begin
    WizardForm.DirEdit.Text := OldInstallDir;
  end;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
end;

[Files]
Source: "SuperPicky.exe"; DestDir: "{app}"; Flags: ignoreversion overwritereadonly
Source: "_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs overwritereadonly

[Run]
Filename: "{app}\SuperPicky.exe"; Description: "{cm:LaunchProgram,SuperPicky}"; Flags: nowait postinstall skipifsilent

[Languages]
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
