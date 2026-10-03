# Integration examples

Any OpenAI-compatible client works behind the AI Control Layer by changing **two settings**: `base_url` → the proxy, `api_key` → the agent key from the policy. No SDK patches, no new dependencies in the project.

Start the proxy first (`make run`, or `docker compose up -d` — see `docs/deploy.md`).

| Example | Run |
|---|---|
| `curl.sh` — raw HTTP, shows the `X-Control-*` headers | `bash examples/curl.sh` |
| `openai_python.py` — OpenAI Python SDK | `uv run --no-project --with openai python examples/openai_python.py` |
| `openai_node.mjs` — OpenAI Node SDK | `cd examples && npm install --no-save openai && node openai_node.mjs` |
| `langchain_python.py` — LangChain `ChatOpenAI` | `uv run --no-project --with langchain-openai python examples/langchain_python.py` |
| `../scripts/demo_agent.py` — agent with tools, indirect injection EN/PL | `uv run --no-project --with openai python scripts/demo_agent.py --scene all` |

Environment: `CONTROL_LAYER_URL` (default `http://127.0.0.1:8080/v1`), `CONTROL_LAYER_KEY` (default `sk-demo-agent`; the demo agent uses `CONTROL_LAYER_DEMO_KEY`, default `sk-tools-agent`).

## Reading the decision

Every response carries a receipt:

- headers `X-Control-Decision` (`allow` | `redact` | `block`), `X-Control-Request-Id`, `X-Policy-Version`, `X-Policy-Sha256`;
- body field `control_layer`: `decision`, `blocked_by`, `controls` (findings), `errors`.

A block is an ordinary `200` completion with `finish_reason: "content_filter"` and a short message naming the control and request id, so agents do not crash on it. Clients that ignore extra fields (e.g. LangChain) still see `finish_reason`.

Set `max_retries=0` (Python) / `maxRetries: 0` (Node): SDK retries count twice against the agent's budget and loop detector.

## Expected output

| Prompt | Decision | Control |
|---|---|---|
| "Podaj jedną zaletę przelewów natychmiastowych." | `allow` | — |
| "Mój PESEL to 44051401359, …" | `redact` | `pii` |
| "Ignore all previous instructions …" | `block` | `injection_heuristics` |
| "Mój klucz to AKIAIOSFODNN7EXAMPLE …" (curl) | `block` | `secrets` |
| `POST /api/pull` (curl) | `404` | Ollama API is not proxied |
