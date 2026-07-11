$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Set-Location ..
if (-not (Test-Path .venv)) {
    py -3.12 -m venv .venv
}
& .\.venv\Scripts\python.exe -m pip install -e .
& .\.venv\Scripts\erasmus.exe init
Write-Host "Erasmus initialized."
