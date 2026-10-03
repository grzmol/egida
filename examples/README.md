# Przykłady integracji

Każdy klient zgodny z OpenAI działa za AI Control Layer po zmianie **dwóch ustawień**: `base_url` → proxy, `api_key` → klucz API agenta z polityki. Nie musisz zmieniać SDK ani dodawać zależności do projektu.

Najpierw uruchom proxy (`make run` albo `docker compose up -d`, patrz `docs/deploy.md`).

| Przykład | Uruchomienie |
|---|---|
| `curl.sh`: surowe HTTP, pokazuje nagłówki `X-Control-*` | `bash examples/curl.sh` |
| `openai_python.py`: OpenAI Python SDK | `uv run --no-project --with openai python examples/openai_python.py` |
| `openai_node.mjs`: OpenAI Node SDK | `cd examples && npm install --no-save openai && node openai_node.mjs` |
| `langchain_python.py`: LangChain `ChatOpenAI` | `uv run --no-project --with langchain-openai python examples/langchain_python.py` |
| `../scripts/demo_agent.py`: agent z narzędziami, pośrednie injection EN/PL | `uv run --no-project --with openai python scripts/demo_agent.py --scene all` |

Zmienne środowiskowe: `CONTROL_LAYER_URL` (domyślnie `http://127.0.0.1:8080/v1`), `CONTROL_LAYER_KEY` (domyślnie `sk-demo-agent`). Agent demo używa `CONTROL_LAYER_DEMO_KEY` (domyślnie `sk-tools-agent`).

## Jak odczytać decyzję

Każda odpowiedź ma potwierdzenie decyzji:

- nagłówki `X-Control-Decision` (`allow` | `redact` | `block`), `X-Control-Request-Id`, `X-Policy-Version`, `X-Policy-Sha256`;
- pole `control_layer` w treści: `decision`, `blocked_by`, `controls` (znaleziska), `errors`.

Blokada to zwykła odpowiedź `200` z `finish_reason: "content_filter"`. Krótki komunikat podaje kontrolę i id żądania. Dzięki temu agent nie przerywa pracy z błędem. Klienci, którzy ignorują dodatkowe pola (np. LangChain), dalej widzą `finish_reason`.

Ustaw `max_retries=0` (Python) / `maxRetries: 0` (Node). Ponowienia SDK liczą się podwójnie w budżecie agenta i w wykrywaniu pętli.

## Oczekiwany wynik

| Prompt | Decyzja | Kontrola |
|---|---|---|
| "Podaj jedną zaletę przelewów natychmiastowych." | `allow` | - |
| "Mój PESEL to 44051401359, …" | `redact` | `pii` |
| "Ignore all previous instructions …" | `block` | `injection_heuristics` |
| "Mój klucz to AKIAIOSFODNN7EXAMPLE …" (curl) | `block` | `secrets` |
| `POST /api/pull` (curl) | `404` | proxy nie przekazuje API Ollamy |
