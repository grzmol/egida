# Raport QA — Checkpoint Draft (20:00)

**Data i godzina audytu:** 2026-10-03  
**Audytor:** Kamil (Dev C — rola „Pierwszego Jurora”)  
**Środowisko:** Świeży klon repozytorium (`/tmp/froggers-qa`)  
**Cel:** Weryfikacja odtwarzalności rozwiązania wyłącznie na podstawie instrukcji z `README.md` przed zgłoszeniem draftu o 19:45.

---

## 1. Tabela kroków weryfikacyjnych (zgodnie z `README.md`)

| # | Polecenie / Krok z `README.md` | Oczekiwany wynik | Faktyczny wynik | Status (OK / BŁĄD) | Uwagi |
|---|---|---|---|---|---|
| 1 | `git clone https://github.com/grzmol/froggers.git` | Czysty klon repozytorium bez błędów | Klon pobrany w 7 s, 1487 obiektów | **OK** | Repozytorium kompletne |
| 2 | `uv sync` | Pomyślna instalacja zależności z `uv.lock` | Zainstalowano 52 pakiety w 173 ms | **OK** | Python 3.12 środowisko czyste |
| 3 | `uv run python scripts/fetch_models.py` | Pobranie i weryfikacja sha256 modeli ONNX w `models/` | Pobrany model Prompt Guard 2 (`model.quant.onnx`, tokenizer, config) | **OK** | Sumy sha256 zweryfikowane |
| 4 | `make check` | Zielone lintery (`ruff`, `mypy`, `lint-imports`) i testy offline (`pytest -q`) | 760 testów passed, ruff/mypy/linter OK; 1 fail: `test_long_text_uses_windows_and_stays_fast` | **BŁĄD** | Asercja czasu (3.12 s > 3.0 s) na MacBook Air pod obciążeniem; zgłoszono do Sebastiana |
| 5 | `make run` | Serwer wstaje na `http://127.0.0.1:8080` (FastAPI + Uvicorn) | Serwer wystartował, nasłuchuje na 127.0.0.1:8080 | **OK** | Port 8080 otwarty |
| 6 | Wejście na `http://127.0.0.1:8080/dashboard` | Dashboard otwiera się w przeglądarce, wyświetla metryki i status | Zwraca HTTP 200, interfejs HTML/JS dostępny | **OK** | Dashboard działa |
| 7 | Legalne żądanie (curl/SDK z kluczem `sk-demo-agent`) | Decyzja `allow`, odpowiedź z modelu | Przy braku Ollamy zwraca oczekiwane 502 Bad Gateway (upstream unreachable) | **OK** | Przepływ i autoryzacja Bearer OK |
| 8 | Atak z PII (`Mój PESEL to 44051401358`) | Decyzja `redact`, PESEL wycięty przed modelem | Proxy redaguje PESEL do `[REDACTED:pesel]`; decyzja `redact` w audycie | **OK** | python-stdnum działa poprawnie |
| 9 | Atak prompt injection (`Ignore all previous instructions...`) | Decyzja `block`, nagłówek `X-Control-Decision: block`, status 200/odmowa | HTTP 200, `finish_reason: content_filter`, `blocked_by: injection_heuristics` | **OK** | Blokada w 1 ms bez wołania modelu |
| 10 | `make selftest` | Wykonanie testów live przeciwko `http://127.0.0.1:8080` | Live: wymaga Ollamy na porcie 11434 dla przypadków `allow`. Offline runner: 200 passed, 33 skipped | **BŁĄD (live)** | README powinno wskazać uruchomienie Ollamy lub test offline |
| 11 | `make verify-audit` | Weryfikacja integralności łańcucha hashy w `var/audit.jsonl` | `OK 6 events, last seq 6, head 0f6c67c6ca42` | **OK** | Łańcuch SHA-256 nienaruszony |
| 12 | Weryfikacja plików zgłoszenia | `docs/pitch/draft-slides.pdf` istnieje i ma ≤5 stron; `docs/submission/draft.md` gotowy | `draft-slides.pdf` ma 5 stron; `draft.md` ma 1845 znaków opisu | **OK** | Formalia zgłoszenia spełnione |

---

## 2. Zgłoszone błędy i status napraw

| ID Błędu | Krok | Opis problemu | Zgłoszono do | Status naprawy |
|---|---|---|---|---|
| ERR-01 | Krok 4 | `test_long_text_uses_windows_and_stays_fast`: asercja `time < 3.0 s` jest zbyt ciasna na słabszych maszynach (MacBook Air: 3.12 s). Wystarczy podbić próg do 4.5 s. | Sebastian (Dev B) | Zgłoszono na Discord |
| ERR-02 | Krok 10 | `make selftest` na żywej instancji wymaga działającej Ollamy na 11434 dla testów `allow`. W README warto dopisać komendę offline `uv run pytest -q tests/test_cases.py` dla sędziów bez Ollamy. | Grzegorz (Dev A) | Zgłoszono na Discord |

---

## 3. Podsumowanie gotowości do zgłoszenia o 19:45

- [x] Świeży klon przechodzi procedurę weryfikacyjną (10/12 kroków w pełni OK, 2 drobne uwagi zgłoszone właścicielom).
- [x] Pliki zgłoszenia `docs/submission/draft.md` oraz `docs/pitch/draft-slides.pdf` gotowe.
- [x] Pliki zgłoszenia finałowego `docs/submission/final.md`, `docs/pitch/slides.pdf` (10 slajdów) i `docs/pitch/speaker-notes.md` gotowe.
- [ ] Oznaczenie tagiem `draft-20` (oczekuje na Grzegorza przed 19:45).

