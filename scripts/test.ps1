$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
Set-Location $PSScriptRoot
Set-Location ..

$python = if (Test-Path -LiteralPath ".\.venv\Scripts\python.exe") {
    ".\.venv\Scripts\python.exe"
}
else {
    "python"
}

& $python scripts\validate_opencode_layer.py
if ($LASTEXITCODE -ne 0) {
    throw "OpenCode Erasmus layer validation failed."
}

& $python -m pytest tests\ -v
if ($LASTEXITCODE -ne 0) {
    throw "Repository tests failed."
}
