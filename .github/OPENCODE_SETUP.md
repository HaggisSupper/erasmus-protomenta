# OpenCode GitHub Agent — BYOK activation

The workflow is installed at `.github/workflows/opencode.yml` and uses GitHub's built-in `GITHUB_TOKEN`; the OpenCode GitHub App is therefore optional.

## Required repository settings

In **Settings → Secrets and variables → Actions**:

1. Add repository secret `OPENROUTER_API_KEY` containing the OpenRouter API key.
2. Add repository variable `OPENCODE_MODEL` containing a full OpenCode model identifier in `provider/model` form.

Example model identifiers should be selected from the current OpenCode/OpenRouter model list rather than copied blindly, because provider model IDs change.

## Invocation

Comment on an issue, pull request, or inline pull-request review comment:

```text
/opencode inspect this issue, implement the required change, run the relevant checks, and open a pull request.
```

The shorter `/oc` trigger is also supported.

## Security and operating constraints

- The API key is read only from GitHub Actions secrets.
- Session sharing is disabled.
- The job receives repository content, issue and pull-request write permissions so it can create branches, commits, comments, and pull requests.
- The workflow runs only when a new comment contains `/oc` or `/opencode`.
- GitHub-hosted runners cannot reach a Mistral.rs endpoint bound only to a private machine or localhost. That requires a self-hosted runner or a securely reachable endpoint.
