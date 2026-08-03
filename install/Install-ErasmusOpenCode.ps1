[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "Medium")]
param(
    [ValidateSet("Install", "Repair", "Rollback", "Uninstall")]
    [string]$Action = "Install",

    [string]$SourceRoot = (Split-Path -Parent $PSScriptRoot),

    [string]$TargetRoot = (Join-Path $HOME ".config\opencode"),

    [string]$PythonExecutable = "python"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Get-FullPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    return [System.IO.Path]::GetFullPath($Path)
}

function Get-Sha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Convert-RelativePathToNative {
    param([Parameter(Mandatory = $true)][string]$Path)
    return $Path.Replace("/", [System.IO.Path]::DirectorySeparatorChar)
}

function Copy-FileAtomically {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )

    $directory = Split-Path -Parent $Destination
    if (-not (Test-Path -LiteralPath $directory)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }
    $temporary = "$Destination.erasmus.$([Guid]::NewGuid().ToString('N')).tmp"
    try {
        Copy-Item -LiteralPath $Source -Destination $temporary -Force
        Move-Item -LiteralPath $temporary -Destination $Destination -Force
    }
    finally {
        if (Test-Path -LiteralPath $temporary) {
            Remove-Item -LiteralPath $temporary -Force
        }
    }
}

function Write-JsonAtomically {
    param(
        [Parameter(Mandatory = $true)][object]$Value,
        [Parameter(Mandatory = $true)][string]$Destination
    )

    $directory = Split-Path -Parent $Destination
    if (-not (Test-Path -LiteralPath $directory)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }
    $temporary = "$Destination.erasmus.$([Guid]::NewGuid().ToString('N')).tmp"
    $encoding = New-Object System.Text.UTF8Encoding($false)
    try {
        $json = $Value | ConvertTo-Json -Depth 10
        [System.IO.File]::WriteAllText($temporary, $json + [Environment]::NewLine, $encoding)
        Move-Item -LiteralPath $temporary -Destination $Destination -Force
    }
    finally {
        if (Test-Path -LiteralPath $temporary) {
            Remove-Item -LiteralPath $temporary -Force
        }
    }
}

function Assert-ValidSourceLayer {
    param([Parameter(Mandatory = $true)][string]$Root)

    $validator = Join-Path $Root "scripts\validate_opencode_layer.py"
    if (-not (Test-Path -LiteralPath $validator -PathType Leaf)) {
        throw "OpenCode layer validator not found: $validator"
    }

    & $PythonExecutable $validator $Root
    if ($LASTEXITCODE -ne 0) {
        throw "OpenCode layer validation failed; no installation files were changed."
    }
}

function Get-SourceEntries {
    param([Parameter(Mandatory = $true)][string]$Root)

    $sourceBase = Get-FullPath (Join-Path $Root ".opencode")
    if (-not (Test-Path -LiteralPath $sourceBase -PathType Container)) {
        throw "OpenCode source directory not found: $sourceBase"
    }

    $entries = @()
    foreach ($directoryName in @("agents", "commands", "skills")) {
        $directory = Join-Path $sourceBase $directoryName
        if (-not (Test-Path -LiteralPath $directory -PathType Container)) {
            throw "Required OpenCode source directory not found: $directory"
        }
        foreach ($file in Get-ChildItem -LiteralPath $directory -File -Recurse | Sort-Object FullName) {
            $relative = $file.FullName.Substring($sourceBase.Length).TrimStart("\", "/")
            $entries += [PSCustomObject]@{
                source_path = $file.FullName
                relative_path = $relative.Replace("\", "/")
                source_sha256 = Get-Sha256 $file.FullName
            }
        }
    }
    return @($entries)
}

function Install-Layer {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Target,
        [Parameter(Mandatory = $true)][string]$Operation
    )

    Assert-ValidSourceLayer $Root
    $sourceEntries = Get-SourceEntries $Root
    $manifestPath = Join-Path $Target "erasmus-install-manifest.json"
    $timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssfffffffZ")
    $backupRoot = Join-Path $Target ".erasmus-backups\$timestamp"
    $mutations = @()

    foreach ($sourceEntry in $sourceEntries) {
        $nativeRelative = Convert-RelativePathToNative $sourceEntry.relative_path
        $destination = Join-Path $Target $nativeRelative
        $exists = Test-Path -LiteralPath $destination -PathType Leaf
        if ($exists -and (Get-Sha256 $destination) -eq $sourceEntry.source_sha256) {
            continue
        }

        $backupPath = $null
        $createdByInstall = -not $exists
        if ($exists) {
            $backupPath = Join-Path $backupRoot $nativeRelative
        }

        $mutations += [PSCustomObject]@{
            source_path = $sourceEntry.source_path
            relative_path = $sourceEntry.relative_path
            source_sha256 = $sourceEntry.source_sha256
            target_path = $destination
            created_by_install = $createdByInstall
            backup_path = $backupPath
        }
    }

    if ($mutations.Count -eq 0) {
        Write-Output "Erasmus OpenCode layer is already current."
        return
    }

    $previousManifestBackup = $null
    if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
        $previousManifestBackup = Join-Path $backupRoot "erasmus-install-manifest.previous.json"
    }

    foreach ($mutation in $mutations) {
        $description = "$Operation $($mutation.relative_path)"
        if ($PSCmdlet.ShouldProcess($mutation.target_path, $description)) {
            if ($null -ne $mutation.backup_path) {
                $backupDirectory = Split-Path -Parent $mutation.backup_path
                if (-not (Test-Path -LiteralPath $backupDirectory)) {
                    New-Item -ItemType Directory -Path $backupDirectory -Force | Out-Null
                }
                Copy-FileAtomically -Source $mutation.target_path -Destination $mutation.backup_path
            }
            Copy-FileAtomically -Source $mutation.source_path -Destination $mutation.target_path
        }
    }

    if ($null -ne $previousManifestBackup -and $PSCmdlet.ShouldProcess($previousManifestBackup, "Back up previous Erasmus install manifest")) {
        Copy-FileAtomically -Source $manifestPath -Destination $previousManifestBackup
    }

    $manifestEntries = @()
    foreach ($mutation in $mutations) {
        $manifestEntries += [ordered]@{
            relative_path = $mutation.relative_path
            installed_sha256 = $mutation.source_sha256
            created_by_install = [bool]$mutation.created_by_install
            backup_path = $mutation.backup_path
        }
    }

    $manifest = [ordered]@{
        schema_version = 1
        action = $Operation
        created_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        source_root = $Root
        target_root = $Target
        previous_manifest_backup = $previousManifestBackup
        entries = $manifestEntries
    }

    if ($PSCmdlet.ShouldProcess($manifestPath, "Write Erasmus install manifest")) {
        Write-JsonAtomically -Value $manifest -Destination $manifestPath
    }

    Write-Output "$Operation completed: $($mutations.Count) file(s) changed."
}

function Read-Manifest {
    param([Parameter(Mandatory = $true)][string]$ManifestPath)

    if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
        throw "Erasmus install manifest not found: $ManifestPath"
    }
    return Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Rollback-OneManifest {
    param(
        [Parameter(Mandatory = $true)][string]$Target,
        [Parameter(Mandatory = $true)][string]$ManifestPath,
        [Parameter(Mandatory = $true)][string]$Operation
    )

    $manifest = Read-Manifest $ManifestPath
    $entries = @($manifest.entries)

    for ($index = $entries.Count - 1; $index -ge 0; $index--) {
        $entry = $entries[$index]
        $nativeRelative = Convert-RelativePathToNative ([string]$entry.relative_path)
        $destination = Join-Path $Target $nativeRelative

        if (Test-Path -LiteralPath $destination -PathType Leaf) {
            $currentHash = Get-Sha256 $destination
            if ($currentHash -ne [string]$entry.installed_sha256) {
                throw "Refusing to overwrite or remove modified file during ${Operation}: $destination"
            }
        }

        $backupPath = [string]$entry.backup_path
        if (-not [string]::IsNullOrWhiteSpace($backupPath)) {
            if (-not (Test-Path -LiteralPath $backupPath -PathType Leaf)) {
                throw "Required rollback backup is missing: $backupPath"
            }
            if ($PSCmdlet.ShouldProcess($destination, "Restore pre-install file")) {
                Copy-FileAtomically -Source $backupPath -Destination $destination
            }
        }
        elseif ([bool]$entry.created_by_install -and (Test-Path -LiteralPath $destination -PathType Leaf)) {
            if ($PSCmdlet.ShouldProcess($destination, "Remove Erasmus-created file")) {
                Remove-Item -LiteralPath $destination -Force
            }
        }
    }

    $previousManifest = [string]$manifest.previous_manifest_backup
    if (-not [string]::IsNullOrWhiteSpace($previousManifest)) {
        if (-not (Test-Path -LiteralPath $previousManifest -PathType Leaf)) {
            throw "Previous install manifest backup is missing: $previousManifest"
        }
        if ($PSCmdlet.ShouldProcess($ManifestPath, "Restore previous Erasmus install manifest")) {
            Copy-FileAtomically -Source $previousManifest -Destination $ManifestPath
        }
    }
    elseif ($PSCmdlet.ShouldProcess($ManifestPath, "Remove Erasmus install manifest")) {
        Remove-Item -LiteralPath $ManifestPath -Force
    }

    return $true
}

$SourceRoot = Get-FullPath $SourceRoot
$TargetRoot = Get-FullPath $TargetRoot
$manifestPath = Join-Path $TargetRoot "erasmus-install-manifest.json"

switch ($Action) {
    "Install" {
        Install-Layer -Root $SourceRoot -Target $TargetRoot -Operation "Install"
    }
    "Repair" {
        Install-Layer -Root $SourceRoot -Target $TargetRoot -Operation "Repair"
    }
    "Rollback" {
        [void](Rollback-OneManifest -Target $TargetRoot -ManifestPath $manifestPath -Operation "Rollback")
        Write-Output "Rollback completed."
    }
    "Uninstall" {
        $count = 0
        while (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
            $changed = Rollback-OneManifest -Target $TargetRoot -ManifestPath $manifestPath -Operation "Uninstall"
            if (-not $changed) {
                break
            }
            $count++
            if ($WhatIfPreference) {
                break
            }
        }
        Write-Output "Uninstall completed: $count installation layer(s) reverted."
    }
}
