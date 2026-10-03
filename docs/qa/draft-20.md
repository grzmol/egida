# Raport QA — Checkpoint Draft (20:00)

**Data i godzina audytu:** 2026-10-03  
**Audytor:** Kamil (Dev C — rola „Pierwszego Jurora”)  
**Środowisko:** Świeży klon repozytorium (`/tmp/froggers-qa`)  
**Cel:** Weryfikacja odtwarzalności rozwiązania wyłącznie na podstawie instrukcji z `README.md` przed zgłoszeniem draftu o 19:45.

---

## 1. Tabela kroków weryfikacyjnych (zgodnie z `README.md`)

| # | Polecenie / Krok z `README.md` | Oczekiwany wynik | Faktyczny wynik | Status (OK / BŁĄD) | Uwagi |
|---|---|---|---|---|---|
| 1 | `git clone https://github.com/grzmol/froggers.git` | Czysty klon repozytorium bez błędów | — | DO WYKONANIA | Sprawdzenie kompletności repo |
| 2 | `uv sync` | Pomyślna instalacja zależności z `uv.lock` | — | DO WYKONANIA | Sprawdzenie zależności Pythona 3.12 |
| 3 | `uv run python scripts/fetch_models.py` | Pobranie i weryfikacja sha256 modeli ONNX w `models/` | — | DO WYKONANIA | Model Prompt Guard 2 |
| 4 | `make check` | Zielone lintery (`ruff`, `mypy`, `lint-imports`) i testy offline (`pytest -q`) | — | DO WYKONANIA | Weryfikacja jakości i architektury |
| 5 | `make run` | Serwer wstaje na `http://127.0.0.1:8080` (FastAPI + Uvicorn) | — | DO WYKONANIA | Port 8080 otwarty |
| 6 | Wejście na `http://127.0.0.1:8080/dashboard` | Dashboard otwiera się w przeglądarce, wyświetla metryki i status | — | DO WYKONANIA | Interfejs webowy |
| 7 | Legalne żądanie (curl/SDK z kluczem `sk-demo-agent`) | Decyzja `allow`, odpowiedź z modelu | — | DO WYKONANIA | Przepływ normalnego zapytania |
| 8 | Atak z PII (`Mój PESEL to 44051401359`) | Decyzja `redact`, PESEL wycięty przed modelem | — | DO WYKONANIA | Ochrona danych osobowych |
| 9 | Atak prompt injection (`Ignore previous instructions...`) | Decyzja `block`, nagłówek `X-Control-Decision: block`, status 200/odmowa | — | DO WYKONANIA | Blokada wstrzyknięcia |
| 10 | `make selftest` | Wykonanie testów live przeciwko `http://127.0.0.1:8080` | — | DO WYKONANIA | Sprawdzenie runnera jurora |
| 11 | `make verify-audit` | Weryfikacja integralności łańcucha hashy w `var/audit.jsonl` | — | DO WYKONANIA | Łańcuch SHA-256 nienaruszony |
| 12 | Weryfikacja plików zgłoszenia | `docs/pitch/draft-slides.pdf` istnieje i ma ≤5 stron; `docs/submission/draft.md` gotowy | — | DO WYKONANIA | Formalia zgłoszenia |

---

## 2. Zgłoszone błędy i status napraw

| ID Błędu | Krok | Opis problemu | Zgłoszono do | Status naprawy |
|---|---|---|---|---|
| — | — | Brak krytycznych błędów blokujących | — | — |

---

## 3. Podsumowanie gotowości do zgłoszenia o 19:45

- [ ] Świeży klon przechodzi wszystkie kroki z `README.md`.
- [ ] Kod na gałęzi `main` oznaczony tagiem `draft-20`.
- [ ] Formularz na platformie HackTribe wypełniony treścią z `docs/submission/draft.md`.
- [ ] Załączono plik `docs/pitch/draft-slides.pdf`.
- [ ] Zapisano zrzut potwierdzenia w `docs/submission/draft-confirmation.png`.
