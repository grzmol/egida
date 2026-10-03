# Architecture Decision Records

Decyzje architektoniczne projektu. Plan: [`docs/PLAN.md`](../PLAN.md).

## Indeks

| ADR | Tytuł | Status | Data |
|---|---|---|---|
| [0001](0001-architektura-heksagonalna-z-pipeline.md) | Architektura heksagonalna z liniowym pipeline'em kontroli | Accepted | 2026-10-03 |
| [0002](0002-stack-python-fastapi-ollama.md) | Stack — Python 3.12, FastAPI, Pydantic v2, Ollama | Proposed | 2026-10-03 |
| [0003](0003-polityka-jako-wersjonowany-kontrakt.md) | Polityka jako wersjonowany kontrakt z hot reloadem | Accepted | 2026-10-03 |
| [0004](0004-semantyka-decyzji-i-obsluga-bledow.md) | Semantyka decyzji i jawna obsługa błędów kontroli | Accepted | 2026-10-03 |

## Kiedy pisać ADR

Nowa zależność, wybór modelu, format danych, protokół, zmiana portów w `core/ports.py`, zmiana schematu polityki. Nie piszemy ADR dla poprawek błędów i szczegółów implementacji.

## Jak dodać ADR

1. Skopiuj format istniejącego ADR do `NNNN-tytul-z-myslnikami.md` (kolejny numer).
2. Sekcje: Status, Data, Kontekst, Decyzja, Rozważane opcje (jeśli były), Konsekwencje (dobre, złe, mitygacje).
3. Dopisz wiersz do indeksu.
4. Zaakceptowanego ADR nie edytujemy — piszemy nowy ze statusem „Supersedes ADR-NNNN”, a stary oznaczamy „Superseded”.

Statusy: Proposed → Accepted → Deprecated / Superseded; albo Rejected.
