# Erasmus–Protomentat

A personal, persistent cognitive system for Scott and Erasmus.

The system combines bounded conversational continuity, deterministic-first capabilities, an epistemic ledger, sleep consolidation, mission execution, and a 10th-Man cognitive immune system.

## Core separations

- **RAG** preserves explicit memory and evidence.
- **Ledger** preserves current propositions, confidence, contradictions, and tangible wrongness.
- **Sleep** integrates session experience.
- **Skills and LoRA** preserve validated adaptive intelligence.
- **10th-Man immunity** detects divergence and prevents shared hallucination.
- **Mission engine** converts cognition into bounded execution.

## Commands

- `erasmus init` — apply schema migrations and initialise the database
- `erasmus status` — table row counts and applied schema versions
- `erasmus mission-create --title "..." --objective "..."`
- `erasmus sleep` — consolidate events into experience candidates (idempotent)
- `erasmus checkpoint` — JSON-dump the latest committed checkpoint
- `erasmus integrity` — run `PRAGMA integrity_check`
- `erasmus backup <dest>` — hot-backup the database to a file
- `erasmus restore <src>` — restore from a backup file
- `erasmus review --proposition "..."`

See [`docs/runbook-windows.md`](docs/runbook-windows.md) for PowerShell verification commands.

## Status

This repository is an implementable experimental kernel. It is personal-first but contract-shaped so it can later evolve into isolated dyadic deployments.
