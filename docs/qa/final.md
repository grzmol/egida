# Raport QA: zgłoszenie finałowe (bramki A8 na `freeze-0830`)

**Data i godzina audytu:** 2026-10-03 (sobota), ok. 16:40-16:50  
**Audytor:** Kamil (Dev C, rola „Pierwszego Jurora”). Przebiegi wykonali agenci na prośbę Grzegorza, każdy na osobnym świeżym klonie.  
**Commit:** tagi `freeze-0830` = `draft-20` = `26e0e15` (commit z 3.10 16:31; zespół przesunął freeze wcześniej). Tag `final` wskazuje późniejszy commit, który zmienia tylko dokumentację. Dlatego wyniki dotyczą też `final`.  
**Środowisko:** świeże klony, macOS arm64, bez Ollamy i modeli ONNX. Przypadki selftestu używają atrapy upstreamu zgodnej z OpenAI (`/chat/completions`).

---

## 1. Kroki weryfikacji (według `README.md`)

| # | Polecenie / krok z `README.md` | Oczekiwany wynik | Faktyczny wynik | Status (OK / BŁĄD) | Uwagi |
|---|---|---|---|---|---|
| 1 | `git clone https://github.com/grzmol/froggers.git` | Czysty klon repozytorium | Klony bez błędów; w historii 0 prawdziwych sekretów (tylko przykład AWS z dokumentacji, próbka jwt.io, klucz PEM `FAKEKEY`), brak plików > 1 MB | **OK** | Repo prywatne: jury dostaje dostęp od zespołu |
| 2 | `git checkout freeze-0830` (`final`) | Przełączenie na tag | `26e0e15` | **OK** | |
| 3 | `uv sync` | Instalacja zależności z `uv.lock` | Bez błędów; `uv lock --check` OK | **OK** | |
| 4 | `make models` | Pobranie Prompt Guard 2 (opcjonalny, domyślnie wyłączony) | Nie uruchomiono (łącze na miejscu ~0,5 MB/s); 39 testów ONNX pominiętych | **OK (pominięty)** | Polityka `policy.strict.yaml` bez `make models` blokuje wszystko (fail-closed); patrz uwagi |
| 5 | `make check` | ruff, mypy, lint-imports, testy offline | ruff, format (93 pliki), mypy (42 pliki), lint-imports (2 kontrakty), pytest **930 passed, 76 skipped, 0 failed**; drzewo czyste; 2 kolejne przebiegi identyczne | **OK** | Pominięte: 39 brak modelu ONNX, 33 wyłączone kontrole, 4 wymagają Ollamy z `llama-guard3:1b` |
| 6 | `make run` | Start proxy na 127.0.0.1:8080 | Proxy działa; wszystkie endpointy z README zwracają 200 | **OK** | |
| 7 | Dashboard `http://127.0.0.1:8080/dashboard` | Dane, strumień decyzji, eksport | Brak błędów konsoli, dane < 3 s, `blocked_by` w strumieniu, eksport CSV/JSONL = dziennik audytu, `/api/audit/verify` ok, `/metrics` text/plain 0.0.4, zmiana polityki widoczna bez przeładowania strony; układ OK 1280/1920 | **OK** | Panel „Evidence” na świeżym klonie: „No evidence yet”; patrz uwagi |
| 8 | Zwykłe żądanie agenta (snippet `agent.py` / curl z README) | `allow`/`redact`, odpowiedź modelu | Snippet → `redact`; curl z atakiem → 200 `content_filter`; przy wyłączonym upstreamie benign → 502 `upstream_error` (format OpenAI), bez 500 i tracebacków | **OK** | Atrapa upstreamu zamiast Ollamy |
| 9 | Ochrona PII i sekretów | PESEL `redact`, sekret `block` | PESEL zredagowany (także w strumieniu; dziennik audytu bez surowego PESEL), klucz AWS zablokowany także przy niedostępnym upstreamie | **OK** | |
| 10 | Prompt injection / RCE / regresje bezpieczeństwa | `block` bez wywołania modelu | 18/18: m.in. błędne `max_tokens`/`model`/129 narzędzi → 400, injection w schemacie narzędzia → block, pickle w base64/MIME → SIG-0001+SIG-0006, zły klucz 401, dziennik audytu tylko do odczytu → 503 `audit_unavailable`, wejście 100001 znaków → block `limit` | **OK** | |
| 11 | `CONTROL_LAYER_SELFTEST_AGENT=selftest-agent make selftest` | 0 failed | **184 passed, 56 skipped, 0 failed**; drugi przebieg identyczny | **OK** | Pominięte: 29 tylko offline, 24 harmful (wyłączona), 3 prompt_guard (wyłączona) |
| 12 | `make verify-audit` | `OK n events` | `OK 360 events` (po 2 przebiegach selftestu) | **OK** | |
| 13 | W1 przeładowanie polityki na żywo | redact → block bez restartu; proxy odrzuca błędną politykę | redact→block 0,96-1,01 s; próg 1.5 → `policy_rejected`, działa stara polityka; przywrócenie 0,64-1,05 s | **OK** | |
| 14 | W2 feed sygnatur | Nowa reguła feedu działa bez restartu | allow→block 0,37-0,96 s po dodaniu SIG-0005 (feed 1.1.0); błędny regex → `feed_rejected`; obniżenie wersji do 1.0.9 → odrzucone | **OK** | |
| 15 | W3 pętle i budżety | Proxy ucina pętlę, limit żądań działa | 5× allow, potem block `budget.loop`; ci-agent żądanie 31 → block `budget.requests`, HTTP 200 `content_filter`, nigdy 429 | **OK** | |
| 16 | W4 dowody | Tabele README = `docs/evidence/*.json` | garak (12 sond × 6 liczb) i FP/FN: 0 rozbieżności | **OK** | |
| 17 | Docker Compose (statycznie + obraz) | Poprawny compose, na hoście tylko proxy | Config poprawny; opublikowany tylko 127.0.0.1:8080; obraz uid 10001, config tylko do odczytu; redact+block w kontenerze OK; testy zgodności 12 passed | **OK (częściowo)** | Pełne `docker compose up` z pobraniem modelu nie zostało uruchomione (łącze ~0,5 MB/s). To pokrywa QA Macieja D6 12/12 (`docs/deploy.md`) |

**Wynik: 17/17 OK, 0 BŁĄD.**

---

## 2. Uwagi nieblokujące (znane ograniczenia, bez zmian kodu po freeze)

1. Sekret podzielony na dwie wiadomości użytkownika (`AKIAIOSF` + `ODNN7EXAMPLE`) przechodzi. Detektor sekretów skanuje każdy tekst osobno.
2. PESEL ze spacjami (`440 514 013 59`) proxy redaguje jako `[REDACTED:phone]` na 9 cyfrach. Ostatnie 2 cyfry zostają jawne.
3. Panel „Evidence” na dashboardzie na świeżym klonie pokazuje „No evidence yet”. Panel czyta `var/redteam/summary.json` i `var/eval.json`. Zatwierdzone dowody są w `docs/evidence/`.
4. Baner postawy działa dla rodzaju detektora. Wyłączony `egress.tool` nie ma oznaczenia, bo rodzaj `egress` jest włączony (tabela kontroli to pokazuje).
5. `CONTROL_LAYER_POLICY=config/policy.strict.yaml make run` bez `make models` blokuje każde żądanie (Prompt Guard `on_error: block`, fail-closed z założenia).
6. Przy niedostępnym upstreamie żądanie z PESEL (`redact`) dostaje 502, bo po redakcji proxy przekazuje żądanie do modelu (fail-closed, bez wycieku).
7. Proxy buforuje strumień odpowiedzi: SSE wychodzi po kontrolach wyjścia (z założenia).
8. `harmful_content` nie jest w `config/policy.yaml` (30 przypadków pominiętych). `prompt_guard` jest wyłączony (wymaga `make models`).

---

## 3. Gotowość do zgłoszenia finałowego (10:30)

- [x] Prezentacja finałowa `docs/pitch/slides.pdf` jest gotowa (≤ 10 stron).
- [x] Notatki mówcy `docs/pitch/speaker-notes.md` są gotowe (czas wystąpienia ≤ 5 min).
- [x] Formularz zgłoszenia finałowego `docs/submission/final.md` jest gotowy i ma sprawdzone limity znaków.
- [ ] Tag `final` (Grzegorz, A8 krok 7).
