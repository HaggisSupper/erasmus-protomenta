# Runtime Contract Evidence

Issue: #52

Captured on Windows from the local laptop environment.

## mistral.rs

- Version command: `mistralrs --version`
- Observed version: `mistralrs 0.9.0`
- One-shot command evidence: `mistralrs run --help` states that `run` enters one-shot mode with `-i, --input <INPUT>`.
- Server command evidence: `mistralrs serve --help` exposes server-level `--host`, `--port`, and `--no-ui` before the model subcommand.
- Model subcommand evidence: `mistralrs serve auto --help` and `mistralrs run auto --help` expose model-level `--model-id`, `--format`, `--quantized-file`, `--lora`, `--xlora`, `--xlora-order`, and `--tgt-non-granular-index`.

## llama.cpp

- Version command: `llama-cli --version`
- Observed version: `version: 9837 (b3fed31b9)`
- Single-turn evidence: `llama-cli --help` exposes `--single-turn`, `--conversation`, and `--no-conversation`; `--single-turn` exits after a predefined `--prompt`.

## Boundaries

- This evidence validates argv shape only.
- It does not prove LoRA and X-LoRA can safely be combined, so the wrapper rejects that combination.
- Process shutdown means terminating the supervised process; it is not adapter unload.
