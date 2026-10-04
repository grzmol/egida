# ADR-0008: Zmiana nazwy produktu na Egida

**Status**: Accepted
**Data**: 2026-10-03
**Decydują**: Grzegorz

## Kontekst

Produkt nazywał się „AI Control Layer”. To jest też tytuł zadania partnerskiego HackYeah (Goldman Sachs). Narzędzie terminalowe miało nazwę Egida (ADR-0007). Dwie nazwy jednego produktu wprowadzały w błąd. Stara nazwa była w wielu miejscach:
- pakiet Python `control_layer` i dystrybucja `control-layer` 0.1.0;
- nagłówki odpowiedzi `X-Control-*` i pole `control_layer` w odpowiedzi (ADR-0005);
- zmienne środowiskowe `CONTROL_LAYER_*`;
- metryki Prometheusa, obraz Docker i projekt Compose.

## Decyzja

Produkt nazywa się **Egida** we wszystkich nazwach, także w kontrakcie HTTP. Wersja: 0.2.0. Zmiany nazw:

| Rodzaj | Stara nazwa | Nowa nazwa |
|---|---|---|
| Nazwa produktu | AI Control Layer | Egida |
| Narzędzie terminalowe | Egida | konsola Egidy |
| Pakiet Python | `control_layer`, `src/control_layer/` | `egida`, `src/egida/` |
| Pakiet konsoli | `control_layer.egida`, `tests/unit/egida/` | `egida.console`, `tests/unit/console/` |
| Moduły w poleceniach | `control_layer.app:create_app`, `-m control_layer.adapters.audit_jsonl` | `egida.app:create_app`, `-m egida.adapters.audit_jsonl` |
| Dystrybucja | `control-layer` 0.1.0 | `egida` 0.2.0 |
| Polecenie | `uv run egida`, `uv run egida run`, `make egida` | `egd`, `egd run`, `egd --profile PATH`, `make egd`, `make install` |
| Zmienne środowiskowe | `CONTROL_LAYER_<X>` | `EGIDA_<X>` |
| Nagłówki HTTP | `X-Control-Decision`, `X-Control-Request-Id` | `X-Egida-Decision`, `X-Egida-Request-Id` |
| Pole odpowiedzi | `control_layer` (JSON i fragmenty SSE) | `egida` (ta sama struktura) |
| Metryki | `control_layer_*` | `egida_*` |
| `owned_by` w `/v1/models` | `control-layer` | `egida` |
| Tytuł API i dashboardu | `AI Control Layer`, `AI Control Layer: Operations` | `Egida`, `Egida: Operations` |
| Docker | projekt i obraz `control-layer` | projekt i obraz `egida` |

Zasady:
- Nagłówki i pole odpowiedzi zastępują nazwy z kontraktu odpowiedzi blokady (ADR-0005). Nagłówki `X-Policy-Version`, `X-Policy-Sha256` i `X-Feed-Version` zostają.
- Zmienna `EGIDA_<X>` zastępuje `CONTROL_LAYER_<X>` dla każdego X: POLICY, AUDIT, FEED, GUARD_URL, MODELS_DIR, SELFTEST_AGENT, DEMO_KEY, KEY, TEST_KEYS, URL.
- Polecenie `egd` uruchamia konsolę Egidy i samo uruchamia proxy. `egd run` uruchamia proxy na pierwszym planie, bez interfejsu.
- Nie ma aliasów starych nazw.
- Nazwa repozytorium i nazwa zespołu (`froggers`) zostają.

## Rozważane opcje

1. **Tylko nazwy w tekście.** Odrzucone: kod i API dalej używają starej nazwy, więc nazwy są niespójne.
2. **Nazwy w tekście i pakiet, kontrakt HTTP bez zmian.** Odrzucone: nagłówki, pole odpowiedzi i zmienne dalej mają starą nazwę, więc nazwy w kodzie i API są niespójne.
3. **Pełna zmiana nazwy, także kontraktu HTTP i zmiennych.** Wybrane.

## Konsekwencje

**Pozytywne**: jedna nazwa produktu w kodzie, API, poleceniach i dokumentacji. Jedno polecenie `egd` uruchamia aplikację.

**Negatywne**: zmiana łamie zgodność. Klient, który czyta stare nagłówki albo pole `control_layer`, przestaje działać. Proxy pomija stare zmienne środowiskowe `CONTROL_LAYER_*`.

**Mitygacje**:
- Wszystkich klientów w repozytorium zmieniamy razem z proxy: selftest, skrypty, testy, konsolę, Compose.
- Wersja 0.2.0 pokazuje zmianę łamiącą zgodność.
- Dokumenty historyczne (zadania, ai-usage, audyty, ADR-0001 do ADR-0007, `docs/hackyeah.md`) zachowują stare nazwy, bo opisują stan zgłoszenia.
