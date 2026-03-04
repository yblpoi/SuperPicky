[Setup]
AppName=SuperPicky
AppVersion=4.1.0-0e7bc32
DefaultDirName={commonpf}\SuperPicky
DefaultGroupName=SuperPicky
AppPublisherURL=https://superpicky.app/
OutputBaseFilename=SuperPicky_Setup_Win64_4.1.0_0e7bc32
Compression=lzma2/ultra64
LZMAUseSeparateProcess=yes
LZMADictionarySize=1048576
LZMANumFastBytes=273
SolidCompression=yes
CreateAppDir=yes
UninstallDisplayIcon={app}\SuperPicky.exe
SetupIconFile=_internal\img\icon.ico
WizardStyle=modern
DisableProgramGroupPage=yes
DisableDirPage=no
DisableReadyPage=no
DisableFinishedPage=no
VersionInfoCompany=https://superpicky.app/
WizardImageFile=_internal\img\icon.png
WizardSmallImageFile=_internal\img\icon.png
AlwaysShowComponentsList=no
AlwaysShowGroupOnReadyPage=no
WindowVisible=yes

[Registry]
Root: HKLM; Subkey: SOFTWARE\SuperPicky; ValueType: string; ValueName: InstallDir; ValueData: {app}; Flags: uninsdeletevalue
Root: HKLM; Subkey: SOFTWARE\SuperPicky; ValueType: string; ValueName: Version; ValueData: {#SetupSetting("AppVersion")}; Flags: uninsdeletevalue
Root: HKLM; Subkey: SOFTWARE\SuperPicky; ValueType: string; ValueName: CUDA_Patch_Installed; ValueData: "1"; Flags: uninsdeletevalue

[Code]
function InitializeSetup(): Boolean;
var
  OldInstallDir: string;
  dummy: Integer;
begin
  Result := True;
  // 检查是否已安装旧版本
  if RegValueExists(HKLM, 'SOFTWARE\SuperPicky', 'InstallDir') then
  begin
    // 读取旧安装目录
    if RegQueryStringValue(HKLM, 'SOFTWARE\SuperPicky', 'InstallDir', OldInstallDir) then
    begin
      // 停止正在运行的进程
      Exec('taskkill.exe', '/f /im SuperPicky.exe', '', SW_HIDE, ewWaitUntilTerminated, dummy);
      // 删除旧文件
      DelTree(OldInstallDir, True, True, True);
    end;
  end;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
end;

[Files]
Source: "SuperPicky.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\SuperPicky"; Filename: "{app}\SuperPicky.exe"
Name: "{commondesktop}\SuperPicky"; Filename: "{app}\SuperPicky.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Run]
Filename: "{app}\SuperPicky.exe"; Description: "{cm:LaunchProgram,SuperPicky}"; Flags: nowait postinstall skipifsilent
Filename: "https://superpicky.app/"; Description: "访问项目网站"; Flags: postinstall skipifsilent shellexec

[UninstallRun]
Filename: "taskkill.exe"; Parameters: "/f /im SuperPicky.exe"; Flags: skipifdoesntexist; RunOnceId: "KillSuperPickyProcess"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Languages]
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"