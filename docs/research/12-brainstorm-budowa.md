# 12 — Brainstorm: jak to zbudować (perspektywa lead engineera)

Perspektywa: szybka dostawa z agentami AI przy małym długu. Podstawa: [PLAN](../PLAN.md), [ADR](../adr/), research 01–04. Pakiety spoza researchu sprawdziłem w PyPI 2026-10-03: `onnxruntime` 1.30.0 MIT (Python ≥3.11), `tokenizers` 0.23.2 Apache-2.0, `prometheus-client` 0.26.0 Apache-2.0. Nasze wnioski są oznaczone `[INFERENCE]`.

## 1. Reuse vs build

| Komponent | Decyzja · pakiet (licencja) | Uzasadnienie | ADR |
|---|---|---|---|
| Proxy | build: FastAPI + httpx | jury ocenia naszą architekturę (01 §5) | 0002 |
| Polityka | build: Pydantic + PyYAML, reload przez polling sha256 co 1 s | zero nowych zależności, testowalne z `Clock` | — |
| PII | regexy + `python-stdnum` (LGPL-2.1+, 02 §2) | sum kontrolnych nie piszemy sami (typowy błąd kodu z AI); Presidio po drafcie | DEPS |
| Sekrety | build: reguły w feedzie sygnatur, wzorowane na `gitleaks.toml` (MIT) | **wbrew 02 §5** (`detect-secrets`: release z 2024-05, API pod pliki): jedna maszyna reguł dla R2 i R4, edytowalna na żywo | — |
| Injection (model) | PG2-86M ONNX (gravitee, Llama 4 Community, 281 MB) przez `onnxruntime` + `tokenizers`, w procesie | 111 ms, 6/6 (02 §1b), bez torch | **tak** |
| Injection (heurystyki) | build: NFKC, usuwanie zero-width, dekodowanie base64 (C06) | tanie i deterministyczne | — |
| Guard LLM | `llama-guard3:1b`, zapas `granite3-guardian:2b` (Ollama, 02 §5) | szkodliwe treści na wejściu i wyjściu; po drafcie | **tak** |
| Sygnatury | build: silnik wg 04 §5; pickle przez stdlib `pickletools` | `picklescan`/`modelscan` tylko do plików artefaktów (P1) | format |
| Budżety | build: in-memory; ceny w polityce | **wbrew 01 §5** (JSON z LiteLLM): ceny potrzebne tylko dla modeli z allowlisty, jury edytuje je w jednym pliku | — |
| Audyt | build: JSONL + łańcuch hashy (C20) | ~20 linii, argument przy kryterium „Security reporting” | schemat |
| Metryki | agregacja ze zdarzeń audytu; `/metrics` (`prometheus-client`) po drafcie | jedno źródło prawdy | — |
| Dashboard | statyczny HTML + JS (polling `/api/stats`), bez CDN | bez dodatkowego procesu; design ma 0% wagi | tak |
| Selftest | pytest z `--target` (transport ASGI albo HTTP) | **wbrew PLAN F6** (osobny CLI): jeden runner, JUnit przez `--junitxml` | — |
| Red team | `garak` (Apache-2.0) przez `uvx`, poza `uv.lock` | izoluje ciężkie zależności (03 §1) | — |

**Ranking:** (1) rdzeń, polityka, sygnatury, audyt i selftest bez nowych zależności; (2) z gotowych bierzemy tylko modele i `python-stdnum`; (3) narzędzia zewnętrzne trzymamy poza lockiem.

## 2. Stack i runtime: zmiany w ADR-0002

- **Python 3.12**, nie 3.13: `modelscan` wymaga <3.13, a pomiary z 02 §1b zrobiliśmy na 3.12.
- **Układ (rekomendacja):** proxy natywnie przez `uv run`; PG2 przez ONNX w procesie (`anyio.to_thread` + semafor, wyłączony padding 512); Ollama jako natywny sidecar, bo ma Metal. W Dockerze na macOS Ollama nie ma GPU `[INFERENCE]`, więc tam guard LLM byłby wolny. **Docker Compose** (`app` + `ollama`, port 11434 niewystawiony, D01) służy tylko jako deliverable na czystą maszynę. PG2 przez Ollamę odpada: modelu nie ma w library (02 §1a).
- **Czego brakuje w ADR-0002:** `onnxruntime`, `tokenizers`, PyYAML, układ procesów, `make models` z przypiętymi sha256 (nasz własny C12), kontrakt HTTP.
- **Rozbieżność z PLAN Z8:** jeden ADR na każdą bibliotekę przed 20:00 to za dużo. Proponuję ADR-0002 → Accepted teraz, a resztę w zbiorczym **ADR-0005 „Zależności i modele v1”**.

## 3. Przyrosty

I0 robi jedna osoba. Potem tory równoległe (‖) z rozłącznymi plikami. Do `core/models.py`, `ports.py`, `pipeline.py` i `app.py` pisze tylko integrator A.

**Do draftu 20:00**

| # | Okno | Właściciel: pliki | Wycinek → akceptacja |
|---|---|---|---|
| I0 | 12:45–13:30 | A: `pyproject`, `Makefile`, `core/*`, `tests/test_cases.py` | kontrakty z §4 → `make check` zielone, 1 przypadek YAML |
| ops‖ | od 12:45 | dowolny | Ollama, model czatu, `llama-guard3:1b`, `make models` → `ollama list`, sha256 OK |
| I1 | 13:30–14:30 | A: `adapters/http_api.py`, `ollama_client.py`, `app.py`; F: `audit_jsonl.py` | walking skeleton → SDK `openai` przez proxy, w audycie wpis z `policy_sha256` |
| I2‖ | 13:30–15:30 | B: `adapters/policy_file.py`, `detectors/access.py` | reload, last-known-good, klucz → agent, allowlista → zmiana działa w ≤2 s; zły YAML → `policy_rejected` |
| I3‖ | 13:30–15:30 | C: `detectors/pii.py`, `secrets.py`, `cases/pii,secrets.yaml` | przypadki 1, 2, 4, 5 (03 §4) |
| I4‖ | 13:30–15:30 | D: `core/budget.py`, `adapters/budget_memory.py`, `cases/budget.yaml` | przypadki 15–17 |
| I5‖ | 13:30–16:00 | E: `detectors/prompt_guard.py`, `normalize.py`, `cases/injection.yaml` | **PG2 + C06 przed draftem (z F3)** → przypadki 6, 9–11 + pozytywy XSTest-like |
| I6 | 15:30–16:30 | A | integracja, agregacja, format blokady → wszystkie `cases/` e2e przez ASGI |
| I7‖ | 16:00–18:00 | F: `dashboard/`, `/api/stats`, `/api/audit?format=csv` | liczniki i ostatnie zdarzenia odświeżają się w trakcie `make selftest` |
| I8 | 18:00–19:00 | wszyscy | `policy.strict/lenient.yaml`, diagram, README, `AI_USAGE.md` |
| I9 | 19:00–19:45 | A | **freeze 19:00**, świeży klon: `uv sync && make run && make selftest` → zgłoszenie 19:45 |

**Po drafcie do 11:00:** I10 20:00–22:00: feed sygnatur z hot reloadem; `tests` z reguł zasilają selftest; kontrole `tool_calls` C03/C10/C11 (przypadki 19–23) · I11‖: spike guard LLM na 30 promptach EN/PL → ADR → detektor z `on_error` · I12‖: pseudo-stream (`stream:true` buforujemy, potem wysyłamy SSE) · I13 22:30–01:00: p50/p95 per etap, `/metrics`, `verify-audit`, panel posture · I14‖: demo agent z narzędziami, czyli indirect injection w `role: tool`, C14, C22 · I15 01:00–04:00: garak przed/po, FP/FN na deepset i XSTest · I16 04:00–06:30: compose na czystej maszynie · I17 06:30–10:30: audyt długu (PLAN §8), freeze 08:30, slajdy, zgłoszenie.

## 4. Kontrakty do zamrożenia w I0

- **`Interaction`** (frozen): `request_id`, `agent_id`, `channel` (`app_model|tool_result|agent_agent`), `model`, `messages: tuple[Message(role, content, name?, tool_call_id?, tool_calls?)]`, `tools`, `max_tokens`, `output?`.
- **`Finding`**: `control_id`, `category` (`access|pii|secret|injection|harmful|signature|budget`), `score`, `spans: tuple[Span(msg_index, start, end, label)]`, `evidence` (już zredagowane), `tags` (`owasp.*|asi.*|atlas.*`). **Bez akcji:** pipeline wylicza ją z polityki (`score ≥ threshold`), zgodnie z ADR-0004.
- **`Decision`**: `action`, `findings`, `blocked_by?`, `redacted?`, `errors`.
- **`Detector`**: `kind`, `Params: type[BaseModel]`, `async scan(interaction, side, params) -> list[Finding]`. Timeout i `on_error` obsługuje pipeline. Detektory CPU same przenoszą pracę do wątku.
- **Polityka v1**: `version`, `defaults{on_error, timeout_ms}`, `limits{max_input_chars, max_tokens}`, `agents{id: {key_sha256, allowed_models, allowed_tools, budget}}`, `models{name: {upstream, price_in_per_1k, price_out_per_1k}}`, `budgets{name: {max_tokens, max_cost, max_requests, max_identical, window_s}}`, `controls[{id, kind, enabled, sides, action, threshold, on_error?, timeout_ms?, params}]`. Klucze trzymamy tylko jako hash (C19). Błąd walidacji `params` w modelu `Params` odrzuca całą politykę.
- **`audit.v1`**: `seq`, `ts`, `type` (`decision|policy_reloaded|policy_rejected|feed_rejected|control_error`), `request_id`, `agent_id`, `model`, `policy_version`, `policy_sha256`, `feed_version`, `decision`, `findings[{control_id, category, score, action, tags}]`, `usage{tokens, cost}`, `budget{used, limit}`, `latency_ms{total, stages}`, `error?`, `prev_hash`, `hash`. Surowej treści nie zapisujemy nigdy.
- **HTTP blokady**: 200 + poprawne `chat.completion` z `finish_reason: "content_filter"`, nagłówkiem `X-Control-Decision` i polem `control_layer{decision, request_id, controls}` (03 §1). Wyjątki: 401 (klucz) i 400 (złe wejście). **Przekroczenie budżetu nie zwraca 429**, bo SDK OpenAI automatycznie ponawia 429 `[INFERENCE]`. Ustalić w ADR-0005.
- **Przypadek testowy**: schemat z 03 §3.

## 5. Ryzyka

| Ryzyko | Mitygacja |
|---|---|
| Agenci rozjeżdżają kontrakty, konflikty w `app.py` | I0 przed torami; `core/` i `app.py` zmienia tylko A; rejestr detektorów: jedna linia na detektor; test kontraktowy portu |
| Ollama nie jest gotowa | ops od 12:45; testy na `FakeModelClient` (adapter testowy) |
| ONNX blokuje pętlę zdarzeń | wątek + semafor; p50 w audycie od I5 |
| Halucynowane API bibliotek | smoke test każdego adaptera; `uv lock --check` |
| Połknięte wyjątki = fail-open | `ruff` BLE/S110; test: zatrzymana Ollama → BLOCK (C21) |
| Scope creep: adapter MCP | kontrole narzędzi przez `tools`/`tool_calls` (04 §1); MCP zostaje w backlogu |
| Nadmierne blokowanie | pozytywy XSTest-like obowiązkowe w każdym `cases/*.yaml` |
| Nieznana zawartość draftu | Main pyta organizatorów; freeze 19:00 niezależnie od odpowiedzi |

## 6. Rekomendacje (ranking)

1. Zamrozić kontrakty z §4 przed torami (I0 do 13:30), łącznie z kontraktem HTTP blokady.
2. Przenieść PG2-86M ONNX przed draft (tor E, kryterium z wagą 30%); guard LLM dopiero po drafcie.
3. ADR-0002 → Accepted z poprawkami (3.12, natywnie + sidecar, compose jako deliverable); resztę decyzji zebrać w ADR-0005.
4. Poza modelami i `python-stdnum` żadnych nowych zależności: sekrety jako reguły feedu, ceny w polityce, polling, statyczny dashboard.
5. Jeden runner testów: pytest z `--target` zamiast osobnego CLI.
