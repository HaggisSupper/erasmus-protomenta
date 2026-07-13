# Purpose and scope

This is the human review surface for the local deterministic tool registry. Signed manifests and SQLite registry state are authoritative; this document cannot override them.

# Deterministic-first policy

Use a registered deterministic tool before inference when it can establish the claim at reasonable cost. Inference cannot register, activate, revoke, or execute tools.

# Supported platforms

The initial target is `any-py3-none` on Windows and CI-supported Linux, using one local process and SQLite database. No Docker, daemon, remote execution, or updater is permitted.

# Runtime priorities

Rust single-file binaries are preferred when they exist. The bounded vertical slice uses Python `>=3.12,<3.13`; execution uses the current governed environment's exact interpreter, never an executable discovered through `PATH`.

# Governed tools

| Tool | Capability | Manifest | Digest | Source commit |
|---|---|---|---|---|
| pytest_runner 1.0.0 | run_tests@1.0.0 | tools/manifests/pytest_runner.json | 3737eba08a05b190f5049829eb3ab62d6a2c2cb91f0f253f7db58ebaa549594c | d43372d7f6925845b903bf8c411ed1c5a1565e0c |
| sqlite_reader 1.0.0 | query_sqlite@1.0.0 | tools/manifests/sqlite_reader.json | ca75383ccfeb79013c052d00241ef7351518bfbf9999644859c73ca759366973 | d43372d7f6925845b903bf8c411ed1c5a1565e0c |

Both manifests are signed by `erasmus-release-2026-01`; the corresponding public key is in `tools/publishers.json`.

# Lifecycle state

Canonical manifests are candidates until their signature and artifact digest are verified locally. The registry records candidate, verified, active, quarantined, deprecated, and revoked states. Only one active implementation may resolve a capability version and target.

# Operations

Register the trusted publisher, register manifests, verify exact artifacts, install to the content-addressed cache, activate, health-check or execute, then quarantine/revoke and uninstall when required. Every transition and execution is append-only audited. Activation rollback selects the previously verified version; uninstall preserves manifests and audit history.

# Trust boundaries

`PATH`, environment variables, network locations, model output, and external publisher claims are untrusted. Artifact identity is SHA-256 plus an Ed25519-signed manifest. A valid signature does not grant capability authority. Private signing keys and secrets must never enter the repository or registry.

# Cache and registry

The default registry is `state/erasmus.db`. The cache is `state/tool-cache/<sha256>/<target>/<artifact>` and contains no secrets. Manifests under `tools/manifests` and publisher public keys under `tools/publishers.json` rebuild registry metadata.

# Verification

Run `python -m pytest tests/test_tool_registry.py -v` and the commands in `docs/runbook-windows.md`. CI runs the full suite on Windows and Linux. Health checks execute the cached artifact only after signature, digest, target, capability, authority, lifecycle, and side-effect checks pass.

# Exceptions and waivers

No exceptions or waivers are active. Any future waiver requires an owner, approval record, reason, and expiry date.

# Contract relationships

`AGENTS.md` and the immutable contract govern authority. The OKF capability bundle declares permitted implementation IDs. Tool manifests bind exact artifacts to those capability versions. Execution evidence records the resolved tool version, digest, result, and authority used.

# 10th-Man countercase

Signed and hashed artifacts can still contain deterministic defects or malicious source. Preserve independent tests, source provenance, quarantine, revocation, least authority, and human escalation.
