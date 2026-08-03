# OpenCode Erasmus Skill Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a validated, installable OpenCode agent/command/skill layer that exposes focused Erasmus workflows while preserving the existing runtime as authoritative.

**Architecture:** Project-local OpenCode files provide immediate discovery and serve as the versioned source copied by a Windows global installer. A standard-library Python validator checks frontmatter, references, authority boundaries, and provider neutrality. Skills remain prose workflows; all persistent state and consequential operations remain behind existing typed Erasmus CLI/MCP/runtime interfaces.

**Tech Stack:** OpenCode Markdown agents/commands/skills, JSON project configuration, Python 3.12 standard library, pytest, PowerShell 7/Windows PowerShell.

## Global Constraints

- Python 3.12 or newer.
- No new runtime dependency.
- No Docker, Electron, npm package dependency, hosted skill marketplace, or new OAuth/provider dependency.
- Do not copy Matt Pocock's wording or branding; adapt only general engineering principles.
- No provider or model is pinned in the repository agent or project config.
- The Erasmus runtime remains authoritative for memory, mission, belief, evidence, authority, runtime state, and skill promotion.
- One bounded Issue #64 PR; no unrelated runtime or persistence changes.

---

### Task 1: Record the interaction-layer boundary

**Files:**
- Create: `CONTEXT.md`
- Create: `docs/adr/ADR-AGENT-001-opencode-skill-layer.md`
- Modify: `AGENTS.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: existing constitution, architecture, CLI/MCP commands, and Issue #64.
- Produces: stable vocabulary and the authoritative boundary consumed by every agent and skill.

- [ ] **Step 1: Add `CONTEXT.md`** with concise definitions and links to authoritative documents.
- [ ] **Step 2: Add the accepted ADR** recording commands-for-human-invocation and skills-for-reusable-discipline.
- [ ] **Step 3: Append an `OpenCode interaction layer` section to `AGENTS.md`** requiring lazy skill loading and typed runtime calls.
- [ ] **Step 4: Add README usage** for `opencode --agent erasmus`, slash commands, validation, and installation.
- [ ] **Step 5: Run document checks** with `git diff --check` and confirm no duplicated authority source was introduced.
- [ ] **Step 6: Commit** with `docs: define OpenCode interaction boundary`.

### Task 2: Add the primary Erasmus agent and project config

**Files:**
- Create: `.opencode/agents/erasmus.md`
- Create: `opencode.json`

**Interfaces:**
- Consumes: `CONTEXT.md`, `AGENTS.md`, immutable contract, existing OpenCode skill tool.
- Produces: selectable primary agent `erasmus` and explicit project skill permissions.

- [ ] **Step 1: Write `.opencode/agents/erasmus.md`** with `mode: primary`, no model, `skill: allow`, read permissions allowed, edits/shell/external access/subtasks set to `ask`, and external-directory access denied.
- [ ] **Step 2: Write `opencode.json`** loading `CONTEXT.md`, the immutable contract, and architecture while allowing skills and pinning no provider/model.
- [ ] **Step 3: Verify JSON** using `python -m json.tool opencode.json`.
- [ ] **Step 4: Commit** with `feat: add provider-neutral Erasmus OpenCode agent`.

### Task 3: Add reusable core skills

**Files:**
- Create: `.opencode/skills/erasmus-router/SKILL.md`
- Create: `.opencode/skills/erasmus-setup/SKILL.md`
- Create: `.opencode/skills/erasmus-domain-model/SKILL.md`
- Create: `.opencode/skills/erasmus-spec/SKILL.md`
- Create: `.opencode/skills/erasmus-implement/SKILL.md`
- Create: `.opencode/skills/erasmus-tdd/SKILL.md`
- Create: `.opencode/skills/erasmus-diagnose/SKILL.md`
- Create: `.opencode/skills/erasmus-research/SKILL.md`
- Create: `.opencode/skills/erasmus-code-review/SKILL.md`
- Create: `.opencode/skills/erasmus-handoff/SKILL.md`

**Interfaces:**
- Consumes: typed Erasmus CLI/MCP operations, project rules, issue/spec/plan artifacts.
- Produces: native on-demand OpenCode skills with consistent sections and stop conditions.

- [ ] **Step 1: Create each skill with recognized frontmatter only:** `name`, `description`, optional `compatibility`.
- [ ] **Step 2: Include required sections in every skill:** Trigger, Authority boundary, Deterministic evidence, Workflow, Output artifact, Stop condition.
- [ ] **Step 3: State exactly `The Erasmus runtime remains authoritative.` in every authority boundary.
- [ ] **Step 4: Keep workflows small and composable; reference another skill by name rather than duplicating its procedure.
- [ ] **Step 5: Commit** with `feat: add composable Erasmus OpenCode skills`.

### Task 4: Add explicit slash-command entry points

**Files:**
- Create: `.opencode/commands/erasmus.md`
- Create: `.opencode/commands/erasmus-setup.md`
- Create: `.opencode/commands/erasmus-spec.md`
- Create: `.opencode/commands/erasmus-implement.md`
- Create: `.opencode/commands/erasmus-review.md`
- Create: `.opencode/commands/erasmus-research.md`
- Create: `.opencode/commands/erasmus-handoff.md`
- Create: `.opencode/commands/erasmus-doctor.md`

**Interfaces:**
- Consumes: skills from Task 3.
- Produces: user-controlled workflows discoverable through OpenCode `/` commands.

- [ ] **Step 1: Add command frontmatter** with `description` and `agent: erasmus`; use `subtask: true` only for research/review where context isolation is useful.
- [ ] **Step 2: Use the exact reference sentence** `Load the OpenCode skill named `<skill-name>` and follow it.` for validator discovery.
- [ ] **Step 3: Ensure `/erasmus-doctor` remains read-only** and calls existing `erasmus status`, `erasmus integrity`, MCP initialize/tools-list, and runtime validation where configured.
- [ ] **Step 4: Commit** with `feat: add Erasmus OpenCode slash commands`.

### Task 5: Implement deterministic OpenCode-layer validation

**Files:**
- Create: `src/erasmus/opencode_layer.py`
- Create: `scripts/validate_opencode_layer.py`
- Create: `tests/test_opencode_layer.py`

**Interfaces:**
- Produces:
  - `parse_frontmatter(text: str) -> tuple[dict[str, object], str]`
  - `validate_opencode_layer(root: Path) -> tuple[str, ...]`
  - `main(argv: Sequence[str] | None = None) -> int`

- [ ] **Step 1: Write failing tests** for the valid repository layer and each required invalid fixture.
- [ ] **Step 2: Run** `python -m pytest tests/test_opencode_layer.py -v` and verify failures identify missing implementation.
- [ ] **Step 3: Implement a bounded frontmatter parser** supporting scalars and one nested mapping, with explicit parse errors.
- [ ] **Step 4: Implement skill validation** for allowed fields, name regex, directory equality, duplicate names, descriptions, sections, and authority phrase.
- [ ] **Step 5: Implement command validation** for allowed fields and referenced-skill existence.
- [ ] **Step 6: Implement agent/config validation** for primary mode, skill permission, and absence of model/provider pinning.
- [ ] **Step 7: Add CLI output**: sorted errors to stderr and exit `1`; `OpenCode layer: READY` and exit `0` on success.
- [ ] **Step 8: Run focused tests** and confirm all pass.
- [ ] **Step 9: Commit** with `feat: validate OpenCode Erasmus layer`.

### Task 6: Add the idempotent global PowerShell installer

**Files:**
- Create: `install/Install-ErasmusOpenCode.ps1`
- Extend: `tests/test_opencode_layer.py`

**Interfaces:**
- Consumes: project `.opencode/agents`, `.opencode/skills`, `.opencode/commands`.
- Produces: global OpenCode files and `erasmus-install-manifest.json` under the selected target root.

- [ ] **Step 1: Write installer contract tests** for dry-run, install, idempotency, repair/backup, rollback, and source-validation failure.
- [ ] **Step 2: Implement `SupportsShouldProcess`** and `Action` values `Install`, `Repair`, `Rollback`, `Uninstall`.
- [ ] **Step 3: Validate source artifacts** by running `scripts/validate_opencode_layer.py` before any mutation.
- [ ] **Step 4: Implement SHA-256 comparison, timestamped backup, atomic copy through a temporary file, and manifest writing.
- [ ] **Step 5: Implement rollback** restoring backups and deleting only files whose manifest records `created_by_install: true`.
- [ ] **Step 6: Run PowerShell tests** on available Windows/PowerShell environments; skip with an explicit reason only where no PowerShell executable exists.
- [ ] **Step 7: Commit** with `feat: install Erasmus OpenCode layer globally`.

### Task 7: Wire CI and Windows verification

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `scripts/test.ps1`
- Modify: `docs/runbook-windows.md`

**Interfaces:**
- Consumes: validator and installer.
- Produces: exact-head Windows/Ubuntu evidence and operator verification commands.

- [ ] **Step 1: Add `python scripts/validate_opencode_layer.py` to CI** before the full pytest run.
- [ ] **Step 2: Add the validator to `scripts/test.ps1`** and preserve existing failure behavior.
- [ ] **Step 3: Document project discovery, global install dry-run, install, repair, doctor, rollback, and uninstall commands.
- [ ] **Step 4: Run** `python scripts/validate_opencode_layer.py`.
- [ ] **Step 5: Run** `python -m pytest tests/test_opencode_layer.py -v`.
- [ ] **Step 6: Run** `python -m pytest tests/ -q`.
- [ ] **Step 7: Run** `git diff --check`.
- [ ] **Step 8: Commit** with `ci: verify OpenCode Erasmus layer`.

### Task 8: Final review and PR

**Files:**
- Review all Issue #64 files.

**Interfaces:**
- Produces: one reviewable PR linked to Issue #64.

- [ ] **Step 1: Inspect changed paths** and reject any runtime, migration, provider, model, OAuth, Docker, Electron, or unrelated routing change.
- [ ] **Step 2: Verify no copied branding or text** from the comparison repository.
- [ ] **Step 3: Confirm every command references an existing skill and every skill identifies a concrete failure it prevents.
- [ ] **Step 4: Record tests, dependencies, limitations, rollback, exact head SHA, and 10th-Man countercase in the PR body.
- [ ] **Step 5: Open the PR; do not merge until exact-head Windows and Ubuntu CI and independent review pass.

## Plan self-review

- All Issue #64 requirements map to Tasks 1–8.
- No persistent schema or runtime behavior is changed.
- Provider/model selection remains operator-owned.
- User invocation is implemented through commands, avoiding unsupported skill frontmatter.
- Deterministic validation and installer rollback are explicit.
- No placeholder or deferred implementation step remains in this plan.