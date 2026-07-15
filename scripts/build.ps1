$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (!(Test-Path $Python)) {
    & (Join-Path $PSScriptRoot "setup.ps1")
}
Push-Location $Root
try {
    if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
    if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
    & $Python -m PyInstaller "pixel_level_tool.spec" --clean --noconfirm
    $Exe = Join-Path $Root "dist\MarbleSortPixelLevelTool\MarbleSortPixelLevelTool.exe"
    if (!(Test-Path $Exe)) {
        throw "Expected EXE was not created: $Exe"
    }
}
finally {
    Pop-Location
}
