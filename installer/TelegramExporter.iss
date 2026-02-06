[Setup]
AppId={{FAD5F563-8D91-4D92-9A92-0FD0BE8C2C9B}}
AppName=Telegram Exporter
AppVersion=1.0.0
AppPublisher=Telegram Exporter
DefaultDirName={pf}\Telegram Exporter
DefaultGroupName=Telegram Exporter
DisableProgramGroupPage=yes
OutputBaseFilename=TelegramExporterSetup
OutputDir=dist
Compression=lzma
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\icons\app.ico
UninstallDisplayIcon={app}\Telegram Exporter.exe

[Files]
Source: "..\dist\Telegram Exporter.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Telegram Exporter"; Filename: "{app}\Telegram Exporter.exe"
Name: "{commondesktop}\Telegram Exporter"; Filename: "{app}\Telegram Exporter.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительно:"
