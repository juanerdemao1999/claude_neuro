#define MyAppName "NEX5 Spike LFP Analyzer"
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#ifndef AppSourceDir
  #error AppSourceDir must be provided on the command line.
#endif
#ifndef OutputDir
  #define OutputDir AddBackslash(SourcePath) + "..\\release"
#endif

[Setup]
AppId={{56FC3C91-091D-483A-B786-7F4B114A2128}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppPublisher=NEX5
DefaultDirName={autopf}\NEX5SpikeLFPAnalyzer
DefaultGroupName=NEX5 Spike LFP Analyzer
DisableProgramGroupPage=yes
Compression=lzma
SolidCompression=yes
WizardStyle=modern
OutputDir={#OutputDir}
OutputBaseFilename=NEX5SpikeLFPAnalyzer_Setup_{#AppVersion}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\NEX5SpikeLFPAnalyzer.exe

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional tasks:"; Flags: unchecked

[Files]
Source: "{#AppSourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\NEX5 Spike LFP Analyzer"; Filename: "{app}\NEX5SpikeLFPAnalyzer.exe"
Name: "{autodesktop}\NEX5 Spike LFP Analyzer"; Filename: "{app}\NEX5SpikeLFPAnalyzer.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\NEX5SpikeLFPAnalyzer.exe"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
