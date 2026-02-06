$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Join-Path $root "..")

python -m venv .venv
. .venv\Scripts\Activate.ps1

pip install -r requirements.txt
pip install pyinstaller

$iconPng = Join-Path (Get-Location) "assets\app_icon.png"
$iconIco = Join-Path (Get-Location) "icons\app.ico"
$iconArg = ""

if (Test-Path $iconPng) {
    pip install pillow
    python scripts\make_icons.py --in $iconPng --out $iconIco
    $iconArg = "--icon `"$iconIco`""
}

pyinstaller --windowed --onefile --name "Telegram Exporter" $iconArg app.py

Write-Host "EXE готов: dist\Telegram Exporter.exe"
