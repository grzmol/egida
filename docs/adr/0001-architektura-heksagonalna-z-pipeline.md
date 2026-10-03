# ADR-0001: Architektura heksagonalna z liniowym pipeline'em kontroli

**Status**: Accepted
**Data**: 2026-10-03

## Kontekst

Zadanie wymaga kontroli deterministycznych i semantycznych, budżetów, wykrywania znanych ataków, raportowania i testów. Jury zmienia konfigurację na żywo i sprawdza architekturę (20% oceny). Projekt będzie rozszerzany: kolejne kontrole, protokoły (MCP, agent↔agent), magazyny danych. Większość kodu powstanie z pomocą AI, która bez wyraźnych granic miesza logikę z frameworkiem.

## Decyzja

- Rdzeń `core/` zawiera model domeny (`Interaction`, `Finding`, `Decision`, `Policy`) i pipeline. Nie importuje frameworków, klientów HTTP, plików ani modeli.
- Świat zewnętrzny wyłącznie przez porty (`typing.Protocol`): `Detector`, `PolicySource`, `ModelClient`, `BudgetStore`, `AuditSink`, `SignatureFeed`, `Clock`.
- Pipeline o stałej kolejności: tożsamość i dostęp → rezerwacja budżetu → detektory wejścia → wywołanie modelu → detektory wyjścia → rozliczenie budżetu → agregacja decyzji → audyt.
- Kontrole to implementacje `Detector`, rejestrowane i parametryzowane polityką. Nowa kontrola nie zmienia pipeline'u.
- Adaptery tworzone tylko w `app.py`.
- Granice egzekwuje `import-linter` w `make check`.

## Rozważane opcje

- **Middleware frameworka (np. łańcuch middleware FastAPI)** — szybki start, ale logika związana z HTTP; MCP i agent↔agent wymagałyby duplikacji.
- **Gotowy gateway LLM z wtyczkami** — mniej kodu, ale architektura i guardrails byłyby cudze, a to one są oceniane; ryzyko licencyjne.

## Konsekwencje

**Dobre**: rdzeń testowany bez sieci i Ollamy; nowy protokół = nowy adapter wejścia; nowa kontrola = nowy detektor; czytelny diagram dla jury.

**Złe**: więcej plików i interfejsów na starcie; trzeba pilnować, żeby porty nie puchły.

**Mitygacje**: porty tylko dla rzeczy, które realnie mają dwie implementacje (produkcyjną i testową); zmiana `core/ports.py` wymaga ADR.
