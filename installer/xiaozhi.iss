#define MyAppName "小智电脑助手"
#define MyAppVersion "0.1.2"
#define MyAppPublisher "XiaoZhi"
#define MyAppExe "runtime\pythonw.exe"

[Setup]
AppId={{E4AEF3AD-2F37-47BF-B3B6-BC4FB9A0D1C8}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\XiaoZhiAssistant
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=XiaoZhiSetup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\runtime\pythonw.exe
SetupLogging=yes

[Files]
Source: "..\build\stage\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\小智电脑助手"; Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\app\main.py"""; WorkingDir: "{app}"
Name: "{userdesktop}\小智电脑助手"; Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\app\main.py"""; WorkingDir: "{app}"
Name: "{userstartup}\小智电脑助手后台"; Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\app\main.py"" --background"; WorkingDir: "{app}"; Tasks: startup

[Tasks]
Name: "startup"; Description: "登录 Windows 后自动启动小智后台"; GroupDescription: "启动选项:"; Flags: checkedonce

[Run]
Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\app\main.py"""; WorkingDir: "{app}"; Description: "启动小智电脑助手"; Flags: nowait postinstall skipifsilent
