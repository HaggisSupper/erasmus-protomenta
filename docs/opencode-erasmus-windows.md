# OpenCode Erasmus Windows Verification

This runbook verifies the repository-local OpenCode layer and the bounded global installation. It does not select a provider/model, write credentials, or mutate Erasmus database state.

All commands assume PowerShell at the repository root.

## Prerequisites

```powershell
python --version
opencode --version
```

Python must be 3.12 or newer. OpenCode must be installed independently through the operator's approved method.

## Validate repository discovery artifacts

```powershell
python scripts\validate_opencode_layer.py
# Expected: OpenCode layer: READY
```

This validates:

- `.opencode\agents\erasmus.md`;
- `.opencode\commands\*.md`;
- `.opencode\skills\*\SKILL.md`;
- `opencode.json`;
- `CONTEXT.md`;
- command-to-skill references;
- provider/model neutrality;
- authoritative runtime boundaries.

## Start the project agent

```powershell
opencode --agent erasmus
```

Inside OpenCode, enter `/` and confirm these commands are discoverable:

```text
/erasmus
/erasmus-setup
/erasmus-spec
/erasmus-implement
/erasmus-review
/erasmus-research
/erasmus-handoff
/erasmus-doctor
```

The skill tool should discover the versioned skills under `.opencode\skills`. A command loads exactly one named primary skill; supporting skills are loaded lazily by the workflow.

## Global install dry run

```powershell
pwsh -NoProfile -File install\Install-ErasmusOpenCode.ps1 `
  -Action Install `
  -WhatIf
```

The dry run must validate the source and create no files under `$HOME\.config\opencode`.

To exercise an isolated target rather than the real profile:

```powershell
$target = Join-Path $env:TEMP "erasmus-opencode-verification"
Remove-Item $target -Recurse -Force -ErrorAction SilentlyContinue

pwsh -NoProfile -File install\Install-ErasmusOpenCode.ps1 `
  -Action Install `
  -TargetRoot $target `
  -WhatIf

if (Test-Path $target) { throw "Dry run mutated the target" }
```

## Install and idempotency

```powershell
pwsh -NoProfile -File install\Install-ErasmusOpenCode.ps1 `
  -Action Install `
  -TargetRoot $target

Get-ChildItem $target -Recurse -File
Get-Content (Join-Path $target "erasmus-install-manifest.json")

$before = Get-FileHash (Join-Path $target "agents\erasmus.md")

pwsh -NoProfile -File install\Install-ErasmusOpenCode.ps1 `
  -Action Install `
  -TargetRoot $target

$after = Get-FileHash (Join-Path $target "agents\erasmus.md")
if ($before.Hash -ne $after.Hash) { throw "Idempotent install changed the agent" }
```

The second install should report that the layer is already current.

## Repair and latest-operation rollback

```powershell
$agent = Join-Path $target "agents\erasmus.md"
Set-Content -LiteralPath $agent -Value "operator-local-agent" -Encoding UTF8

pwsh -NoProfile -File install\Install-ErasmusOpenCode.ps1 `
  -Action Repair `
  -TargetRoot $target

Select-String -LiteralPath $agent -Pattern "primary OpenCode interaction agent"

pwsh -NoProfile -File install\Install-ErasmusOpenCode.ps1 `
  -Action Rollback `
  -TargetRoot $target

if ((Get-Content -LiteralPath $agent -Raw).Trim() -ne "operator-local-agent") {
  throw "Rollback did not restore the pre-repair file"
}
```

Rollback reverts only the latest recorded install or repair operation. It refuses to overwrite a file changed after that operation.

## Uninstall all recorded layers

```powershell
pwsh -NoProfile -File install\Install-ErasmusOpenCode.ps1 `
  -Action Uninstall `
  -TargetRoot $target
```

Uninstall follows the manifest chain to restore pre-existing files and remove only installation-created files whose digest still matches the installed artifact.

## Read-only doctor workflow

From the repository-local OpenCode session:

```text
/erasmus-doctor state\erasmus.db configs\local-runtime.example.json
```

Doctor may inspect:

- OpenCode layer validation;
- `erasmus status`;
- `erasmus integrity`;
- MCP initialize and tools/list;
- explicitly selected runtime configuration and versions;
- logs, locks, ports, and process evidence.

It must not install, migrate, restart, restore, delete, or alter provider credentials without separate approval.

## Automated verification

```powershell
python -m pytest tests\test_opencode_layer.py -v
powershell -ExecutionPolicy Bypass -File scripts\test.ps1
```

The focused test covers frontmatter, naming, duplicate detection, required boundaries, command references, provider/model pin rejection, installer dry-run, idempotency, repair, and rollback. The full script validates the OpenCode layer before running every repository test.

## Production global installation

After isolated verification:

```powershell
pwsh -NoProfile -File install\Install-ErasmusOpenCode.ps1 -Action Install
opencode --agent erasmus
```

The default target is `$HOME\.config\opencode`. The project `opencode.json` is intentionally not copied into the global directory, so repository-local instructions and operator-owned provider/model configuration remain separate.

## Rollback

```powershell
pwsh -NoProfile -File install\Install-ErasmusOpenCode.ps1 -Action Rollback
```

Use `Uninstall` only when all recorded Erasmus OpenCode installation layers should be removed. Neither action changes SQLite, model files, provider configuration, credentials, or Erasmus runtime state.
