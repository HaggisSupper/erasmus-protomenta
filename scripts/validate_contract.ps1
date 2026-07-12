<#
.SYNOPSIS
    Governance control-plane validator for agent task contracts (Windows).

.DESCRIPTION
    Wraps validate_contract.py for Windows PowerShell.  No Docker, no daemon,
    no OAuth provider is required.  All checks are deterministic.

    Exit codes:
        0   ready
        1   blocked
        2   repair_required
        3   awaiting_human
        4   abandoned
        10  usage error / file not found

.PARAMETER ContractPath
    Path to the agent task contract JSON file.
    Defaults to contracts\fixtures\valid_task.json for quick verification.

.PARAMETER HeadSha
    Current HEAD SHA of the branch (40 hex characters).
    If omitted, stale-SHA check is skipped and a warning is emitted.

.PARAMETER BranchWriters
    Comma-separated list of GitHub usernames with write access to the branch.
    If omitted, the shared-branch check is skipped.

.PARAMETER RepairAttempts
    Number of prior materially-similar repair attempts (default: 0).
    When >= 3, the contract is immediately abandoned.

.PARAMETER AsJson
    Emit output as machine-readable JSON instead of human-readable text.

.EXAMPLE
    # Quick smoke-test with the valid fixture:
    .\scripts\validate_contract.ps1

.EXAMPLE
    # Full enforcement including HEAD SHA and branch writers:
    $sha = git rev-parse HEAD
    .\scripts\validate_contract.ps1 `
        -ContractPath contracts\fixtures\valid_task.json `
        -HeadSha $sha `
        -BranchWriters "HaggisSupper"

.EXAMPLE
    # Machine-readable JSON output:
    .\scripts\validate_contract.ps1 -ContractPath path\to\contract.json -AsJson

.NOTES
    Windows-first operation.  Requires Python 3.12+ on PATH (or .venv activated).
    Run from the repository root.
#>

[CmdletBinding()]
param(
    [string]$ContractPath = "contracts\fixtures\valid_task.json",
    [string]$HeadSha = "",
    [string]$BranchWriters = "",
    [int]$RepairAttempts = 0,
    [switch]$AsJson
)

$ErrorActionPreference = "Stop"

# Resolve Python interpreter: prefer .venv if present.
$PythonExe = "python"
$VenvPython = Join-Path $PSScriptRoot "..\\.venv\\Scripts\\python.exe"
if (Test-Path $VenvPython) {
    $PythonExe = $VenvPython
}

$ScriptPath = Join-Path $PSScriptRoot "validate_contract.py"
if (-not (Test-Path $ScriptPath)) {
    Write-Error "validate_contract.py not found at: $ScriptPath"
    exit 10
}

if (-not (Test-Path $ContractPath)) {
    Write-Error "Contract file not found: $ContractPath"
    exit 10
}

# Build argument list.
$Args = @($ScriptPath, $ContractPath, "--repair-attempts", $RepairAttempts)

if ($HeadSha -ne "") {
    $Args += @("--head-sha", $HeadSha)
}

if ($BranchWriters -ne "") {
    $Args += @("--branch-writers", $BranchWriters)
}

if ($AsJson) {
    $Args += "--json"
}

Write-Host ""
Write-Host "Erasmus Governance Validator" -ForegroundColor Cyan
Write-Host "Contract : $ContractPath" -ForegroundColor Cyan
if ($HeadSha -ne "") {
    Write-Host "HEAD SHA : $HeadSha" -ForegroundColor Cyan
}
if ($BranchWriters -ne "") {
    Write-Host "Writers  : $BranchWriters" -ForegroundColor Cyan
}
Write-Host ""

& $PythonExe @Args
$ExitCode = $LASTEXITCODE

# Map exit code to status label for summary line.
$StatusMap = @{0="READY"; 1="BLOCKED"; 2="REPAIR_REQUIRED"; 3="AWAITING_HUMAN"; 4="ABANDONED"}
$StatusLabel = $StatusMap[$ExitCode]
if (-not $StatusLabel) { $StatusLabel = "UNKNOWN" }

$Color = switch ($ExitCode) {
    0 { "Green" }
    1 { "Red" }
    2 { "Yellow" }
    3 { "Blue" }
    4 { "Magenta" }
    default { "White" }
}

if (-not $AsJson) {
    Write-Host ""
    Write-Host "Governance status: $StatusLabel" -ForegroundColor $Color
}

exit $ExitCode
