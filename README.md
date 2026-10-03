# froggers — HackYeah 2026

Repozytorium zespołu na hackathon HackYeah 2026 (Kraków, 3–4 października 2026).

## Wybrane zadanie: AI Control Layer

**Partner Task — Goldman Sachs.** Lekka warstwa kontrolna (gateway / proxy / middleware / SDK) przechwytująca i nadzorująca ruch systemów agentowych AI: agent↔agent, aplikacja→agent, agent→MCP, agent→model. Polityki bezpieczeństwa, prywatności i budżetów pochodzą z jednego, centralnego źródła konfiguracji.

| | |
|---|---|
| Nagrody | 15 000 PLN brutto: 6 000 / 5 000 / 4 000 |
| Zespół | 1–6 osób |
| Okno pracy | start nie wcześniej niż 3.10 23:00, oddanie do 4.10 23:00 (wg RULES — patrz [Do potwierdzenia](#do-potwierdzenia)) |
| Język | angielski lub polski |
| Prawa autorskie | zostają przy nas |
| Pełna specyfikacja | [`knowledge-base/tasks/partner-goldman-sachs-ai-control-layer.md`](knowledge-base/tasks/partner-goldman-sachs-ai-control-layer.md) |

### Wymagania formalne

1. **Centralny silnik polityk** — jedna konfiguracja: kontrole, progi (blokuj vs. redaguj), dozwolone modele LLM, budżety.
2. **Kontrole hybrydowe** — deterministyczne (np. wykrywanie PII i sekretów, uwierzytelnianie, dostęp) + semantyczne oparte na AI.
3. **Budżety i zasoby** — limity tokenów, czasu obliczeń, dostępu do zasobów.
4. **Ochrona przed znanymi atakami** — np. wykonanie złośliwego kodu, niebezpieczna deserializacja, ataki na łańcuch dostaw repozytoriów modeli.
5. **Raportowanie i audyt** — metryki na żywo dla zarządu (zablokowane interakcje, zużycie budżetu) + eksportowalne logi audytowe dla zespołów bezpieczeństwa.
6. **Zestaw testów** — automatyczny, przypadki pozytywne (dozwolone) i negatywne (zablokowane).

Do tego: diagram architektury, przykładowa konfiguracja z różnymi poziomami restrykcyjności, prosty interaktywny dashboard i telemetria wydajności. Nie dostajemy płatnych API ani danych — używamy bibliotek open source i lokalnych modeli (np. Ollama).

### Jak oceniają

| Kryterium | Waga (CRITERIA) | Waga (RULES) |
|---|---|---|
| Odporność rozwiązania i jakość guardrails | 30% | 30% |
| Architektura i wydajność | 20% | 20% |
| Raportowanie bezpieczeństwa | 20% | 20% |
| Kompletność zestawu testów | 15% | 20% |
| Wdrażalność i skalowalność | 15% | 10% |

Jury bez przygotowania: uruchamia nasz zestaw testów, wpisuje własne prompty do działającej warstwy, zmienia konfigurację na żywo (usuwa kontrole, zmienia progi) i patrzy, czy zmiany działają.

## Dlaczego to zadanie

Przeanalizowaliśmy wszystkie 10 zadań pod kątem pisania projektu z pomocą AI. Kwoty, wagi i wymagania pochodzą z [bazy wiedzy](knowledge-base/README.md); oceny „+/−” to nasza ocena.

| Zadanie | AI dobrze koduje w tym stacku? | Ocena sprawdzalna kodem/testami? | Nagrody | Przeszkody | Miejsce |
|---|---|---|---|---|---|
| **AI Control Layer** | ++ Python/Go, regexy, Ollama, pytest | ++ jury uruchamia testy, prompty i zmiany konfiguracji na żywo | 15k PLN, 3 miejsca | brak; EN/PL, prawa zostają u nas | **1** |
| HubMI.pl | ++ zwykła aplikacja webowa z AI do dopasowań | + 40% za liczbę modułów, ale 40% to UX, WCAG i makiety | 15k PLN, 3 miejsca | przekazanie praw autorskich, oddanie kodu w 24 h, tylko po polsku, 18+, na miejscu | 2 |
| Huawei – Imagine What's Next | −− ArkTS/ArkUI API 20, DevEco, `.hap`; modele słabo znają ten stack | + | 25k PLN, 3 miejsca | tylko po angielsku, emulator i podpisywanie aplikacji | 3 |
| Kraków bez barier | + web i OpenStreetMap | − dwa różne zestawy kryteriów, 20% za model biznesowy | 5k PLN, 1 miejsce | przekazanie praw, wypłata do 180 dni | 4 |
| 5 zadań otwartych (AI, Defence, ImpactHer, Smart City, Sport) | ++ | −− 30% za pomysł i 20% za wygląd, ocena subiektywna | 8k PLN, 1 miejsce każde | brak | 5 |
| SuperTeam (Solana) | − Rust/Anchor, portfele, faucet | + demo transakcji on-chain | 3k PLN łącznie | sprzeczna waluta puli (USD czy PLN) | 6 |

Najważniejsze powody:

- **Konkretna specyfikacja.** Sześć formalnych wymagań da się zamienić w testy, które przechodzą albo nie — na takiej specyfikacji agenci AI pracują najlepiej.
- **Testy są częścią oceny** (15–20%). Generowanie wielu przypadków pozytywnych i negatywnych to mocna strona AI.
- **Wygląd nie jest oceniany** — kryterium Design ma 0%. Wystarczy prosty dashboard.
- **Kod zostaje nasz** — bez przekazania praw autorskich (w przeciwieństwie do HubMI i Krakowa).
- **Trzy nagrody** — większa szansa na wynik niż w zadaniach otwartych z jedną nagrodą.

**Alternatywa: HubMI.pl** — jeśli wolimy zadanie społeczne z prezentacją po polsku i przekazanie praw nam nie przeszkadza. 40% punktów daje liczba zrobionych modułów, a z AI można je dorobić szybko.

## Ocena ryzyka

1. **Ryzyko: średnie.** Kod jest przewidywalny; ryzykiem jest odporność na prompty, których jury nie przygotowuje wcześniej, i na zmiany konfiguracji w trakcie testów.
2. **Główne założenie.** Lokalny model przez Ollamę musi wyłapywać prompt injection wystarczająco dobrze i szybko, żeby demo nie zwalniało.
3. **Co sprawdzić najpierw.** Godzinny test: kilka małych modeli w Ollamie na ok. 30 promptach z atakami i bez nich; mierzymy trafność i czas odpowiedzi.
4. **Najmniejsza działająca wersja:**
   - proxy zgodne z API OpenAI;
   - plik YAML z politykami, przeładowywany bez restartu;
   - deterministyczne wykrywanie PII i sekretów (blokowanie albo redakcja);
   - budżet tokenów per agent;
   - log audytowy w JSONL;
   - testy w pytest uruchamiane jednym poleceniem.

   Potem: kontrole semantyczne, sygnatury znanych ataków (np. niebezpieczny pickle, wykonanie kodu), dashboard i telemetria.
5. **Na później.** Obsługa wielu protokołów naraz (agent↔agent, MCP), zewnętrzny system dostarczający sygnatury (na start lokalny plik), dopracowany frontend.

## Do potwierdzenia

- **Godziny pracy.** RULES tego zadania: start nie wcześniej niż 3.10 23:00, oddanie do 4.10 23:00. Kraków i HubMI mają 11:00 → 11:00. Potwierdzić u organizatorów.
- **Wagi kryteriów.** CRITERIA i RULES różnią się dla testów i wdrażalności (15/15 vs 20/10). Przygotowujemy się na wariant z RULES — 20% za testy.
- **Platforma zgłoszeń.** RULES: HackTribe.
- **Stack.** Propozycja: Python (FastAPI + pytest) + Ollama. Niezatwierdzone.

## Zasady hackathonu, o których pamiętamy

- Liczy się tylko praca wykonana w oknie konkursowym; kod sprzed hackathonu wyraźnie oddzielamy i ujawniamy.
- Musimy umieć wyjaśnić każdą część rozwiązania, także kod wygenerowany przez AI.
- Ujawniamy istotne użycie narzędzi AI, zewnętrznych modeli, API, zbiorów danych i bibliotek; cytujemy wykorzystane repozytoria; przestrzegamy licencji.
- Zgłoszenie: tytuł, nazwa zespołu, lista członków, opis, prezentacja PDF do 10 slajdów; opcjonalnie repozytorium, demo, zrzuty ekranu.
- Nagroda wymaga min. 50% punktów.

Pełne wspólne zasady: [`knowledge-base/README.md` §3](knowledge-base/README.md#3-common-rules).

## Plan projektu

Plan ogólny z etapami F0–F7, zasadami ograniczającymi dług techniczny, architekturą i definicją ukończenia: [`docs/PLAN.md`](docs/PLAN.md). Decyzje architektoniczne: [`docs/adr/`](docs/adr/README.md).

## Struktura repozytorium

| Ścieżka | Zawartość |
|---|---|
| [`knowledge-base/README.md`](knowledge-base/README.md) | Indeks bazy wiedzy: porównanie zadań, wspólne zasady, kryteria, sprzeczności w źródłach |
| [`knowledge-base/tasks/`](knowledge-base/tasks/) | Streszczenia 10 zadań zoptymalizowane pod AI (format HADS) |
| [`knowledge-base/rules/`](knowledge-base/rules/) | Dosłowne teksty oficjalnych dokumentów — źródło prawdy |
| [`docs/PLAN.md`](docs/PLAN.md) | Plan projektu: etapy, zasady przeciw długowi technicznemu, architektura, definicja ukończenia |
| [`docs/adr/`](docs/adr/README.md) | Rejestr decyzji architektonicznych (ADR) |
| [`AGENTS.md`](AGENTS.md) | Instrukcje dla agentów AI pracujących w repo |
| `Dockerfile`, `compose.yaml` | Szablon z `docker init` (placeholder); start: `docker compose up --build` |
