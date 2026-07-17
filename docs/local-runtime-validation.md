# Local Runtime Validation

Validated on the Windows local-development checkout for issue #55.

## Successful wrapper smoke tests

- LM Studio CLI `9902c3a`: `google/gemma-3n-e4b` returned a non-empty one-shot response through `run_headless` in 1.47 seconds.
- Ollama `0.31.2`: local `qwen3:4b` returned a non-empty one-shot response through `run_headless` in 2.17 seconds.
- llama.cpp `9837 (b3fed31b9)`: the local FunctionGemma GGUF completed a one-shot `run_headless` assertion.

The wrapper decodes CLI output as UTF-8 with replacement. This prevents Ollama's UTF-8 stderr from crashing the Windows CP1252 host decoder after a successful response.

## mistral.rs boundary

`mistralrs 0.9.0` and its CLI contract are installed, but the tested local candidates did not yield a compatible non-disruptive launch:

- FunctionGemma and CodeGemma GGUFs use unsupported `gemma3` and `gemma` architectures.
- LFM2.5 uses unsupported `lfm2`.
- Qwen3.5 uses unsupported IQ4 quantization.
- The Qwen3 Q4K candidate is supported by the loader but needs 881 MB more CPU capacity than is currently available.

No model was downloaded and no active LM Studio model was unloaded. Re-run the mistral.rs smoke after selecting a compatible local GGUF or after the Protomentat authorizes changing the active runtime allocation.

## Reproduction

The default pytest temp root is permission-denied on this Windows checkout, so use a repository-local base temp.

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_headless.py -v --basetemp=.tmp-pytest-headless
.\.venv\Scripts\python.exe -m pytest tests\ -v --basetemp=.tmp-pytest-full
```
