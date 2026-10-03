# ADR-0005: Zależności, modele i kontrakt odpowiedzi blokady v1

**Status**: Accepted
**Data**: 2026-10-03
**Decydują**: Grzegorz, Sebastian

## Kontekst

PLAN Z8 wymaga ADR dla każdej zależności, modelu i protokołu. W 24 h osobny ADR na każdą bibliotekę to za dużo ([research 12 §2](../research/12-brainstorm-budowa.md)), więc zbieramy decyzje v1 w jednym miejscu. Dwie decyzje dotyczą zachowania widocznego dla klienta i jury: format odpowiedzi blokującej i to, co się dzieje, gdy detektor nie może wystartować.

## Decyzja

**Zależności runtime** (wersje w `uv.lock`, licencje w [DEPENDENCIES.md](../DEPENDENCIES.md)): FastAPI + uvicorn (wejście HTTP), httpx (upstream), Pydantic v2 (polityka), PyYAML (`safe_load`), python-stdnum (sumy kontrolne PESEL/NIP/REGON/IBAN/Luhn), onnxruntime + tokenizers + numpy (Prompt Guard 2 w procesie, bez torch), anyio (wątki dla CPU, task group lifespan). Nic więcej bez kolejnego ADR.

**Modele**: Llama Prompt Guard 2 86M, eksport ONNX z [research 02 §1b](../research/02-detektory-i-modele.md) (licencja Llama 4 Community, „Built with Llama”), pobierany `make models` z przypiętą rewizją i sha256; upstream demo `llama3.2:3b` w Ollamie. Guard LLM — osobny ADR-0006 po spike'u (B6).

**Odpowiedź blokująca**: HTTP 200, poprawny `chat.completion` z `finish_reason: "content_filter"`, nagłówki `X-Control-Decision`, `X-Control-Request-Id`, `X-Policy-Version`, `X-Policy-Sha256` i pole `control_layer` (decyzja, kontrola, wersja polityki). Kody błędów tylko dla błędów klienta/infrastruktury: 401 (klucz), 400 (złe wejście), 404 (ścieżka spoza allowlisty), 502 (upstream). **Przekroczenie budżetu nie zwraca 429**, bo SDK OpenAI ponawia 429 automatycznie, co samo tworzy pętlę.

**Detektor bez zasobów**: fabryka, która przy starcie rzuca `OSError` (np. brak plików modelu), jest zastępowana atrapą fail-closed: aplikacja startuje, a włączona kontrola tego typu przy każdym żądaniu daje `control_error` i działa jej `on_error` (domyślnie `block`).

## Rozważane opcje

- **Blokada jako 403/422** — prostsza semantyka HTTP, ale narzędzia (garak, promptfoo) i SDK liczą to jako błąd, nie jako skuteczną obronę; agent nie dostaje czytelnej odpowiedzi.
- **Brak startu bez modeli** — najprostsze, ale świeży klon (i CI) nie działa bez 300 MB modeli, choć kontrola jest wyłączona.
- **`detect-secrets`, Presidio, LiteLLM pricing JSON** — odrzucone ([research 12 §1](../research/12-brainstorm-budowa.md)): sekrety jako reguły w kodzie/feedzie, PII przez python-stdnum, ceny w polityce.

## Konsekwencje

**Dobre**: każda decyzja ma „paragon” w odpowiedzi i w audycie; klient OpenAI działa bez zmian poza `base_url`; świeży klon startuje bez modeli; mała lista zależności do obrony.

**Złe**: python-stdnum jest na LGPL-2.1+ (używamy bez modyfikacji, jako zależność dynamiczną); Prompt Guard 2 wymaga napisu „Built with Llama”; budżety tylko w pamięci jednego procesu.

**Mitygacje**: licencje w DEPENDENCIES.md i README; `BudgetStore` to port — Redis bez zmian w rdzeniu.
