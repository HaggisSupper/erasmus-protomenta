# Hosted builds

Project builds run in GitHub Actions on GitHub-hosted runners. Local checkout is
for editing and read-only inspection; compilation, dependency installation that
builds project code, packaging, and required verification run in hosted CI.

## Workflows

The hosted workflow entry points are:

- `.github/workflows/ci.yml`
- `.github/workflows/opencode.yml`

Use the workflow appropriate to the changed component and target operating
system. Existing source filters, pull-request triggers, and release triggers
continue to apply. Manual dispatch is available where the workflow declares
`workflow_dispatch`; otherwise use its documented push or pull-request trigger.

## Run and inspect on GitHub

Open [Actions](https://github.com/HaggisSupper/erasmus-protomenta/actions), or inspect the
workflow list with:

```shell
gh workflow list --repo HaggisSupper/erasmus-protomenta
gh run list --repo HaggisSupper/erasmus-protomenta
gh run view RUN_ID --repo HaggisSupper/erasmus-protomenta --log-failed
gh run download RUN_ID --repo HaggisSupper/erasmus-protomenta
```

For a workflow with manual dispatch, use `gh workflow run WORKFLOW_FILE --repo
HaggisSupper/erasmus-protomenta --ref BRANCH`. Dispatching a build, reading logs, and
downloading its artifacts do not run a project build locally.

## Verification and blockers

Keep required security, lint, type-check, test, and build checks in CI. Inspect
the actual conclusion and uploaded artifacts before claiming a build passed.
A configuration audit alone is not evidence that the project compiles.

If a gate needs licensed software, private credentials, unavailable hardware,
or another capability absent from the selected hosted runner, leave the gate
explicit and report the unmet prerequisite. Do not use a local build, a
self-hosted runner, a skipped required check, or a placeholder success as a
substitute. This build-location policy does not change application runtime
privacy or the location of user data.
