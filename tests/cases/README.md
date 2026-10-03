# Test cases (data, not code)

One YAML list per area. `tests/test_cases.py` runs every case offline through ASGI
(`make test`) and against a live instance (`make selftest`, `--target URL`).

Base setup: `config/policy.yaml`, agent `demo-agent` with key `sk-demo-agent`, model `llama3.2:3b`.
Fake model reply (ASGI): `"OK"` unless `model_reply` is set. Live (`--target`): requests get `max_tokens: 1` unless the case sets it, so only input-side controls decide; output-side controls are covered offline.

| Field | Meaning |
|---|---|
| `id` | unique, stable |
| `control` | policy control id (cases of a detector control that is not enabled in `config/policy.yaml` are skipped) or pipeline stage the case covers (`pii`, `secrets`, `injection_heuristics`, `access.model`, `limit`, `budget`, `auth`, `http`); at least one `negative` and one `positive` per control |
| `polarity` | `negative` = violation, must be caught; `positive` = benign, must pass (false-positive trap) |
| `request` | OpenAI chat body; `model` defaults to `llama3.2:3b` |
| `api_key` | default `sk-demo-agent`; `null` sends no `Authorization` header |
| `headers` | extra HTTP headers |
| `method`, `path` | default `POST /v1/chat/completions` |
| `raw_body` | send this string instead of JSON `request` |
| `fill` | replace the last message content with `"a" * fill` |
| `model_reply` | fake model reply: a string, `{echo: system}` (leaks the system prompt) or `{tool_calls: [{name, arguments}]}` (`arguments` is JSON text; declare the tool in `request.tools`) |
| `policy_patch` | override merged into the base policy; `controls` is patched by id, `null` removes a control |
| `repeat` | send the request N times; `expect` applies to the last response |
| `expect.http_status` | HTTP status, default 200 |
| `expect.decision` | `allow` / `redact` / `block` (from `control_layer.decision`) |
| `expect.control_id` | must equal `control_layer.blocked_by` or appear in `control_layer.controls[].id` |
| `expect.response_not_contains` | strings that must not appear in the response content |
| `expect.upstream_not_contains` | strings that must not reach the model (ASGI only) |
| `expect.upstream_max_tokens` | `max_tokens` the model received (ASGI only) |
| `tags` | `offline-only` (needs `model_reply` or `policy_patch`, skipped with `--target`), `pl`, `judge-likely` (jury will likely try it), `semantic` (needs a real model), `needs-budget-store` (strict xfail until A3), `known-gap` (valid expectation the current detectors miss; strict xfail, remove the tag when the detector is fixed) |

Sources: docs/research/11-brainstorm-red-team.md §1–§4, docs/research/03-testy-i-red-teaming.md §4.
All personal data and credentials here are fictitious or published documentation examples.
