$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Set-Location ..
& .\.venv\Scripts\python.exe -m pytest
