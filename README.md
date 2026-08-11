# Erasmus–Protomentat

A personal-first, persistent cognitive system for a human–AI partnership.

The system combines bounded conversational continuity, deterministic-first capabilities, an epistemic ledger, sleep consolidation, mission execution, and a 10th-Man cognitive immune system.

## Core separations

- **RAG** preserves explicit memory and evidence.
- **Ledger** preserves current propositions, confidence, contradictions, and tangible wrongness.
- **Sleep** integrates session experience.
- **Skills and LoRA** preserve validated adaptive intelligence.
- **10th-Man immunity** detects divergence and prevents shared hallucination.
- **Mission engine** converts cognition into bounded execution.
- **OKF Knowledge Foundry** converts PDF source folders into provenance-bearing draft OKF v0.2 candidate bundles without promoting them into canonical knowledge.

## OpenCode Erasmus layer

The repository includes a provider-neutral OpenCode agent, explicit slash commands, and small composable skills. These files are a thin interaction layer over the real Erasmus CLI, MCP server, SQLite stores, and governed runtime.

From the repository root:

```powershell
python scripts\validate_opencode_layer.py
opencode --agent erasmus
```

Inside OpenCode, use:

- `/erasmus` — route a request to the smallest applicable workflow;
- `/erasmus-setup` — configure a repository without overwriting local instructions;
- `/erasmus-spec` — write a bounded specification;
- `/erasmus-implement` — execute an approved plan;
- `/erasmus-review` — independently review an exact diff;
- `/erasmus-research` — produce a bounded cited research note;
- `/erasmus-handoff` — capture objective continuation state;
- `/erasmus-doctor` — inspect the local interaction and runtime surfaces without mutation.

To install the versioned agent, commands, and skills into the current user's global OpenCode configuration:

```powershell
pwsh -NoProfile -File install\Install-ErasmusOpenCode.ps1 -Action Install -WhatIf
pwsh -NoProfile -File install\Install-ErasmusOpenCode.ps1 -Action Install
```

The installer does not copy project `opencode.json`, choose a provider/model, or write credentials. Use `-Action Repair`, `Rollback`, or `Uninstall` for the corresponding bounded operation.

## Commands

### Core runtime

- `erasmus init` — apply schema migrations and initialise the database
- `erasmus status` — table row counts and applied schema versions
- `erasmus integrity` — run `PRAGMA integrity_check`
- `erasmus checkpoint` — JSON-dump the latest committed checkpoint
- `erasmus backup <dest>` — hot-backup the database to a file
- `erasmus restore <src>` — restore from a backup file

### Runtime and sleep

- `erasmus runtime-validate <config>` — validate a local endpoint configuration
- `erasmus runtime-discover <config>` — list models and advertised capabilities
- `erasmus runtime-smoke <config> --prompt "hello"` — run one bounded local session
- `erasmus runtime-embed <config> "text"` — request embeddings when advertised
- `erasmus sleep` — consolidate events into experience candidates (idempotent)
- `erasmus sleep-report <run-id>` — inspect classifications, reasons, and stage history
- `erasmus sleep-decide <candidate-id> <decision> <target> <evidence-id> --actor ... --authority ... --reason ...`

### Missions

- `erasmus mission-create --contract ... --title ... --objective ...`
- `erasmus mission-inspect <mission-id>`
- `erasmus mission-authorize <mission-id> --actor ... --evidence ... --approval-id ... --deny`
- `erasmus mission-run-one <mission-id>`
- `erasmus mission-pause|mission-resume|mission-cancel|mission-rollback <mission-id>`

### Governance, evidence, and cognition

- `erasmus review --proposition "..."` — run the 10th-Man review pathway for a proposition
- `erasmus immune-process <event.json> --authority ...`
- `erasmus immune-inspect <incident-id>` — inspect incidents and dormant state
- `erasmus immune-agents` — list inactive immune agents
- `erasmus immune-false-positive <incident-id> <detector> --reason ... --actor ... --authority ...`
- `erasmus immune-retire <agent-id> --reason ... --actor ... --authority ...`
- `erasmus divergence-calibrate <baseline> <detector> <kind> <threshold> --actor ... --reason ...`
- `erasmus divergence-evaluate <fixtures> [--calibration ...] --authority ...`
- `erasmus divergence-downweight <calibration-id> --recommendation ... --actor ... --reason ... --authority ...`
- `erasmus skill-observe <candidate-id> <source-event-id> <evidence-id> ...`
- `erasmus skill-promote <candidate-id> <target> ...`
- `erasmus skill-draft <candidate-id> <document> ...`
- `erasmus skill-evaluate <candidate-id> <fixtures> ...`
- `erasmus skill-inspect <candidate-id>`
- `erasmus skill-export --actor ... --authority ...`
- `erasmus ledger-evidence-add ...`
- `erasmus ledger-propose <statement> <evidence-id> ...`
- `erasmus ledger-transition <proposition-id> <operation> <evidence-id> ...`
- `erasmus ledger-confidence <proposition-id> <confidence> <evidence-id> ...`
- `erasmus ledger-supersede <proposition-id> <replacement-id> <evidence-id> ...`
- `erasmus ledger-inspect <proposition-id>` / `ledger-query <proposition-id>`

### Graph and toolchain

- `erasmus graph-validate <manifest>` / `graph-import <manifest>` / `graph-list`
- `erasmus graph-inspect <capability>` / `graph-plan <goal> [--authority ...]` / `graph-export <dest>`
- `erasmus bootstrap-validate <fixture>` / `bootstrap-resolve <fixture>`
- `erasmus toolchain-validate [document] [--manifests tools/manifests]`
- `erasmus tool-publisher-register <publishers>`
- `erasmus tool-register <manifest>`
- `erasmus tool-verify <manifest> <artifact>`
- `erasmus tool-install <manifest> <artifact>`
- `erasmus tool-list`
- `erasmus tool-inspect <tool-id> <version> <target>`
- `erasmus tool-activate|tool-deactivate|tool-quarantine|tool-revoke|tool-uninstall <tool-id> <version> <target>`
- `erasmus tool-execute <capability-id> <capability-version> <target> [args...]`
- `erasmus tool-health <tool-id> <version> <target> --authority ...`
- `erasmus tool-export <dest>`

### OKF foundry

- `erasmus-foundry build <pdf-folder> <candidate-bundle> <runtime-config>`
- `erasmus-foundry validate <candidate-bundle> --write-report`

The knowledge-system command namespace shown in [`docs/architecture/knowledge-system/OPERATOR_API_AND_RUNBOOK.md`](docs/architecture/knowledge-system/OPERATOR_API_AND_RUNBOOK.md) is design-only and not available as runtime CLI today.

The foundry deliberately stops at **draft candidates**: it does not write ledger propositions, verify concepts, reconcile contradictions, build indexes, or silently grant authority. See [`docs/architecture/okf-knowledge-foundry.md`](docs/architecture/okf-knowledge-foundry.md).

See [`docs/runbook-windows.md`](docs/runbook-windows.md) for PowerShell verification commands.

## Status

This repository is an implementable experimental kernel. It is personal-first but contract-shaped so it can later evolve into isolated dyadic deployments.

See `docs/DEVELOPMENT_TRACK.md` for the locked phased architecture and scope boundaries.
