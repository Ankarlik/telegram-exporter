$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Join-Path $root "..")

python -m venv .venv
. .venv\Scripts\Activate.ps1

pip install -r requirements.txt
pip install pyinstaller

$iconPng = Join-Path (Get-Location) "assets\app_icon.png"
$iconIco = Join-Path (Get-Location) "icons\app.ico"
if (Test-Path $iconPng) {
    python -m pip install pillow
    python scripts\make_icons.py --in $iconPng --out $iconIco
    pyinstaller --windowed --onefile --name "TelegramExporter" --icon "$iconIco" --exclude-module app_legacy --collect-all customtkinter --collect-all telethon --collect-all faster_whisper --collect-all ctranslate2 --collect-all tokenizers --collect-all imageio_ffmpeg app.py
} else {
    pyinstaller --windowed --onefile --name "TelegramExporter" --exclude-module app_legacy --collect-all customtkinter --collect-all telethon --collect-all faster_whisper --collect-all ctranslate2 --collect-all tokenizers --collect-all imageio_ffmpeg app.py
}

Write-Host "EXE ready: dist\TelegramExporter.exe"
Write-Host "Open installer\\TelegramExporter.iss in Inno Setup to compile installer."
