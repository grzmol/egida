# ADR-0009: Harnessy i protokoły: nowe wejścia proxy i kreator w konsoli

**Status**: Accepted
**Data**: 2026-10-04
**Decydują**: Grzegorz

## Kontekst

Harness to narzędzie do pracy z kodem z agentem AI, na przykład Claude Code, Codex albo Gemini CLI. Proxy przyjmowało tylko API OpenAI Chat Completions. Najważniejsze harnessy używają innych protokołów:
- Claude Code: Anthropic Messages;
- Codex: OpenAI Responses;
- Gemini CLI i Antigravity CLI: API Gemini.

Każdy harness ma inny plik konfiguracji i inne nazwy kluczy. Ręczna konfiguracja była trudna i łatwo było o błąd. Po zmianie użytkownik nie miał prostej drogi powrotu.

## Decyzja

1. **Nowe adaptery wejściowe.** Proxy dostaje trzy adaptery wejściowe (driving): `adapters/anthropic_api.py`, `adapters/responses_api.py`, `adapters/gemini_api.py`. Części wspólne są w `adapters/http_common.py`. Każdy adapter zmienia swój format na ten sam `Interaction` i uruchamia ten sam pipeline. `core/` nie zmienia się. Upstream to zawsze model z polityki przez API czatu OpenAI.
2. **Odpowiedź blokady dla każdego protokołu.** Proxy pokazuje tekst `Request blocked by Egida (control: X, request: Y).` w formacie, który harness pokazuje użytkownikowi. Test na żywo dał te wybory:

   | Protokół | Odpowiedź blokady | Powód |
   |---|---|---|
   | OpenAI Chat Completions | HTTP 200, `finish_reason: content_filter` | bez zmian (ADR-0005) |
   | Anthropic Messages | `stop_reason: end_turn`, jeden blok tekstu | przy `refusal` Claude Code ukrywa tekst i pokazuje komunikat AUP Anthropic |
   | OpenAI Responses | `status: completed`, element wiadomości | przy `incomplete` Codex zgłasza błąd strumienia i ponawia żądanie 3 razy |
   | Gemini | `finishReason: SAFETY` z tekstem blokady | Gemini CLI pokazuje tekst |

   Nagłówki `X-Egida-*` i pole `egida` są takie same we wszystkich protokołach. Proxy usuwa narzędzia serwerowe, których upstream czatu nie wykona. Obrazy i dokumenty dostają 400.
3. **Rejestr harnessów.** `console/harnesses/` ma `REGISTRY` z 13 harnessami. Id harnessu jest też id agenta w polityce. Harness ma jeden z trzech trybów:
   - `config`: Egida zmienia plik konfiguracji harnessu;
   - `launch`: Egida zapisuje plik env uruchomienia, a `egd launch <id>` uruchamia harness;
   - `unavailable`: Egida nic nie zmienia (Antigravity IDE, Cursor).
4. **Bezpieczne zmiany w plikach harnessów.**
   - Przed pierwszym zapisem Egida robi kopię w `~/.config/egida/backups/<id>/` (5 najnowszych).
   - Rejestr `~/.config/egida/harnesses.json` (tryb 0600) zapisuje poprzednie wartości i sha256 wartości od Egidy. Rejestr nie zawiera kluczy.
   - Usunięcie przywraca tylko wartości Egidy. Zmiany użytkownika zostają.
   - Egida nie zmienia pliku, którego nie może odczytać.
   - Pliki env uruchomienia: `~/.config/egida/launch/<id>.env` (tryb 0600).
5. **Kreator.** `egd` bez pliku profilu i `egd setup` otwierają kreator. Kroki: powitanie, model, lista harnessów, adres proxy, przegląd z diffem, wynik. Kreator tworzy klucz API dla każdego harnessu, agenta i budżet `harness` w polityce, potem zapisuje pliki i uruchamia proxy.
6. **tomlkit.** Egida zmienia `~/.codex/config.toml` przez tomlkit. Komentarze i kolejność kluczy zostają.
7. **Zmiany silnika sygnatur.**
   - `MAX_BASE64_CANDIDATES`: 64 na 4096. Ścieżki i długie identyfikatory pasują do wzorca kandydata base64. Prompty Gemini CLI przekraczały stary limit, więc każde żądanie dostawało blokadę (`SignatureLimitError`, potem `on_error`).
   - `STACK_GLOBAL` z mniej niż dwoma elementami na stosie kończy analizę pickle. Unpickler też by się zatrzymał, więc to nie jest pickle. Wcześniej identyfikator z bajtem 0x93 dawał fałszywą blokadę SIG-0006 promptu systemowego Codex.

## Rozważane opcje

| Opcja | Dlaczego odrzucona |
|---|---|
| Tylko harnessy z API Chat Completions | Claude Code, Codex i Gemini CLI zostają poza kontrolą. To najczęściej używane harnessy. |
| Proxy MITM HTTPS do API dostawców | Wymaga własnego CA w systemie i zależy od zmian API dostawcy. Ruch nadal idzie do chmury, nie do modelu z polityki. |
| Tylko uruchamianie, jak `ollama launch` | Harness działa przez Egidę tylko po starcie przez `egd`. Egida używa tego trybu tylko tam, gdzie plik konfiguracji nie wystarcza. |
| Zmiana plików rc powłoki (`.zshrc`, `.bashrc`) | Zmienne działają w każdym procesie, także poza harnessem. Zmiana jest trudna do cofnięcia i do sprawdzenia. |

## Konsekwencje

Dobre:
- Claude Code, Codex i Gemini CLI działają przez Egidę. Test na żywo: odpowiedź z upstreamu i blokada injection z tekstem Egidy.
- Te same kontrole, budżety i dziennik audytu działają dla każdego protokołu.
- Użytkownik konfiguruje harnessy w jednym kreatorze i może cofnąć zmianę.

Złe:
- Proxy ma więcej protokołów do utrzymania. Zmiana API harnessu może zepsuć jego adapter.
- Klucze API są jawnym tekstem w konfiguracjach harnessów, jak każdy klucz API tych narzędzi.
- Odpowiedzi daje model z polityki, nie model dostawcy harnessu. Mały model lokalny daje gorsze wyniki.
- Harnessy z innym protokołem albo bez własnego endpointu nadal nie działają z Egidą.

Mitygacje:
- Testy jednostkowe adapterów i zapisu konfiguracji harnessów na tymczasowym katalogu domowym.
- Polityka zawiera tylko sha256 klucza. Pliki env uruchomienia i rejestr mają tryb 0600.
- Kreator pokazuje diff przed zapisem. Kopie i rejestr pozwalają cofnąć zmianę.
