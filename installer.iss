#define MyAppName "Тендер Авто"
#define MyAppVersion "1.3.0"
#define MyAppExeName "TenderAuto.exe"

[Setup]
AppId={{F3A9C2E1-7B4D-4E8A-9C31-5D6F2A8B4E70}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Tender Auto
DefaultDirName={localappdata}\TenderAuto
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=installer_output
OutputBaseFilename=TenderAuto-Setup-{#MyAppVersion}
Compression=lzma2/normal
SolidCompression=yes
SetupIconFile=

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Ярлыки:"; Flags: unchecked

[Files]
; всё содержимое продуктовой папки, КРОМЕ твоих тестовых данных и ТВОЕГО ключа лицензии
Source: "dist\TenderAuto\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "выгрузка_*.xlsx,data\*,output\*,license\*,__pycache__\*"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Удалить {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить {#MyAppName}"; Flags: nowait postinstall skipifsilent