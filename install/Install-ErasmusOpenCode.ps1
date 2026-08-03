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

function Test-PathWithinRoot {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Candidate
    )

    $rootFull = Get-FullPath $Root
    $candidateFull = Get-FullPath $Candidate
    $comparison = [System.StringComparison]::Ordinal
    if ([System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT) {
        $comparison = [System.StringComparison]::OrdinalIgnoreCase
    }
    if ($candidateFull.Equals($rootFull, $comparison)) {
        return $true
    }
    $trimChars = [char[]]@(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )
    $prefix = $rootFull.TrimEnd($trimChars) + [System.IO.Path]::DirectorySeparatorChar
    return $candidateFull.StartsWith($prefix, $comparison)
}

function Resolve-SafeRelativePath {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$RelativePath
    )

    if ([string]::IsNullOrWhiteSpace($RelativePath) -or [System.IO.Path]::IsPathRooted($RelativePath)) {
        throw "Manifest relative path must be a non-empty relative path: $RelativePath"
    }
    $nativeRelative = $RelativePath.Replace("/", [System.IO.Path]::DirectorySeparatorChar)
    $candidate = Get-FullPath (Join-Path $Root $nativeRelative)
    if (-not (Test-PathWithinRoot -Root $Root -Candidate $candidate) -or $candidate -eq (Get-FullPath $Root)) {
        throw "Manifest relative path escapes the OpenCode target root: $RelativePath"
    }
    return $candidate
}

function Assert-SafeBackupPath {
    param(
        [Parameter(Mandatory = $true)][string]$Target,
        [Parameter(Mandatory = $true)][string]$BackupPath
    )

    $backupRoot = Get-FullPath (Join-Path $Target ".erasmus-backups")
    if (-not (Test-PathWithinRoot -Root $backupRoot -Candidate $BackupPath)) {
        throw "Manifest backup path escapes the Erasmus backup root: $BackupPath"
    }
}

function Get-Sha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Convert-RelativePathToNative {
    param([Parameter(Mandatory = $true)][string]$Path)
    return $Path.Replace("/", [System.IO.Path]::DirectorySeparatorChar)
}

function Ensure-ParentDirectory {
    param([Parameter(Mandatory = $true)][string]$Path)
    $directory = Split-Path -Parent $Path
    if (-not [string]::IsNullOrWhiteSpace($directory) -and -not (Test-Path -LiteralPath $directory)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }
}

function Copy-FileAtomically {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )

    Ensure-ParentDirectory $Destination
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

    Ensure-ParentDirectory $Destination
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

function Get-InstallMutations {
    param(
        [Parameter(Mandatory = $true)][object[]]$SourceEntries,
        [Parameter(Mandatory = $true)][string]$Target,
        [Parameter(Mandatory = $true)][string]$BackupRoot
    )

    $mutations = @()
    foreach ($sourceEntry in $SourceEntries) {
        $destination = Resolve-SafeRelativePath `
            -Root $Target `
            -RelativePath ([string]$sourceEntry.relative_path)
        $exists = Test-Path -LiteralPath $destination -PathType Leaf
        if ($exists -and (Get-Sha256 $destination) -eq $sourceEntry.source_sha256) {
            continue
        }

        $backupPath = $null
        if ($exists) {
            $nativeRelative = Convert-RelativePathToNative $sourceEntry.relative_path
            $backupPath = Join-Path $BackupRoot $nativeRelative
        }

        $mutations += [PSCustomObject]@{
            source_path = $sourceEntry.source_path
            relative_path = $sourceEntry.relative_path
            source_sha256 = $sourceEntry.source_sha256
            target_path = $destination
            created_by_install = -not $exists
            backup_path = $backupPath
        }
    }
    return @($mutations)
}

function Restore-InstallTransaction {
    param(
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][object[]]$Completed,
        [Parameter(Mandatory = $true)][string]$ManifestPath,
        [AllowNull()][string]$PreviousManifestBackup
    )

    for ($index = $Completed.Count - 1; $index -ge 0; $index--) {
        $mutation = $Completed[$index]
        if (-not [string]::IsNullOrWhiteSpace([string]$mutation.backup_path)) {
            Copy-FileAtomically -Source $mutation.backup_path -Destination $mutation.target_path
        }
        elseif ([bool]$mutation.created_by_install -and (Test-Path -LiteralPath $mutation.target_path -PathType Leaf)) {
            Remove-Item -LiteralPath $mutation.target_path -Force
        }
    }

    if (-not [string]::IsNullOrWhiteSpace($PreviousManifestBackup)) {
        Copy-FileAtomically -Source $PreviousManifestBackup -Destination $ManifestPath
    }
    elseif (Test-Path -LiteralPath $ManifestPath -PathType Leaf) {
        Remove-Item -LiteralPath $ManifestPath -Force
    }
}

function Install-Layer {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Target,
        [Parameter(Mandatory = $true)][string]$Operation
    )

    Assert-ValidSourceLayer $Root
    $sourceEntries = @(Get-SourceEntries $Root)
    $manifestPath = Join-Path $Target "erasmus-install-manifest.json"
    $timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssfffffffZ")
    $backupRoot = Join-Path $Target ".erasmus-backups\$timestamp"
    $mutations = @(
        Get-InstallMutations `
            -SourceEntries $sourceEntries `
            -Target $Target `
            -BackupRoot $backupRoot
    )

    if ($mutations.Count -eq 0) {
        Write-Output "Erasmus OpenCode layer is already current."
        return
    }

    $description = "$Operation $($mutations.Count) OpenCode interaction file(s)"
    if (-not $PSCmdlet.ShouldProcess($Target, $description)) {
        return
    }

    $previousManifestBackup = $null
    if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
        $previousManifestBackup = Join-Path $backupRoot "erasmus-install-manifest.previous.json"
    }

    # Complete every backup before mutating any target file.
    if ($null -ne $previousManifestBackup) {
        Copy-FileAtomically -Source $manifestPath -Destination $previousManifestBackup
    }
    foreach ($mutation in $mutations) {
        if (-not [string]::IsNullOrWhiteSpace([string]$mutation.backup_path)) {
            Copy-FileAtomically -Source $mutation.target_path -Destination $mutation.backup_path
        }
    }

    $completed = @()
    try {
        foreach ($mutation in $mutations) {
            Copy-FileAtomically -Source $mutation.source_path -Destination $mutation.target_path
            $completed += $mutation
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
        Write-JsonAtomically -Value $manifest -Destination $manifestPath
    }
    catch {
        Restore-InstallTransaction `
            -Completed $completed `
            -ManifestPath $manifestPath `
            -PreviousManifestBackup $previousManifestBackup
        throw
    }

    Write-Output "$Operation completed: $($mutations.Count) file(s) changed."
}

function Read-Manifest {
    param([Parameter(Mandatory = $true)][string]$ManifestPath)

    if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
        throw "Erasmus install manifest not found: $ManifestPath"
    }
    $manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($null -eq $manifest.schema_version -or [int]$manifest.schema_version -ne 1) {
        throw "Unsupported Erasmus install manifest schema version."
    }
    if ($null -eq $manifest.entries) {
        throw "Erasmus install manifest has no entries."
    }
    return $manifest
}

function Get-RollbackPlan {
    param(
        [Parameter(Mandatory = $true)][object]$Manifest,
        [Parameter(Mandatory = $true)][string]$Target
    )

    $plan = @()
    foreach ($entry in @($Manifest.entries)) {
        $relativePath = [string]$entry.relative_path
        $destination = Resolve-SafeRelativePath -Root $Target -RelativePath $relativePath
        $installedSha = [string]$entry.installed_sha256
        if ($installedSha -notmatch "^[0-9a-f]{64}$") {
            throw "Manifest entry has an invalid SHA-256 digest: $relativePath"
        }
        $exists = Test-Path -LiteralPath $destination -PathType Leaf
        if ($exists -and (Get-Sha256 $destination) -ne $installedSha) {
            throw "Refusing to overwrite or remove modified file during rollback: $destination"
        }

        $backupPath = [string]$entry.backup_path
        if (-not [string]::IsNullOrWhiteSpace($backupPath)) {
            Assert-SafeBackupPath -Target $Target -BackupPath $backupPath
            if (-not (Test-Path -LiteralPath $backupPath -PathType Leaf)) {
                throw "Required rollback backup is missing: $backupPath"
            }
        }

        $plan += [PSCustomObject]@{
            destination = $destination
            existed_before_rollback = $exists
            backup_path = $backupPath
            created_by_install = [bool]$entry.created_by_install
        }
    }
    return @($plan)
}

function Restore-RollbackTransaction {
    param(
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][object[]]$Plan,
        [Parameter(Mandatory = $true)][string]$Target,
        [Parameter(Mandatory = $true)][string]$TransactionRoot,
        [Parameter(Mandatory = $true)][string]$ManifestPath,
        [Parameter(Mandatory = $true)][string]$ManifestTransactionBackup
    )

    foreach ($item in $Plan) {
        $relative = $item.destination.Substring($Target.Length).TrimStart("\", "/")
        $transactionCopy = Join-Path $TransactionRoot $relative
        if ([bool]$item.existed_before_rollback) {
            Copy-FileAtomically -Source $transactionCopy -Destination $item.destination
        }
        elseif (Test-Path -LiteralPath $item.destination -PathType Leaf) {
            Remove-Item -LiteralPath $item.destination -Force
        }
    }
    Copy-FileAtomically -Source $ManifestTransactionBackup -Destination $ManifestPath
}

function Rollback-OneManifest {
    param(
        [Parameter(Mandatory = $true)][string]$Target,
        [Parameter(Mandatory = $true)][string]$ManifestPath,
        [Parameter(Mandatory = $true)][string]$Operation
    )

    $manifest = Read-Manifest $ManifestPath
    $plan = @(Get-RollbackPlan -Manifest $manifest -Target $Target)
    $previousManifest = [string]$manifest.previous_manifest_backup
    if (-not [string]::IsNullOrWhiteSpace($previousManifest)) {
        Assert-SafeBackupPath -Target $Target -BackupPath $previousManifest
        if (-not (Test-Path -LiteralPath $previousManifest -PathType Leaf)) {
            throw "Previous install manifest backup is missing: $previousManifest"
        }
    }

    if (-not $PSCmdlet.ShouldProcess($Target, "$Operation the latest Erasmus OpenCode installation layer")) {
        return $false
    }

    $timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssfffffffZ")
    $transactionRoot = Join-Path $Target ".erasmus-backups\rollback-$timestamp"
    $manifestTransactionBackup = Join-Path $transactionRoot "erasmus-install-manifest.current.json"
    Copy-FileAtomically -Source $ManifestPath -Destination $manifestTransactionBackup
    foreach ($item in $plan) {
        if ([bool]$item.existed_before_rollback) {
            $relative = $item.destination.Substring($Target.Length).TrimStart("\", "/")
            Copy-FileAtomically `
                -Source $item.destination `
                -Destination (Join-Path $transactionRoot $relative)
        }
    }

    try {
        for ($index = $plan.Count - 1; $index -ge 0; $index--) {
            $item = $plan[$index]
            if (-not [string]::IsNullOrWhiteSpace([string]$item.backup_path)) {
                Copy-FileAtomically -Source $item.backup_path -Destination $item.destination
            }
            elseif ([bool]$item.created_by_install -and (Test-Path -LiteralPath $item.destination -PathType Leaf)) {
                Remove-Item -LiteralPath $item.destination -Force
            }
        }

        if (-not [string]::IsNullOrWhiteSpace($previousManifest)) {
            Copy-FileAtomically -Source $previousManifest -Destination $ManifestPath
        }
        elseif (Test-Path -LiteralPath $ManifestPath -PathType Leaf) {
            Remove-Item -LiteralPath $ManifestPath -Force
        }
    }
    catch {
        Restore-RollbackTransaction `
            -Plan $plan `
            -Target $Target `
            -TransactionRoot $transactionRoot `
            -ManifestPath $ManifestPath `
            -ManifestTransactionBackup $manifestTransactionBackup
        throw
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
        $changed = Rollback-OneManifest -Target $TargetRoot -ManifestPath $manifestPath -Operation "Rollback"
        if ($changed) {
            Write-Output "Rollback completed."
        }
    }
    "Uninstall" {
        $count = 0
        while (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
            $changed = Rollback-OneManifest -Target $TargetRoot -ManifestPath $manifestPath -Operation "Uninstall"
            if (-not $changed) {
                break
            }
            $count++
        }
        Write-Output "Uninstall completed: $count installation layer(s) reverted."
    }
}
