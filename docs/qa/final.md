# Raport QA — Checkpoint Finałowy (08:45–09:30)

**Data i godzina audytu:** 2026-10-04 (niedziela), _do wpisania_  
**Audytor:** Kamil (Dev C — rola „Pierwszego Jurora”)  
**Środowisko:** Świeży klon repozytorium (`/tmp/froggers-final-qa`)  
**Cel:** Weryfikacja odtwarzalności rozwiązania na tagu `final` przed zamknięciem zgłoszeń o 10:30.

> **Szablon.** Kolumny „Faktyczny wynik” i „Status” wypełnia się dopiero po przebiegu na tagu `final`; do tego czasu nic tu nie jest wynikiem.

---

## 1. Tabela kroków weryfikacyjnych (zgodnie z `README.md`)

| # | Polecenie / Krok z `README.md` | Oczekiwany wynik | Faktyczny wynik | Status (OK / BŁĄD) | Uwagi |
|---|---|---|---|---|---|
| 1 | `git clone https://github.com/grzmol/froggers.git` | Czysty klon repozytorium | _do wypełnienia_ | — | |
| 2 | `git checkout final` | Przełączenie na oficjalny tag finałowy | _do wypełnienia_ | — | |
| 3 | `uv sync` | Pomyślna instalacja zależności z `uv.lock` | _do wypełnienia_ | — | |
| 4 | `make models` | Pobranie i weryfikacja sha256 modelu Prompt Guard 2 (opcjonalny, domyślnie wyłączony) | _do wypełnienia_ | — | |
| 5 | `make check` | Zielone lintery, kontrakty heksagonalne i testy (próba 3.10: 930 passed, 76 skipped) | _do wypełnienia_ | — | |
| 6 | `make run` | Start proxy na porcie 8080 | _do wypełnienia_ | — | |
| 7 | Dashboard webowy | Otwarcie `http://127.0.0.1:8080/dashboard` | _do wypełnienia_ | — | |
| 8 | Normalne zapytanie agenta | Decyzja `allow`, odpowiedź modelu, nagłówki `X-Control-*` i `X-Policy-*` | _do wypełnienia_ | — | Wymaga Ollamy; bez niej 502 |
| 9 | Ochrona PII i sekretów | PESEL `redact`, sekret `block` | _do wypełnienia_ | — | |
| 10 | Atak prompt injection / RCE | Decyzja `block` bez wołania modelu | _do wypełnienia_ | — | |
| 11 | `CONTROL_LAYER_SELFTEST_AGENT=selftest-agent make selftest` | 0 failed (próba 3.10 z atrapą upstreamu: 179 passed, 54 skipped) | _do wypełnienia_ | — | Wymaga Ollamy dla `allow`/`redact` |
| 12 | `make verify-audit` | `OK n events` — łańcuch nienaruszony | _do wypełnienia_ | — | |

---

## 2. Podsumowanie gotowości do zgłoszenia finałowego (10:30)

- [ ] Prezentacja finałowa `docs/pitch/slides.pdf` gotowa (≤ 10 stron).
- [ ] Notatki mówcy `docs/pitch/speaker-notes.md` przygotowane (czas wystąpienia ≤ 5 min).
- [ ] Formularz zgłoszenia finałowego `docs/submission/final.md` przygotowany i zwalidowany limitami znaków.
- [ ] Oznaczenie tagiem `final` (Grzegorz, A8 krok 7).
