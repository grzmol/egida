# 10 — Brainstorm: perspektywa jury (security engineering) i strategia hackathonowa

Stan: 2026-10-03, ~12:15. Rama: skill `competitive-landscape` (Blue Ocean Four Actions, positioning statement). Fakty z research 01–04 cytuję z sekcją; reszta to `[INFERENCE]`.

## 1. Co zbuduje typowy zespół i jak go pobić `[INFERENCE]`

| Typowy wzorzec konkurencji | Słabość widoczna dla jury | Jak wygrywamy |
|---|---|---|
| Cienki wrapper FastAPI + regex PII + „LLM-as-judge” na każdym żądaniu | p95 w sekundach, przepuszcza parafrazy PL | kolejność tanie→drogie i p95 per etap w telemetrii (PLAN §3); PG2-86M ~110 ms (02 §5) |
| Owinięcie LiteLLM / NeMo Guardrails | jury ocenia cudzą architekturę; audyt i guardrails per klucz w Enterprise (01 §2) | własny rdzeń heksagonalny, LiteLLM tylko jako źródło cen (01 §5) |
| Konfiguracja czytana przy starcie | jury edytuje plik → nic się nie dzieje albo crash | hot reload + ostatnia poprawna + wpis w audycie (C19, 03 §4 #24–25) |
| Timeout detektora = przepuszczenie | fail-open, czyli obejście A2.2 (04 §3) | `on_error` per kontrola (ADR-0004, C21) |
| Kilka testów pytest, same negatywy | brak pozytywów → nadmierne blokowanie niewidoczne | YAML z pozytywami XSTest-like, `selftest --target` (03 §3) |
| „Historyczne ataki” = jeden regex `rm -rf` | R4 pokazane symbolicznie | feed sygnatur z CVE i testami w regule (04 §5–6) |
| Streamlit z licznikami | brak rozróżnienia zarząd/bezpieczeństwo, brak eksportu | dwa widoki + eksport + łańcuch hashy (§4) |

**Rekomendacja (ranking):** 1) nie rywalizować liczbą detektorów, tylko *dowodliwością* każdej decyzji; 2) obsłużyć 10 prób ad hoc z 03 §4 (#1, #4, #6, #7, #8, #11, #14, #15, #20, #24) zanim dodamy cokolwiek z backlogu.

## 2. Four Actions (vs zespoły i vs narzędzia z 01)

| Akcja | Co | Uzasadnienie |
|---|---|---|
| **Eliminate** | streaming w wersji draft; routing do wielu dostawców; logowanie do dashboardu; własny agent | 0 pkt w kryteriach; ryzyko z PLAN §9 |
| **Eliminate** | LLM-as-judge na każdym żądaniu | zabija p95 (Architecture 20%) |
| **Reduce** | liczba modeli semantycznych do 1 głównego + fallback (02 §5) | mniej RAM, prostszy spike |
| **Reduce** | design UI do jednej strony HTML | Design ma 0% (PLAN §1) |
| **Raise** | wyjaśnialność decyzji: `control_id`, wersja polityki i feedu, tagi OWASP/ASI/ATLAS, opóźnienie per etap w każdym wpisie | Security reporting 20% + rozmowa z jury |
| **Raise** | odporność na edycję przez jury (walidacja, ostatnia poprawna, metryka reloadu jak w agentgateway, 01 §2) | Robustness 30% |
| **Raise** | polski język w testach i detekcji (03 §4 #11) | jury z Polski `[INFERENCE]` |
| **Create** | „paragon decyzji”: nagłówki `X-Control-Decision`, `X-Control-Id`, `X-Policy-Version` przy HTTP 200 z odmową (format zgodny z garak/promptfoo, 03 §1) | nikt z 01 tego nie łączy `[INFERENCE]` |
| **Create** | reguła sygnatury niesie własne testy → `selftest` rośnie z feedem (04 §5) | R4 + R6 jednym ruchem |
| **Create** | mapa pokrycia OWASP LLM 2025/2026 + ASI per kontrola, liczona z polityki | kontra wobec 01 §4 #6 |
| **Create** (P1) | „what-if”: przed zastosowaniem nowej polityki odtwórz ostatnie N zdarzeń audytu i pokaż różnicę decyzji | odpowiedź na „jury zmienia progi” |

**Niezgodności z PLAN:** mapa OWASP jest w backlogu (PLAN §5) — proponuję P0, bo to tagi w polityce, nie kod. C20 (łańcuch hashy) ma P1 (04 §4) — proponuję P0 dla widoku security, koszt `[INFERENCE]` < 1 h.

**Positioning statement:**
> Dla zespołów bezpieczeństwa w instytucjach finansowych, które wpuszczają agentów AI do systemów produkcyjnych, AI Control Layer to lokalna warstwa polityk (policy-as-code), która przy każdej interakcji agenta decyduje ALLOW/REDACT/BLOCK, pilnuje budżetów i blokuje znane exploity. W odróżnieniu od gatewayów (LiteLLM, agentgateway), które delegują semantykę do chmury lub licencji Enterprise (01 §2–3), każda nasza decyzja ma paragon z kontrolą, wersją polityki i tagiem OWASP, a produkt sam dowodzi swojego pokrycia testem na żywej instancji.

**Co zapamięta jury:** hasło „Każda decyzja ma paragon” + moment, w którym jury samo edytuje plik i widzi zmianę na dashboardzie w ciągu sekund.

## 3. Momenty „wow” w demo

| # | Moment | Kryteria (waga) | Wymagania | Ranking |
|---|---|---|---|---|
| W1 | Jury zmienia `pii.action: redact → block` (albo psuje YAML) → dashboard pokazuje nową wersję polityki, ten sam prompt zmienia decyzję; zły YAML odrzucony, działa ostatnia poprawna | Robustness 30, Architecture 20 | R1, C19 | **1** |
| W2 | Dopisanie SIG-0002 (LangChain `lc`, CVE-2025-68664) do feedu → blokada bez restartu, `selftest` od razu ma 2 nowe przypadki | Robustness 30, Tests 15–20 | R4, R6 | **2** |
| W3 | Agent w pętli (20 identycznych wywołań, C16) zatrzymany; wskaźnik budżetu agenta (także koszt compute lokalnego, 01 §4 #4) dochodzi do limitu | Reporting 20, Robustness 30 | R3 | **3** |
| W4 | `selftest --target` → tabela per kontrola (pozytywy/negatywy, p50/p95) + garak przed/po proxy (03 §3) | Tests 15–20, Reporting 20 | R6 | **4** |
| W5 | Zatrzymanie Ollamy w trakcie demo → kontrole semantyczne fail-closed, deterministyczne działają, dashboard pokazuje zdrowie detektorów | Robustness 30, Architecture 20 | C21 | **5** |

Polska parafraza injection w wyniku narzędzia (03 §4 #11–12) wpleciona w W1 lub W5, bez osobnego slotu.

## 4. Dashboard i raportowanie (20%)

| Element | Zarząd | Zespół bezpieczeństwa |
|---|---|---|
| Postawa | wynik pokrycia: % kontrol OWASP/ASI włączonych i przetestowanych | macierz kontrola × tag OWASP/ASI/ATLAS × status testu |
| Zagrożenia | liczba BLOCK/REDACT w czasie, top 5 kategorii | żywy feed decyzji: agent, `control_id`, fragment po redakcji, wersja polityki/feedu |
| Budżety | wydatki per agent/model vs limit (API zewn. + compute lokalny), prognoza wyczerpania | odrzucenia budżetowe i pętle per agent |
| Wydajność | narzut proxy p95 | opóźnienie per etap pipeline'u, timeouty i `on_error` per detektor |
| Zmiany | ostatnia zmiana polityki (kto/kiedy) | dziennik zmian polityki i feedu z diffem i hashem; `feed_rejected`, `policy_rejected` |
| Zaufanie | wynik ostatniego `selftest` | eksport JSONL/CSV, weryfikacja łańcucha hashy (C20) |

**Technologia (ranking):** 1) jedna strona HTML serwowana przez FastAPI + SSE, czyta tylko porty metryk/audytu (PLAN §4) — zero dodatkowego procesu `[INFERENCE]`; 2) Streamlit — szybki, ale osobny proces; 3) Grafana — mocna dla skalowalności, za ciężka na 24 h.
**Niezgodność z PLAN:** dashboard jest w F5. Proponuję minimalny feed decyzji już w drafcie 20:00, bo jury przegląda dashboard i logi (spec §5).

## 5. Draft 20:00 i pitch

**Draft musi pokazać** (zawartość nieznana, PLAN §10 — przygotowujemy pełną listę):
1. README: positioning statement, `docker compose up` / `uv run`, jak podpiąć agenta zmianą `base_url`.
2. Diagram architektury (PLAN §3) + tabela kontroli z tagami OWASP (podzbiór P0 z 04 §4).
3. Działające proxy: C01, C02, C04, C05, C15–C17, hot reload z ostatnią poprawną.
4. `selftest` z tabelą wyników + `config/policy.strict.yaml` i `policy.lenient.yaml`.
5. Audyt JSONL i minimalna strona feedu decyzji.
6. Zrzut ekranu lub GIF z W1.

**Niezgodność z PLAN F0:** spike modeli semantycznych nie może blokować szkieletu — robimy go równolegle, a draft opieramy na kontrolach deterministycznych.

**Pitch (≤10 slajdów):**
1. Problem: agenci w banku = nowa powierzchnia ataku (lethal trifecta, 04 §3).
2. Positioning statement + hasło „Każda decyzja ma paragon”.
3. Architektura: porty, pipeline tanie→drogie, fail-closed.
4. Polityka jako kontrakt: progi block/redact, budżety, hot reload (W1).
5. Warstwy obrony: det + sem + sygnatury, mapa OWASP/ASI.
6. Historyczne ataki: feed z CVE (W2).
7. Budżety i pętle agentów (W3).
8. Raportowanie: widok zarządu vs bezpieczeństwa.
9. Dowód: `selftest`, garak przed/po, p95 (W4).
10. Wdrożenie i skalowanie: zmiana `base_url`, za LiteLLM/Kongiem (01 §5), porty pod Redis; roadmapa MCP/A2A.

## 6. Rekomendacje (ranking)

1. **Paragon decyzji jako oś produktu:** każdy wpis audytu i odpowiedź niosą `control_id`, wersję polityki/feedu, tagi OWASP/ASI i opóźnienie per etap.
2. **W1 dopracowane do perfekcji przed 20:00:** edycja polityki przez jury, odrzucenie złego YAML, widoczne na stronie feedu.
3. **Minimalny dashboard w drafcie** (HTML + SSE), nie w F5; dwa widoki (zarząd/bezpieczeństwo) do rana.
4. **Sygnatury z testami w regule** (04 §5) jako most R4→R6, demonstrowane przez W2.
5. **Mapa pokrycia OWASP i łańcuch hashy audytu awansowane do P0**; spike semantyczny równolegle, nie przed szkieletem.
