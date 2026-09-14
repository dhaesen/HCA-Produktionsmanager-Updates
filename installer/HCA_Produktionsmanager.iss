#define MyAppName "HCA Produktionsmanager"
#define MyAppVersion "0.13.5.4"
#define MyAppPublisher "Werbestudio Königswinter"
#define MyAppExeName "HCA_Produktionsmanager.exe"

#ifndef SourceDir
  #define SourceDir ".\payload"
#endif
#ifndef OutputDir
  #define OutputDir ".\dist"
#endif

[Setup]
AppId={{D8768B32-5DA6-4AEC-A9B5-B945A6B65273}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\HCA Produktionsmanager
DefaultGroupName=HCA Produktionsmanager
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=HCA_Produktionsmanager_Setup_v0.13.5.4
SetupIconFile={#SourceDir}\assets\HCA.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
CloseApplications=yes
RestartApplications=no
VersionInfoVersion=0.13.5.4
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=HCA Produktionsmanager Vollinstallation
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoCopyright=Werbestudio Königswinter

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "Desktop-Verknüpfung erstellen"; GroupDescription: "Verknüpfungen:"; Flags: checkedonce

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Excludes: "config.json,data\*"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceDir}\data\README.txt"; DestDir: "{app}\data"; Flags: ignoreversion onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{autoprograms}\HCA Produktionsmanager"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\HCA Produktionsmanager"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "HCA Produktionsmanager starten"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM HCA_Produktionsmanager.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM HCA_Backend.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ConfigFile: String;
  DefaultConfig: String;
begin
  if CurStep = ssPostInstall then
  begin
    ConfigFile := ExpandConstant('{app}\config.json');
    DefaultConfig := ExpandConstant('{app}\config.default.json');
    if (not FileExists(ConfigFile)) and FileExists(DefaultConfig) then
      FileCopy(DefaultConfig, ConfigFile, False);
  end;
end;
