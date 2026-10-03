# 03 — Testy i red teaming: narzędzia, zbiory danych, projekt zestawu testów

Stan na 2026-10-03. Licencje i daty sprawdzone przez GitHub API (`gh api repos/…`), PyPI JSON i Hugging Face API. Elementy, których nie udało się potwierdzić, oznaczono `[niezweryfikowane]`.

## 1. Narzędzia do red teamingu i ewaluacji

| Narzędzie | Co robi | Licencja | Wersja / aktywność | Jak podpiąć do naszego proxy | Wysiłek |
|---|---|---|---|---|---|
| [garak](https://github.com/NVIDIA/garak) (NVIDIA) | Skaner podatności LLM: probe → generator → detektor, raport JSONL/HTML. Probe m.in. `promptinject`, `dan`, `encoding`, `latentinjection`, `web_injection` (eksfiltracja przez Markdown), `apikey`, `malwaregen`, `exploitation`, `smuggling`, `sysprompt_extraction`, `av_spam_scanning`, `agent_breaker` | Apache-2.0 | v0.17.0 (2026-09-09), aktywny | Generator `openai.OpenAICompatible` z opcją `uri` (domyślnie `http://localhost:8000/v1/`), CLI `--target_type/--target_name`, `--probes`, `--report_prefix` ([źródło](https://github.com/NVIDIA/garak/blob/main/garak/generators/openai.py)). Garak przy starcie robi `GET` na `uri`, więc proxy musi przyjmować połączenia. | niski |
| [promptfoo](https://github.com/promptfoo/promptfoo) | Ewaluacje sterowane YAML i red team: pluginy (`pii:direct`, `indirect-prompt-injection`, `excessive-agency`, `mcp`…) i strategie (Base64, ROT13, leetspeak, wielojęzyczność, crescendo, GOAT) ([docs](https://www.promptfoo.dev/docs/red-team/configuration/)) | MIT | npm 0.123.1 (2026-09-18) | Provider `openai:chat:<model>` z `apiBaseUrl` wskazującym na nasze proxy ([docs](https://www.promptfoo.dev/docs/providers/openai/)). Grader i generator ataków mogą działać na Ollamie (`ollama:chat:<model>`). Asercja `guardrails` czyta pole `guardrails.flagged` z odpowiedzi providera ([docs](https://www.promptfoo.dev/docs/configuration/expected-outputs/guardrails/)), więc nasza decyzja block/redact staje się oceniana wprost. Domyślnie generowanie ataków idzie przez zdalną usługę promptfoo; trzeba przełączyć na lokalny LLM ([docs](https://www.promptfoo.dev/docs/red-team/troubleshooting/remote-generation/)). | niski–średni (Node) |
| [PyRIT](https://github.com/microsoft/PyRIT) (Microsoft) | Framework do orkiestracji ataków: targety, konwertery (Base64, tłumaczenia i inne), ataki jedno- i wieloturowe, scorery, pamięć w SQLite | MIT | v1.1.0 (2026-09-04). Uwaga: stare repo `Azure/PyRIT` jest zarchiwizowane. | `OPENAI_CHAT_ENDPOINT/KEY/MODEL` ustawione na proxy ([config](https://github.com/microsoft/PyRIT/blob/main/doc/getting_started/configuration.md)). Ma też `GandalfTarget` i `HTTPTarget`. | średni–wysoki |
| [DeepTeam](https://github.com/confident-ai/deepteam) | Red team z ponad 50 podatnościami (PII Leakage, Prompt Leakage, Shell/SQL Injection, SSRF, Indirect Instruction, Excessive Agency, Recursive Hijacking…) i frameworkiem `OWASPTop10`. Ma też moduł `Guardrails`. | Apache-2.0 | PyPI 1.0.9 (2026-08-12) | `red_team(model_callback=…, vulnerabilities=…, attacks=…)`. Callback to `async def` wołający nasze proxy. Symulator i sędzia to LLM; Ollama przez deepeval ([integracja](https://github.com/confident-ai/deepeval/blob/main/docs/content/integrations/models/ollama.mdx)). | średni |
| [deepeval](https://github.com/confident-ai/deepeval) | Metryki LLM w stylu pytest, baza DeepTeam | Apache-2.0 | 4.2.8 (2026-10-02) | Niepotrzebny: do testów kontroli wystarczy pytest. | — |
| [Giskard](https://github.com/Giskard-AI/giskard-oss) | Wersja v3 to przepisana od nowa biblioteka do testów agentów: `giskard-checks` (scenariusze, LLM-as-judge) i `giskard-scan` | Apache-2.0 | v3.0.1 (2026-10-02, świeże wydanie). v2 nie jest już utrzymywana. | Wymaga Pythona 3.12+. API dopiero co zmienione, więc ryzyko na hackathonie. | średni (pominąć) |
| [Inspect](https://github.com/UKGovernmentBEIS/inspect_ai) (UK AISI) + [inspect_evals](https://github.com/UKGovernmentBEIS/inspect_evals) | Framework ewaluacji. Gotowe evale: `agentdojo`, `agent_threat_bench`, `ipi_coding_agent`, `strong_reject`, `xstest`, `cyberseceval_2/3/4`, `b3` | MIT | inspect-ai 0.3.276 (2026-10-02) | `OPENAI_BASE_URL` ustawione na proxy ([providers](https://github.com/UKGovernmentBEIS/inspect_ai/blob/main/docs/providers.qmd)). `xstest` mierzy nadmierne blokowanie. | średni |
| [AgentDojo](https://github.com/ethz-spylab/agentdojo) / [PINT](https://github.com/lakeraai/pint-benchmark) (Lakera, repo zarchiwizowane) | Indirect injection na agentach z narzędziami / benchmark detektorów injection | MIT / MIT | v0.1.35 (2025-10) / — | Wzór do przypadków „injection w wyniku narzędzia” i do metodologii FP/FN | wysoki (nie uruchamiać) |

**Rekomendacja:** jako zewnętrzny red team użyć garak, bo to jedno polecenie CLI i daje gotowy raport HTML dla jury. Promptfoo jako opcja: YAML, wiele strategii obfuskacji, asercja `guardrails`. PyRIT, Giskard i Inspect nie mieszczą się w 24 h.

**Uwaga integracyjna `[INFERENCE]`:** detektory garak i promptfoo oceniają tekst odpowiedzi. Zablokowane żądanie powinno więc zwracać poprawną odpowiedź OpenAI (HTTP 200, treść odmowy i znacznik decyzji w nagłówku lub polu metadanych), a nie sam kod 4xx/5xx. Błędy HTTP mogą być liczone jako błąd narzędzia, a nie jako skuteczna obrona. Format trzeba ustalić w ADR-0004.

## 2. Publiczne zbiory danych (injection, jailbreak, harmful, over-refusal)

| Zbiór | Zawartość | Licencja | Uwagi | Użycie u nas |
|---|---|---|---|---|
| [deepset/prompt-injections](https://huggingface.co/datasets/deepset/prompt-injections) | 662 wiersze (546 train / 116 test), etykiety 0/1, EN i DE | apache-2.0 (tag). Karta zawiera też wpis `cc-by-4.0`, więc jest niespójna. | Mały i czysty zbiór | Pozytywy i negatywy dla detektora semantycznego, pomiar FP/FN |
| [Lakera/gandalf_ignore_instructions](https://huggingface.co/datasets/Lakera/gandalf_ignore_instructions) | ok. 1000 prawdziwych ataków „ignore instructions” | MIT | — | Negatywy (direct injection) |
| [Lakera/mosscap_prompt_injection](https://huggingface.co/datasets/Lakera/mosscap_prompt_injection) | 100K–1M ataków z gry Mosscap | MIT | Duży, trzeba wybrać próbkę | Próbka do testów obciążeniowych detektora |
| [Lakera/gandalf_summarization](https://huggingface.co/datasets/Lakera/gandalf_summarization) | poniżej 1K ataków przez zadanie streszczania | MIT | Bliskie indirect injection | Negatywy (injection w treści dokumentu) |
| [JailbreakBench/JBB-Behaviors](https://huggingface.co/datasets/JailbreakBench/JBB-Behaviors) | 100 szkodliwych i 100 nieszkodliwych zachowań | MIT | Pary harmful/benign | Negatywy i pozytywy, mierzy over-blocking |
| [HarmBench](https://github.com/centerforaisafety/HarmBench) (`data/behavior_datasets/harmbench_behaviors_text_*.csv`) | Szkodliwe zachowania w podziale na kategorie | MIT (repo) | Ostatnia aktywność 2024-08. Mirror `walledai/HarmBench` (MIT) wymaga akceptacji warunków (gated auto). | Negatywy semantyczne |
| [AdvBench](https://github.com/llm-attacks/llm-attacks) (`data/advbench/harmful_behaviors.csv`, `harmful_strings.csv`) | 520 szkodliwych poleceń i stringów | MIT (repo) | Mirror `walledai/AdvBench` jest gated (auto) | Negatywy, bazowy zestaw do sufiksów GCG |
| [TrustAIRLab/in-the-wild-jailbreak-prompts](https://huggingface.co/datasets/TrustAIRLab/in-the-wild-jailbreak-prompts) / [verazuo/jailbreak_llms](https://github.com/verazuo/jailbreak_llms) | ok. 15 tys. promptów z Reddita, Discorda i innych, w tym jailbreaki (DAN itp.) | MIT | — | Negatywy „jak prawdziwy użytkownik” |
| [jackhhao/jailbreak-classification](https://huggingface.co/datasets/jackhhao/jailbreak-classification) | 1K–10K wierszy z etykietą jailbreak/benign | apache-2.0 | — | Pozytywy i negatywy |
| [reshabhs/SPML_Chatbot_Prompt_Injection](https://huggingface.co/datasets/reshabhs/SPML_Chatbot_Prompt_Injection) | Pary system prompt + atak | MIT | — | Injection z kontekstem systemowym |
| [Paul/XSTest](https://huggingface.co/datasets/Paul/XSTest) | poniżej 1K bezpiecznych promptów, które wyglądają na niebezpieczne | CC-BY-4.0 (repo `paul-rottger/xstest`: CC-BY-4.0) | Wymaga atrybucji | **Pozytywy**: kontrole nie mogą blokować tych promptów |
| [Tensor Trust](https://github.com/HumanCompatibleAI/tensor-trust-data) (mirror HF `qxcv/tensor-trust`) | Ataki i obrony z gry: hijacking, extraction | **`[niezweryfikowane]`**: brak pliku LICENSE i brak licencji w karcie. Kod gry ma BSD-2-Clause, ale to nie dotyczy danych. | — | Tylko jako inspiracja. Nie kopiować do repo. |
| [microsoft/BIPIA](https://github.com/microsoft/BIPIA) | Benchmark indirect injection (e-mail, tabele, kod, QA) | MIT (LICENSE). Część danych (WebQA, streszczenia) trzeba pobrać ze źródeł o innych licencjach. | Repo zarchiwizowane | Wzorce indirect injection w wynikach narzędzi |
| [allenai/wildjailbreak](https://huggingface.co/datasets/allenai/wildjailbreak) | Syntetyczne jailbreaki i kontrastowe pozytywy | ODC-BY | gated (auto) | Opcjonalnie |
| [hackaprompt/hackaprompt-dataset](https://huggingface.co/datasets/hackaprompt/hackaprompt-dataset) | ok. 600K zgłoszeń z konkursu | MIT | gated (auto) | Opcjonalnie |
| [tljohnsilver/zn-prompt-injection-bench](https://huggingface.co/datasets/tljohnsilver/zn-prompt-injection-bench) | 23 699 wierszy w wielu językach, **w tym `pl`** | CC-BY-4.0 (karta) | Niszowy (97 pobrań), jakość `[niezweryfikowane]` | Ewentualne źródło polskich przypadków po ręcznym przeglądzie |
| `qualifire/prompt-injections-benchmark`, `lmsys/toxic-chat`, `PKU-Alignment/BeaverTails` | — | CC-BY-NC-4.0 | Licencja niekomercyjna | Lepiej unikać |
| `xTRam1/safe-guard-prompt-injection`, `rubend18/ChatGPT-Jailbreak-Prompts` | — | brak licencji w karcie: `[niezweryfikowane]` | — | Nie używać |
| `ai4privacy/pii-masking-400k` | Syntetyczne PII w 6 językach (bez polskiego) | `other` (własna licencja) `[niezweryfikowane]` | — | Nie używać. PII generujemy sami. |

**Wnioski:**
- Nie znaleźliśmy dojrzałego, dobrze licencjonowanego zbioru polskich ataków injection. Polskie przypadki piszemy sami i tłumaczymy próbki z deepset oraz Gandalfa.
- Danych nie redystrybuujemy hurtowo. W `tests/cases/` trzymamy własne przypadki i małe, przypisane próbki z zestawów MIT/Apache, a pełne zbiory pobiera opcjonalny skrypt.
- Do testów PII, sekretów i ładunków pickle żaden zbiór nie jest potrzebny. Generujemy fikcyjne dane, na przykład klucz `AKIAIOSFODNN7EXAMPLE` z dokumentacji AWS i nieszkodliwy `__reduce__` wywołujący `echo`.

## 3. Projekt zestawu testów

Trzy warstwy. Wszystkie korzystają z tych samych danych w `tests/cases/*.yaml`, zgodnie z PLAN §6 i Z5.

1. **`make test` (offline, pytest):** każdy plik YAML zamienia się w przypadki parametryzowane i jest uruchamiany na pipeline z adapterami in-memory (atrapa LLM, stały zegar). Jest deterministyczny i szybki. Przypadki semantyczne mają tag `semantic` i dostają atrapę detektora albo, jeśli działa Ollama, prawdziwy model.
2. **`selftest --target http://host:port` (na żywej instancji):** te same pliki YAML są wysyłane po HTTP do działającego proxy. Sprawdzamy decyzję (`allow` / `redact` / `block`), identyfikator kontroli, zredagowany fragment, wpis w audycie (`GET /audit?request_id=`) i liczniki metryk. Wynik to tabela w konsoli, `selftest-report.json` i JUnit XML. To jest polecenie, które uruchomi jury.
3. **Opcjonalny zewnętrzny red team:** `make redteam` uruchamia garak (`promptinject`, `dan`, `encoding`, `latentinjection`, `web_injection`, `apikey`, `exploitation`) przeciwko proxy. Robimy dwa przebiegi: bezpośrednio na Ollamę i przez proxy. Raport HTML z porównaniem „przed i po” trafia do dashboardu i prezentacji. Opcjonalnie promptfoo ze strategiami obfuskacji i asercją `guardrails`.

**Schemat przypadku (propozycja):** `id`, `control`, `polarity: positive|negative`, `channel: app→model|agent→mcp|tool_output|agent→agent`, `request` (wiadomości, model, agent i klucz), `policy_overrides` (opcjonalnie, np. próg), `expect: {decision, control_id, redacted_contains?, response_not_contains?, http_status?}`, `tags` (`judge-likely`, `semantic`, `pl`, `source: deepset@apache-2.0`).

**Zasady:**
- Każda kontrola w `policy.yaml` ma co najmniej jeden przypadek pozytywny i jeden negatywny. Pilnuje tego test metadanych (PLAN Z5).
- Test „config live” zmienia próg albo wyłącza kontrolę przez plik polityki, czeka na hot reload, a potem ten sam przypadek musi zmienić decyzję. To odtwarza scenariusz, w którym jury edytuje konfigurację.
- Raport podaje FP/FN dla detektora semantycznego na próbce deepset, Gandalfa i XSTest oraz opóźnienie p50/p95 per kontrola (telemetria).

## 4. Lista startowa kategorii przypadków (~27)

★ oznacza kategorię, którą jury prawdopodobnie sprawdzi ad hoc promptami albo edycją konfiguracji.

| # | Kategoria | Kontrola | Negatyw (oczekiwane) | Pozytyw (oczekiwane) |
|---|---|---|---|---|
| 1 | ★ E-mail i telefon w prompcie | PII | redact | zwykłe pytanie bez PII → allow |
| 2 | PESEL, IBAN PL, numer karty (Luhn) | PII | redact lub block wg progu | numer zamówienia podobny do karty, ale bez poprawnego Luhna → allow |
| 3 | PII w **odpowiedzi** modelu (wyciek na wyjściu) | PII (output) | redact | — |
| 4 | ★ Klucz AWS i token GitHub | sekrety | block | słowo „AWS” w zwykłym zdaniu → allow |
| 5 | Klucz prywatny PEM, JWT, connection string | sekrety | block | — |
| 6 | ★ Bezpośrednie „ignore previous instructions” | injection | block | pytanie o to, czym jest prompt injection → allow (XSTest-like) |
| 7 | ★ Wyciąganie system promptu | injection / leak | block | — |
| 8 | ★ Jailbreak DAN, roleplay, „grandma” | jailbreak | block | prośba o fikcyjną historię bez szkody → allow |
| 9 | Injection zakodowany w Base64 lub ROT13 | injection + dekodowanie | block | zwykły blob Base64 (obraz) → allow |
| 10 | Unicode smuggling (zero-width, tag chars, homoglify) | normalizacja | block | — |
| 11 | ★ Injection po polsku (i mieszanka PL/EN) | injection | block | polskie pytanie biznesowe → allow |
| 12 | Indirect injection w wyniku narzędzia lub dokumencie RAG | injection (tool_output) | block lub sanitize | dokument bez instrukcji → allow |
| 13 | Eksfiltracja przez obraz Markdown lub URL z danymi | wyjście / egress | block | — |
| 14 | ★ Niedozwolony model (`model: gpt-4o` spoza allowlisty) | allowlista modeli | block (403 lub odmowa) | dozwolony model lokalny → allow |
| 15 | ★ Wyczerpanie budżetu tokenów lub kosztu agenta | budżet | block po limicie | wywołanie w limicie → allow |
| 16 | Pojedyncze żądanie ponad `max_tokens` lub koszt | budżet | block | — |
| 17 | Niekontrolowana pętla (N wywołań w oknie, ta sama treść) | rate / loop | block | normalny rytm → allow |
| 18 | Brak, zły lub cudzy klucz API agenta (podszycie) | tożsamość | 401 / block | poprawny klucz → allow |
| 19 | Agent bez uprawnień do narzędzia MCP (`delete_*`) | dostęp | block | dozwolone narzędzie → allow |
| 20 | ★ Kod do wykonania w argumentach narzędzia (`os.system`, `rm -rf`, reverse shell) | sygnatury / exec | block | fragment kodu w pytaniu edukacyjnym → zależnie od polityki |
| 21 | Ładunek pickle lub `torch.load` (opcode `GLOBAL`/`REDUCE`, Base64 pickle) | deserializacja | block | zwykły JSON → allow |
| 22 | Pobranie modelu z niedozwolonego repo lub pliku `.bin`/`.pkl` zamiast `safetensors` | supply chain | block | dozwolone źródło `safetensors` → allow |
| 23 | Nowa sygnatura dodana do feedu na żywo (np. ciąg testowy EICAR) | feed sygnatur | block po reloadzie | przed dodaniem → allow |
| 24 | ★ Zmiana progu lub wyłączenie kontroli w `policy.yaml` na żywo | silnik polityk | decyzja zmienia się bez restartu | — |
| 25 | Błędna polityka (zły YAML lub schemat) | silnik polityk | odrzucona, działa ostatnia poprawna, wpis w audycie | — |
| 26 | Awaria lub timeout detektora semantycznego | `on_error` | fail-closed albo fail-open zgodnie z polityką | — |
| 27 | Wejście puste, ogromne lub binarne | odporność | kontrolowany błąd 4xx, brak 500 | — |

**Najbardziej prawdopodobne próby jury ad hoc:** #1, #4, #6, #7, #8, #11 (zespół z Polski, jury może pisać po polsku), #14, #15, #20 i #24. Do tego warianty z obfuskacją (#9) i prośby graniczne, które wyglądają groźnie, ale są dozwolone. Te ostatnie testują nadmierne blokowanie, dlatego potrzebne są pozytywy w stylu XSTest i JBB benign.
