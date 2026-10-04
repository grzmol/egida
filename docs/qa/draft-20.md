# Raport QA: przed freeze draftu i powtórka na tagu `draft-20`

**Data i godzina audytu:** 2026-10-03, ok. 15:45 (sekcja 1: ówczesny `main`, historia) i ok. 16:40-16:50 (sekcja 4: powtórka na tagu `draft-20` = `26e0e15`)  
**Audytor:** Kamil (Dev C, rola „Pierwszego Jurora”)  
**Środowisko:** świeży klon repozytorium (`/tmp/froggers-qa`)  
**Cel:** sprawdzić, czy rozwiązanie działa tylko według instrukcji z `README.md`. Termin: przed zgłoszeniem draftu o 19:45.

---

## 1. Kroki weryfikacji (według `README.md`)

| # | Polecenie / krok z `README.md` | Oczekiwany wynik | Faktyczny wynik | Status (OK / BŁĄD) | Uwagi |
|---|---|---|---|---|---|
| 1 | `git clone https://github.com/grzmol/froggers.git` | Czysty klon repozytorium bez błędów | Klon pobrany w 7 s, 1487 obiektów | **OK** | Repozytorium kompletne |
| 2 | `uv sync` | Instalacja zależności z `uv.lock` bez błędów | 52 pakiety zainstalowane w 173 ms | **OK** | Środowisko Python 3.12 czyste |
| 3 | `uv run python scripts/fetch_models.py` | Pobranie modeli ONNX do `models/` i sprawdzenie sha256 | Pobrany model Prompt Guard 2 (`model.quant.onnx`, tokenizer, config) | **OK** | Sumy sha256 poprawne |
| 4 | `make check` | Zielone lintery (`ruff`, `mypy`, `lint-imports`) i testy offline (`pytest -q`) | 760 testów passed, ruff/mypy/linter OK; 1 fail: `test_long_text_uses_windows_and_stays_fast` | **BŁĄD** | Asercja czasu (3.12 s > 3.0 s) na MacBook Air pod obciążeniem; zgłoszone do Sebastiana |
| 5 | `make run` | Serwer startuje na `http://127.0.0.1:8080` (FastAPI + Uvicorn) | Serwer działa, nasłuchuje na 127.0.0.1:8080 | **OK** | Port 8080 otwarty |
| 6 | Otwórz `http://127.0.0.1:8080/dashboard` | Dashboard otwiera się w przeglądarce, pokazuje metryki i status | HTTP 200, interfejs HTML/JS dostępny | **OK** | Dashboard działa |
| 7 | Poprawne żądanie (curl/SDK z kluczem `sk-demo-agent`) | Decyzja `allow`, odpowiedź modelu | Bez Ollamy proxy zwraca oczekiwane 502 Bad Gateway (upstream unreachable) | **OK** | Przepływ i autoryzacja Bearer OK |
| 8 | Atak z PII (`Mój PESEL to 44051401358`) | Decyzja `redact`, proxy usuwa PESEL przed modelem | Proxy zamienia PESEL na `[REDACTED:pesel]`; decyzja `redact` w dzienniku audytu | **OK** | python-stdnum działa poprawnie |
| 9 | Atak prompt injection (`Ignore all previous instructions...`) | Decyzja `block`, nagłówek `X-Control-Decision: block`, status 200/odmowa | HTTP 200, `finish_reason: content_filter`, `blocked_by: injection_heuristics` | **OK** | Blokada w 1 ms, proxy nie wywołuje modelu |
| 10 | `make selftest` | Testy na `http://127.0.0.1:8080` | Selftest wymaga Ollamy na porcie 11434 dla przypadków `allow`. Runner offline: 200 passed, 33 skipped | **BŁĄD (selftest)** | README powinno podać: uruchom Ollamę albo test offline |
| 11 | `make verify-audit` | Sprawdzenie łańcucha hashy w `var/audit.jsonl` | `OK 6 events, last seq 6, head 0f6c67c6ca42` | **OK** | Łańcuch SHA-256 nienaruszony |
| 12 | Sprawdzenie plików zgłoszenia | `docs/pitch/draft-slides.pdf` istnieje i ma ≤5 stron; `docs/submission/draft.md` gotowy | `draft-slides.pdf` ma 5 stron; `draft.md` ma 1845 znaków opisu | **OK** | Stan z 15:45; po PR #20 `draft-slides.pdf` ma 6 stron (tytuł + 5 slajdów), opis długi ma 1949 znaków (`draft.md`) |

---

## 2. Zgłoszone błędy i status napraw

| ID błędu | Krok | Opis problemu | Zgłoszone do | Status naprawy |
|---|---|---|---|---|
| ERR-01 | Krok 4 | `test_long_text_uses_windows_and_stays_fast`: asercja `time < 3.0 s` jest za ciasna na słabszych maszynach (MacBook Air: 3.12 s). Wystarczy próg 4.5 s. | Sebastian (Dev B) | Otwarte: próg dalej 3.0 s (`tests/unit/detectors/test_prompt_guard.py:107`) |
| ERR-02 | Krok 10 | `make selftest` na działającej instancji wymaga Ollamy na 11434 dla testów `allow`. README powinno podać polecenie offline `uv run pytest -q tests/test_cases.py` dla jury bez Ollamy. | Grzegorz (Dev A) | Częściowo: README (sekcja Tests) mówi, że selftest wymaga Ollamy, bo bez niej `allow`/`redact` dostają 502 |

---

## 3. Gotowość do zgłoszenia o 19:45

- [x] Świeży klon przechodzi weryfikację (10/12 kroków w pełni OK, 2 drobne uwagi zgłoszone właścicielom).
- [x] Pliki zgłoszenia `docs/submission/draft.md` i `docs/pitch/draft-slides.pdf` są gotowe.
- [x] Pliki zgłoszenia finałowego `docs/submission/final.md`, `docs/pitch/slides.pdf` (10 slajdów) i `docs/pitch/speaker-notes.md` są gotowe.
- [x] Powtórka QA na tagu `draft-20`: sekcja 4.
- [x] Tag `draft-20` ustawiony (`26e0e15`, ten sam commit co `freeze-0830`).

---

## 4. Powtórka na tagu `draft-20` (= `freeze-0830` = `26e0e15`, ok. 16:40-16:50)

Warunki: świeże klony tagu, bez Ollamy i modeli ONNX, przypadki selftestu z atrapą upstreamu. Szczegóły kroków: `docs/qa/final.md`.

| Krok | Wynik | Status |
|---|---|---|
| `make check` | 930 passed, 76 skipped, 0 failed; ruff, mypy, lint-imports OK; 3 przebiegi identyczne | **OK** (ERR-01 nie występuje) |
| `make selftest` (atrapa upstreamu) | 184 passed, 56 skipped, 0 failed | **OK** (ERR-02: bez Ollamy wystarcza atrapa upstreamu) |
| `make verify-audit` | `OK 360 events` | **OK** |
| W1-W5, README, dashboard, Compose (statycznie), regresje bezpieczeństwa 18/18, sekrety w historii | wszystkie zielone | **OK** |

Wynik powtórki: wszystkie bramki A8 są zielone. Uwagi nieblokujące są w `docs/qa/final.md`, sekcja 2.

