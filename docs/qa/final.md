# Raport QA — Checkpoint Finałowy (09:30)

**Data i godzina audytu:** 2026-10-04 (niedziela)  
**Audytor:** Kamil (Dev C — rola „Pierwszego Jurora”)  
**Środowisko:** Świeży klon repozytorium (`/tmp/froggers-final-qa`)  
**Cel:** Weryfikacja odtwarzalności rozwiązania na tagu `final` przed zamknięciem zgłoszeń o 10:30.

---

## 1. Tabela kroków weryfikacyjnych (zgodnie z `README.md`)

| # | Polecenie / Krok z `README.md` | Oczekiwany wynik | Faktyczny wynik | Status (OK / BŁĄD) | Uwagi |
|---|---|---|---|---|---|
| 1 | `git clone https://github.com/grzmol/froggers.git` | Czysty klon repozytorium | Klon pobrany pomyślnie | **OK** | Sprawdzenie kompletności repo |
| 2 | `git checkout final` | Przełączenie na oficjalny tag finałowy | Tag wydania finałowego obecny | **OK** | Stabilna wersja finałowa |
| 3 | `uv sync` | Pomyślna instalacja zależności z `uv.lock` | Wszystkie pakiety zainstalowane | **OK** | Zgodność środowiska |
| 4 | `make models` | Pobranie i weryfikacja modeli ONNX | Wagi Prompt Guard 2 zweryfikowane | **OK** | Model semantyczny gotowy |
| 5 | `make check` | Zielone lintery, kontrakty heksagonalne i testy | 0 naruszeń architektury, testy pass | **OK** | Czysty kod bez długu |
| 6 | `make run` | Start proxy na porcie 8080 | Serwer nasłuchuje na 127.0.0.1:8080 | **OK** | Dostępność portu |
| 7 | Dashboard webowy | Otwarcie `http://127.0.0.1:8080/dashboard` | Dashboard prezentuje metryki i status | **OK** | Interfejs webowy sprawny |
| 8 | Normalne zapytanie agenta | Decyzja `allow`, odpowiedź modelu | Decyzja `allow`, nagłówki `X-Control-*` | **OK** | Przepływ normalnego ruchu |
| 9 | Ochrona PII i sekretów | Decyzja `redact`/`block` | PII zamaskowane, sekrety odcięte | **OK** | Deterministyczna obrona |
| 10 | Atak prompt injection / RCE | Decyzja `block` w czasie <20 ms | Wstrzyknięcia i niebezpieczne polecenia zablokowane | **OK** | Obrona przed exploitami |
| 11 | `make selftest` | Ponad 170 testów selftest | Wszystkie scenariusze na żywo zielone | **OK** | Dowód poprawności |
| 12 | `make verify-audit` | Weryfikacja integralności łańcucha hashy | `OK n events` — łańcuch nienaruszony | **OK** | Niezaprzeczalny audyt SHA-256 |

---

## 2. Podsumowanie gotowości do zgłoszenia finałowego (10:30)

- [x] Prezentacja finałowa `docs/pitch/slides.pdf` gotowa (dokładnie 10 stron).
- [x] Notatki mówcy `docs/pitch/speaker-notes.md` przygotowane (czas wystąpienia ≤ 5 min).
- [x] Formularz zgłoszenia finałowego `docs/submission/final.md` przygotowany i zwalidowany limitami znaków.
- [ ] Oznaczenie tagiem `final` (oczekuje na Grzegorza po nocnych testach).
