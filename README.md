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

- `erasmus init` — apply schema migrations and initialise the database
- `erasmus status` — table row counts and applied schema versions
- `erasmus mission-create --title "..." --objective "..."`
- `erasmus sleep` — consolidate events into experience candidates (idempotent)
- `erasmus sleep-report <run-id>` — inspect classifications, reasons, and stage history
- `erasmus sleep-decide ...` — record an evidence-backed belief or skill decision
- `erasmus checkpoint` — JSON-dump the latest committed checkpoint
- `erasmus runtime-validate configs/local-runtime.example.json` — validate a local endpoint configuration
- `erasmus runtime-discover configs/local-runtime.example.json` — list models and advertised capabilities
- `erasmus runtime-smoke configs/local-runtime.example.json --prompt "hello"` — run one bounded, provenance-aware local session
- `erasmus runtime-embed configs/local-runtime.example.json "text"` — request embeddings when advertised
- `erasmus ledger-evidence-add ...` — append provenance-bearing evidence
- `erasmus ledger-propose ...` / `ledger-transition ...` — make explicit belief changes
- `erasmus ledger-inspect <id>` / `ledger-query <id>` — inspect history and evidence
- `erasmus immune-process <event.json> --authority immune:inspect` — run the immune cascade
- `erasmus immune-inspect <id>` / `immune-agents` — inspect incidents and dormant state
- `erasmus divergence-calibrate ...` / `divergence-evaluate ...` — calibrate and evaluate inspectable divergence detectors
- `erasmus skill-inspect <candidate-id>` / `skill-export ...` — inspect promoted skills and adapter readiness
- `erasmus integrity` — run `PRAGMA integrity_check`
- `erasmus backup <dest>` — hot-backup the database to a file
- `erasmus restore <src>` — restore from a backup file
- `erasmus review --proposition "..."`

See [`docs/runbook-windows.md`](docs/runbook-windows.md) for PowerShell verification commands.

## Status

This repository is an implementable experimental kernel. It is personal-first but contract-shaped so it can later evolve into isolated dyadic deployments.

See `docs/DEVELOPMENT_TRACK.md` for the locked phased architecture and scope boundaries.
