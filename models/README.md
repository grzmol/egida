# models/

Local model files. **Not committed** (only this README is).

| Directory | Model | Source (pinned revision) | License |
|---|---|---|---|
| `prompt-guard-2-86m/` | Llama Prompt Guard 2 86M, ONNX (quantized) | `gravitee-io/Llama-Prompt-Guard-2-86M-onnx@45a05fb` | Llama 4 Community |
| `prompt-guard-2-22m/` | Llama Prompt Guard 2 22M, ONNX (quantized), fallback | `gravitee-io/Llama-Prompt-Guard-2-22M-onnx@da68d0f` | Llama 4 Community |

Download and verify sha256: `uv run python scripts/fetch_models.py` (`--small` for 22M).
A changed file fails the checksum and the script exits with code 1.

Ollama models (pulled separately, stored by Ollama): `llama3.2:3b` (demo chat model),
`llama-guard3:1b` and `granite3-guardian:2b` (guard LLM, night work B6).

Built with Llama.
