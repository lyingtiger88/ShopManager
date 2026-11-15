#ifndef MySourceDir
  #define MySourceDir "..\\dist"
#endif
#ifndef MyOutputDir
  #define MyOutputDir "..\\artifacts"
#endif
#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif

#define MyAppName "ShopManager"
#define MyAppExeName "ShopManager.exe"

; NEVER rotate AppId. Inno Setup uses it to identify upgrades and reuse
; the existing install directory instead of demanding an uninstall.
[Setup]
AppId={{F4B31C77-3C5F-4E25-A47D-9AFA5AE31156}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Kaliia Soft
DefaultDirName={localappdata}\\Programs\\ShopManager
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
CloseApplications=yes
RestartApplications=yes
PrivilegesRequired=lowest
OutputDir={#MyOutputDir}
OutputBaseFilename=ShopManager-Setup-x64
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\\{#MyAppExeName}

[Files]
Source: "{#MySourceDir}\\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\\{#MyAppName}"; Filename: "{app}\\{#MyAppExeName}"
Name: "{autodesktop}\\{#MyAppName}"; Filename: "{app}\\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Run]
Filename: "{app}\\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

; Business data belongs in AppData, NOT inside {app}. Uninstalling or
; upgrading the installer must never delete the product's database.
