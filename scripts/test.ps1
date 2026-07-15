$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (!(Test-Path $Python)) {
    & (Join-Path $PSScriptRoot "setup.ps1")
}
& $Python -m pytest

