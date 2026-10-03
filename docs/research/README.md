# Eksploracja i brainstorming — synteza

Stan: 2026-10-03, ok. 12:10. Siedmiu agentów w dwóch falach: najpierw przegląd istniejących narzędzi i zagrożeń, potem brainstorming z trzech perspektyw. Ten plik zbiera wnioski i rozbieżności z [PLAN](../PLAN.md) i [ADR](../adr/README.md). Szczegóły i źródła (URL-e, licencje) są w plikach poniżej.

| Plik | Fala | Perspektywa / skill |
|---|---|---|
| [01-gatewaye-i-proxy.md](01-gatewaye-i-proxy.md) | 1 | 22 gatewaye i frameworki OSS + 5 komercyjnych; `competitive-landscape` |
| [02-detektory-i-modele.md](02-detektory-i-modele.md) | 1 | modele guard, PII, sekrety, supply chain; pomiar na M5 Pro |
| [03-testy-i-red-teaming.md](03-testy-i-red-teaming.md) | 1 | garak, promptfoo, zbiory danych, projekt testów; `llm-evaluation` |
| [04-zagrozenia-i-katalog-kontroli.md](04-zagrozenia-i-katalog-kontroli.md) | 1 | STRIDE, drzewo ataku, katalog C01–C24, format feedu sygnatur; `stride-analysis-patterns`, `attack-tree-construction` |
| [10-brainstorm-jury-i-strategia.md](10-brainstorm-jury-i-strategia.md) | 2 | sędzia i strateg: wyróżnik, momenty „wow”, pitch; `competitive-landscape` |
| [11-brainstorm-red-team.md](11-brainstorm-red-team.md) | 2 | red team jury: 20 ataków, pułapki fałszywych alarmów, 29 przypadków testowych; `attack-tree-construction` |
| [12-brainstorm-budowa.md](12-brainstorm-budowa.md) | 2 | lead engineer: reuse vs build, kontrakty, harmonogram torów; `lean-build`, `architecture-patterns`, `ai-debt-detector` |

## 1. Co już istnieje

- **Nikt nie łączy wszystkiego lokalnie i w OSS.** Gatewaye (LiteLLM, Kong, APISIX, Portkey) są mocne w routingu i limitach, ale kontrole semantyczne przekazują do płatnych chmur albo trzymają w wersjach Enterprise (01 §2). Najbliższy naszej wizji jest agentgateway (Rust, Apache-2.0: LLM + MCP + A2A, hot reload, CEL), ale nie ma lokalnej semantyki ani sygnatur ataków (01 §2).
- **Część znanych projektów jest martwa.** LLM Guard, Rebuff i TensorZero są zarchiwizowane, a mcp-scan przeszedł do Snyka i wymaga tokenu (01 §1, 02 §3). Bierzemy z nich pomysły, nie zależności.
- **LiteLLM to punkt odniesienia, ale nie fundament.** Audit logs i guardrails per klucz są w nim płatne, rozliczanie kosztów wymaga Postgresa, a w 2026 r. opublikowano dla niego 17 advisories GHSA (01 §2).
- **Nasza luka** (01 §4): jedna walidowana polityka (ALLOW/REDACT/BLOCK + budżety + sygnatury) z przeładowaniem bez restartu, lokalna semantyka z jawnym `on_error`, sygnatury znanych ataków, budżet liczony także dla modeli lokalnych, selftest na żywej instancji, audyt i raport w OSS.
- **Na pitch:** proxy mówi API OpenAI, więc da się je postawić za LiteLLM, Kongiem czy agentgateway. Uzupełniamy routing, nie konkurujemy z nim (01 §5). OWASP Agent Control Standard (2026-09) opisuje dokładnie nasz wzorzec kontroli w hookach (04 §0).

## 2. Reuse vs build — rekomendacja zbiorcza

| Komponent | Decyzja | Źródło |
|---|---|---|
| Proxy | **budujemy** cienkie FastAPI; nie owijamy LiteLLM ani agentgateway, bo jury ocenia naszą architekturę | 01 §5, 12 §1 |
| PII | regexy + `python-stdnum` (LGPL-2.1+, sumy kontrolne PESEL/NIP/REGON/IBAN) | 02 §2, 12 §1 |
| Sekrety | reguły w feedzie sygnatur wzorowane na `gitleaks.toml` (MIT), bez `detect-secrets` | 12 §1 (wbrew 02 §5) |
| Injection — model | Llama Prompt Guard 2 86M przez ONNX (`onnxruntime` + `tokenizers`, bez torch), ok. 110 ms na CPU; licencja Llama 4 Community, w README napis „Built with Llama” | 02 §1b, 12 §1 |
| Injection — heurystyki | własna normalizacja (NFKC, zero-width, confusables, dekodowanie base64) + ok. 30 fraz EN/PL | 11 §6, 04 C06 |
| Guard LLM (treść szkodliwa) | `llama-guard3:1b` w Ollamie, zapasowo `granite3-guardian:2b`; po drafcie | 02 §5, 12 §3 |
| Sygnatury znanych ataków | własny silnik YAML w stylu Sigma/YARA z testami w regule; pickle przez stdlib `pickletools`; `picklescan`/`modelscan` tylko do plików artefaktów | 04 §5, 12 §1 |
| Budżety | in-memory, ceny w polityce (bez JSON-a z LiteLLM) | 12 §1 (wbrew 01 §5) |
| Audyt | JSONL z łańcuchem hashy, treść zawsze zredagowana | 12 §1, 10 §6 |
| Dashboard | statyczny HTML + JS, metryki liczone ze zdarzeń audytu | 10 §4, 12 §1 |
| Testy | pytest z `--target` (offline przez ASGI albo na żywą instancję), JUnit przez `--junitxml` | 12 §1, 03 §3 |
| Red team | `garak` (Apache-2.0) przez `uvx`, poza lockiem; raport przed/po proxy | 03 §1 |

## 3. Zgoda wszystkich perspektyw

1. **Kontrakty przed równoległą pracą.** Do ok. 13:30 jedna osoba zamraża: `Interaction`, `Finding` (bez akcji), `Decision`, port `Detector`, schemat polityki v1, zdarzenie `audit.v1` i format odpowiedzi blokującej (12 §4).
2. **Blokada jako poprawna odpowiedź OpenAI.** HTTP 200, `finish_reason: "content_filter"`, nagłówek `X-Control-Decision`, pole `control_layer`. Wyjątki: 401 (brak klucza) i 400 (złe wejście). Bez 429 przy budżecie, bo narzędzia traktują kody błędów jak awarię, a SDK OpenAI ponawia 429 `[INFERENCE]` (03, 11 §6, 12 §4).
3. **„Każda decyzja ma paragon”.** Odpowiedź i wpis audytu niosą `control_id`, wersję i hash polityki oraz feedu, tagi OWASP/ASI/ATLAS i opóźnienie każdego etapu (10 §6).
4. **Moment W1 dopracowany przed 20:00.** Jury zmienia `policy.yaml`, a ten sam prompt od razu dostaje inną decyzję. Zły YAML jest odrzucany, działa ostatnia poprawna polityka, a powód odrzucenia widać na dashboardzie (10 §3, 11 §6).
5. **Detektory skanują wszystko.** Wszystkie wiadomości, w tym system, historię i `role: tool`, oraz `tools[].description`, po wspólnej normalizacji (11 §6). Kontrole narzędzi działają na `tools`/`tool_calls` w ruchu OpenAI, więc adapter MCP zostaje w backlogu (04, 12 §5).
6. **Pułapki fałszywych alarmów w każdym pliku przypadków.** Nadmierne blokowanie też traci punkty (11 §2).

## 4. Proponowane zmiany w PLAN i ADR

| # | Zmiana | Dlaczego | Źródło |
|---|---|---|---|
| Z-1 | ADR-0002 → **Accepted** z poprawkami: Python **3.12** (modelscan wymaga <3.13); proxy natywnie przez `uv run`; ONNX w procesie; Ollama jako natywny proces obok (Metal); Docker Compose z niewystawionym portem 11434 tylko jako deliverable | runtime i wydajność na Macu | 12 §2, 04 D01 |
| Z-2 | Zamiast ADR na każdą bibliotekę jeden **ADR-0005 „Zależności i modele v1”** + kontrakt HTTP blokady | czas do 20:00 | 12 §2 |
| Z-3 | **Streaming buforowany od F0** (sprawdzamy całość, potem odtwarzamy jako SSE) + allowlista ścieżek HTTP (`/v1/chat/completions`, `/v1/models`) | `stream:true` omija kontrole wyjścia; `/api/pull` otwiera Probllama (CVE-2024-37032) | 11 §5 |
| Z-4 | **C06 (heurystyki injection) z F3 do F1**; PG2-86M jako tor równoległy przed draftem, w drafcie tylko jeśli zielony do 18:00 | pierwsze prompty jury to „ignore previous instructions” | 11 §5, 12 §3 |
| Z-5 | **Minimalny dashboard już w drafcie** (feed decyzji + liczniki), pełny w F5 | raportowanie to 20% oceny | 10 §6, 12 §3 |
| Z-6 | **Łańcuch hashy audytu (C20), egress markdown (C14) i redakcja treści w audycie: P1 → P0** | tani, mocny argument przy raportowaniu | 10 §6, 11 §6 |
| Z-7 | Jeden runner testów (pytest `--target`) zamiast osobnego CLI `selftest` | jedna ścieżka, mniej kodu | 12 §1 |
| Z-8 | ADR-0003: **brak sekcji kontroli = kontrola wyłączona** + ostrzeżenie „posture weakened” na dashboardzie; przeładowanie przez polling sha256 co 1 s | jury usuwa kontrole na żywo | 11 §6, 12 §1 |
| Z-9 | Spike modeli Ollamy **po** szkielecie, nie przed nim | nie blokuje F0 | 10 §6, 12 §3 |

## 5. Zakres pierwszego draftu (20:00)

Łączy red team (11 §3), lead engineera (12 §3) i strategię (10 §5):

- Proxy `/v1/chat/completions` (+ `/v1/models`) z buforowanym streamingiem, klucz API → agent, allowlista modeli.
- Polityka v1 z przeładowaniem bez restartu i ostatnią poprawną wersją; warianty `strict`/`lenient`.
- Wspólna normalizacja + C04 PII (EN/PL z sumami kontrolnymi), C05 sekrety, C06 heurystyki injection EN/PL.
- C15–C17: budżety tokenów i kosztu, wykrywanie pętli, limity rozmiaru i `max_tokens`; C21 fail-closed.
- Audyt JSONL (zredagowany, z łańcuchem hashy), minimalny dashboard, eksport CSV.
- ~30 przypadków w `tests/cases/*.yaml` (negatywy i pozytywy), `make selftest` na żywej instancji.
- README z positioning statement i instrukcją podpięcia agenta (zmiana `base_url`), diagram architektury, `docs/ai-usage/`.
- Opcjonalnie: PG2-86M, jeśli tor E jest zielony do 18:00. Freeze 19:00, zgłoszenie 19:45.

**Po drafcie do 4.10 11:00:** feed sygnatur z przeładowaniem bez restartu i testami w regułach (C10, C11, C18), kontrole narzędzi (C03, C09), guard LLM, C14 i C22, p50/p95 i `/metrics`, demo agent z narzędziami, garak przed/po proxy, Compose na czystej maszynie, audyt długu, slajdy (12 §3).

## 6. Momenty „wow” w demo

| # | Moment | Kryteria |
|---|---|---|
| W1 | Edycja polityki na żywo → ten sam prompt dostaje inną decyzję; zły YAML odrzucony | Robustness 30, Architecture 20 |
| W2 | Nowa sygnatura (CVE-2025-68664) w feedzie → blokada bez restartu, selftest od razu ma nowe przypadki | Robustness 30, Testy 15–20 |
| W3 | Agent w pętli zatrzymany, wskaźnik budżetu (także koszt lokalnego compute) dochodzi do limitu | Reporting 20, Robustness 30 |
| W4 | Selftest → tabela per kontrola + garak przed/po proxy | Testy 15–20, Reporting 20 |
| W5 | Zatrzymanie Ollamy → kontrole semantyczne fail-closed, deterministyczne dalej działają | Robustness 30, Architecture 20 |

Źródło: 10 §3.

## 7. Do decyzji zespołu teraz

1. Akceptacja Z-1 (stack i runtime) i Z-2 (zbiorczy ADR-0005).
2. Akceptacja zmian Z-3…Z-9 w planie.
3. Podział torów A–F z 12 §3 (integrator A jako jedyny właściciel `core/` i `app.py`).
4. Instalacja Ollamy i pobranie modeli od razu, równolegle z I0 (`ollama` nie jest jeszcze zainstalowana).
5. Pytanie do organizatorów: co musi zawierać draft o 20:00.

## 8. Uwagi

- Agent badający detektory pobrał ok. 1.5 GB modeli ONNX do `~/.cache/huggingface` podczas pomiarów (02).
- Część danych to `[INFERENCE]` albo `[niezweryfikowane]`; są oznaczone w plikach źródłowych.
- OWASP LLM Top 10 ma już wersję 2026 (zmieniona numeracja); katalog używa ID z 2025 z mapowaniem na 2026 (04 §0).
