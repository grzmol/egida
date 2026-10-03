# ADR-0004: Semantyka decyzji i jawna obsługa błędów kontroli

**Status**: Accepted
**Data**: 2026-10-03

## Kontekst

Kontrole działają razem i mogą się nie zgadzać. Kontrole semantyczne zależą od lokalnego modelu, który może być wolny lub niedostępny. Jury sprawdza odporność (30% oceny) promptami ad hoc. Kod generowany przez AI często połyka wyjątki, co w warstwie bezpieczeństwa oznacza ciche przepuszczanie ataków.

## Decyzja

- Każdy detektor zwraca `Finding` albo nic; nie podejmuje decyzji i nie rzuca wyjątków poza swój kontrakt.
- `Decision` = `ALLOW | REDACT | BLOCK`; agregacja: najostrzejsza akcja wygrywa (`BLOCK > REDACT > ALLOW`). Redakcje z wielu detektorów są łączone.
- Kolejność: tanie deterministyczne przed semantycznymi; `BLOCK` przerywa pipeline (bez wywołania modelu i dalszych kontroli).
- Każda kontrola ma w polityce `timeout` i `on_error: block | allow`. Domyślnie `block` (fail-closed).
- Błąd kontroli to osobne zdarzenie audytu z przyczyną; nigdy nie znika.
- Każda decyzja ma w audycie: id żądania, agenta, migawkę wersji polityki, wyniki detektorów, czasy etapów.

## Konsekwencje

**Dobre**: przewidywalne zachowanie przy awariach; pełny ślad dla zespołu bezpieczeństwa; telemetria opóźnień z tych samych zdarzeń.

**Złe**: fail-closed przy niedostępnej Ollamie blokuje ruch.

**Mitygacje**: `on_error` konfigurowalne per kontrola; stan modeli widoczny na dashboardzie.
