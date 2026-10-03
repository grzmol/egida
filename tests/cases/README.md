# Przypadki testowe (dane, nie kod)

Każdy obszar ma jedną listę YAML. `tests/test_cases.py` uruchamia każdy przypadek testowy offline przez ASGI
(`make test`) i na działającej instancji (`make selftest`, `--target URL`).

Ustawienia bazowe: `config/policy.yaml`, agent `demo-agent` z kluczem API `sk-demo-agent`, model `llama3.2:3b`.
Odpowiedź atrapy modelu (ASGI): `"OK"`, jeśli przypadek nie ustawia `model_reply`.
Na żywo (`--target`) żądania dostają `max_tokens: 1`, jeśli przypadek nie ustawia tego pola.
Wtedy decyzję podejmują tylko kontrole wejścia. Kontrole wyjścia sprawdzają przypadki offline.

| Pole | Znaczenie |
|---|---|
| `id` | unikalny, stały |
| `control` | id kontroli w polityce albo etap pipeline'u, który przypadek sprawdza (`pii`, `secrets`, `injection_heuristics`, `access.model`, `limit`, `budget`, `auth`, `http`); przypadki kontroli detektora, która nie jest włączona w `config/policy.yaml`, są pomijane; każda kontrola ma co najmniej jeden przypadek `negative` i jeden `positive` |
| `polarity` | `negative` = naruszenie, proxy musi je złapać; `positive` = treść bezpieczna, proxy musi ją przepuścić (pułapka fałszywego alarmu) |
| `request` | treść żądania czatu OpenAI; domyślny `model` to `llama3.2:3b` |
| `api_key` | domyślnie `sk-demo-agent`; `null` wysyła żądanie bez nagłówka `Authorization` |
| `headers` | dodatkowe nagłówki HTTP |
| `method`, `path` | domyślnie `POST /v1/chat/completions` |
| `raw_body` | wysyła ten tekst zamiast JSON z `request` |
| `fill` | zastępuje treść ostatniej wiadomości tekstem `"a" * fill` |
| `model_reply` | odpowiedź atrapy modelu: tekst, `{echo: system}` (ujawnia prompt systemowy) albo `{tool_calls: [{name, arguments}]}` (`arguments` to tekst JSON; zadeklaruj narzędzie w `request.tools`) |
| `policy_patch` | zmiany scalane z polityką bazową; `controls` są zmieniane według id, `null` usuwa kontrolę |
| `repeat` | wysyła żądanie N razy; `expect` dotyczy ostatniej odpowiedzi |
| `expect.http_status` | status HTTP, domyślnie 200 |
| `expect.decision` | `allow` / `redact` / `block` (z `egida.decision`) |
| `expect.control_id` | musi być równe `egida.blocked_by` albo wystąpić w `egida.controls[].id` |
| `expect.response_not_contains` | teksty, których nie może być w treści odpowiedzi |
| `expect.upstream_not_contains` | teksty, które nie mogą dotrzeć do modelu (tylko ASGI) |
| `expect.upstream_max_tokens` | `max_tokens`, które dostał model (tylko ASGI) |
| `tags` | `offline-only` (wymaga `model_reply` albo `policy_patch`, pomijany z `--target`), `pl`, `judge-likely` (jury prawdopodobnie to sprawdzi), `semantic` (wymaga prawdziwego modelu), `needs-budget-store` (strict xfail do A3), `known-gap` (poprawne oczekiwanie, którego obecne detektory nie spełniają; strict xfail; usuń tag po poprawie detektora) |

Źródła: docs/research/11-brainstorm-red-team.md §1-§4, docs/research/03-testy-i-red-teaming.md §4.
Wszystkie dane osobowe i dane logowania w tym katalogu są fikcyjne albo pochodzą z przykładów w opublikowanej dokumentacji.
