# 01 — Gatewaye, proxy i frameworki guardrails: przegląd istniejących rozwiązań

Stan na 2026-10-03. Metoda: metadane z GitHub API (licencja z pliku `LICENSE`, ostatni push, ostatni release), PyPI JSON i dokumentacja projektów. Ramę wzięliśmy ze skilla `competitive-landscape` (profil konkurenta, mapa pozycjonowania) i dostosowaliśmy ją do narzędzi OSS. `[INFERENCE]` oznacza nasz wniosek, a nie fakt zapisany w źródle.

## 1. Profil zbiorczy

| Narzędzie | Kategoria | Język | Licencja (zweryfikowana) | OpenAI-compat proxy | MCP | Aktywność | Werdykt |
|---|---|---|---|---|---|---|---|
| [LiteLLM](https://github.com/BerriAI/litellm) | gateway LLM + MCP + A2A | Python | MIT; katalog `enterprise/` na osobnej licencji ([LICENSE](https://github.com/BerriAI/litellm/blob/main/LICENSE)) | tak | tak, [MCP Gateway](https://docs.litellm.ai/docs/mcp.md) | v1.103.2, 2026-10-01 | **inspiracja**; ewentualnie tylko [cennik modeli](https://github.com/BerriAI/litellm/blob/main/model_prices_and_context_window.json) jako dane |
| [Portkey Gateway](https://github.com/Portkey-AI/gateway) | gateway LLM | TypeScript | MIT | tak | [MCP Gateway](https://portkey.ai/docs/product/mcp-gateway) w ofercie hostowanej `[INFERENCE: brak w repo OSS]` | v1.15.2, 2026-01-12; gałąź 2.0.0 (pre-release) | inspiracja |
| [Kong Gateway](https://github.com/Kong/kong) | API gateway + wtyczki AI | Lua | Apache-2.0 | tak (`ai-proxy`) | tylko Enterprise ([ai-mcp-proxy](https://developer.konghq.com/plugins/ai-mcp-proxy/)) | OSS 3.9.3, 2026-06-17 | skip |
| [Agent Router (dawniej Envoy AI Gateway)](https://github.com/theagentrouter/agent-router) | gateway na Envoy, K8s | Go | Apache-2.0 | tak (`aigw run`) | tak | v1.1.0, 2026-08-21 | skip |
| [agentgateway](https://github.com/agentgateway/agentgateway) | proxy LLM + MCP + A2A (Linux Foundation) | Rust | Apache-2.0 | tak | tak, wszystkie transporty | v1.6.0, 2026-10-02 | **inspiracja** (najbliższy architektonicznie) |
| [Bifrost](https://github.com/maximhq/bifrost) | gateway LLM | Go | Apache-2.0 | tak | klient MCP; „MCP gateway” i guardrails wg README to Enterprise | tag 2026-10-02 | skip |
| [Higress](https://github.com/higress-group/higress) | API gateway Istio/Envoy + Wasm | Go | Apache-2.0 | tak (`ai-proxy`) | hosting serwerów MCP | v2.2.4, 2026-08-13 | skip |
| [Apache APISIX](https://github.com/apache/apisix) | API gateway + wtyczki AI | Lua | Apache-2.0 | tak (`ai-proxy`) | — | 3.19.0, 2026-09-28 | skip |
| [Plano (dawniej archgw)](https://github.com/katanemo/plano) | proxy agentowe na Envoy | Rust | Apache-2.0 | tak | — `[niezweryfikowane]` | 0.4.37, 2026-09-28 | skip |
| [Helicone AI Gateway](https://github.com/Helicone/ai-gateway) | gateway LLM | Rust | **GPL-3.0** | tak | — | ostatni push 2025-11-21 | skip (licencja, aktywność) |
| [TensorZero](https://github.com/tensorzero/tensorzero) | LLMOps + gateway | Rust | Apache-2.0 | tak | — | **repo zarchiwizowane** (flaga GitHub, przyczyna niepodana) | skip |
| [NeMo Guardrails](https://github.com/NVIDIA-NeMo/Guardrails) | framework guardrails | Python | Apache-2.0 ([LICENSE.md](https://github.com/NVIDIA-NeMo/Guardrails/blob/develop/LICENSE.md)) | serwer z `/v1/chat/completions` | — | v0.24.1, 2026-09-16 | inspiracja (taksonomia rails) |
| [Guardrails AI](https://github.com/guardrails-ai/guardrails) | framework walidatorów | Python | Apache-2.0 | serwer Flask, klient OpenAI SDK | — | v0.11.0, 2026-08-14 | inspiracja |
| [LLM Guard](https://github.com/protectai/llm-guard) | biblioteka skanerów | Python | MIT | — (osobne API) | — | **zarchiwizowane**; README: „no longer under active development” | inspiracja (lista skanerów) |
| [LlamaFirewall](https://github.com/meta-llama/PurpleLlama/tree/main/LlamaFirewall) | firewall agentów | Python | kod MIT ([LICENSE](https://github.com/meta-llama/PurpleLlama/blob/main/LlamaFirewall/LICENSE)); licencja modeli `[niezweryfikowane]` | — | — | PyPI 1.0.3, 2025-05-29; commity 2026-08 | do oceny w raporcie o detektorach |
| [Invariant Guardrails](https://github.com/invariantlabs-ai/invariant) + [Gateway](https://github.com/invariantlabs-ai/invariant-gateway) | język reguł + proxy LLM/MCP | Python | Apache-2.0 | tak (zmiana base URL) | tak | push 2026-01 / 2025-11 | inspiracja (język reguł) |
| [Snyk Agent Scan (dawniej mcp-scan)](https://github.com/snyk/agent-scan) | skaner konfiguracji MCP i skills | Python | Apache-2.0 | — | skanuje | v0.6.8, 2026-09-29; wymaga `SNYK_TOKEN` | inspiracja (klasy ataków MCP) |
| [IBM ContextForge](https://github.com/IBM/mcp-context-forge) | gateway MCP + A2A + REST | Python | Apache-2.0 | routing agentów zgodny z OpenAI | tak | v1.0.11, 2026-09-28 | inspiracja (wtyczki MCP) |
| [Docker MCP Gateway](https://github.com/docker/mcp-gateway) | gateway MCP, kontenery | Go | MIT | — | tak | push 2026-09-23 | skip (inny problem: izolacja) |
| [Microsoft MCP Gateway](https://github.com/microsoft/mcp-gateway) | reverse proxy MCP na K8s | C# | MIT | — | tak (MCP `2026-07-28`) | push 2026-10-02 | skip |
| [Lasso MCP Gateway](https://github.com/lasso-security/mcp-gateway) | gateway MCP z wtyczkami | Python | MIT | — | tak | v1.2.0, 2026-01-21 | inspiracja |
| [MetaMCP](https://github.com/metatool-ai/metamcp) | agregator MCP | TypeScript | MIT | — | tak | v2.4.22, 2025-12-19 | skip |

## 2. Profile kluczowych narzędzi

### LiteLLM (punkt odniesienia nr 1)
- **Polityka:** `config.yaml` czytany przy starcie. Zmiany „day-2” są możliwe przez Admin UI i bazę danych ([Model Management](https://docs.litellm.ai/docs/proxy/model_management.md)); klucze, UI i rozliczanie kosztów wymagają Postgresa ([llms.txt](https://docs.litellm.ai/llms.txt)).
- **Budżety:** klucze wirtualne, budżety, limity RPM/TPM, budżety iteracji agentów ([docs](https://docs.litellm.ai/docs/a2a_iteration_budgets.md)). Budżety per model na klucz i budżety per tag są w Enterprise ([Enterprise](https://docs.litellm.ai/docs/enterprise.md)).
- **Guardrails:** klasa `CustomGuardrail` z metodą `apply_guardrail` i trybami `pre_call`, `during_call` (równolegle z wywołaniem modelu, tylko blokuje) i `post_call` ([docs](https://docs.litellm.ai/docs/proxy/guardrails/custom_guardrail)). Przy streamingu `post_call` działa wyłącznie jako audyt; jest też `stream_holdback_chars`.
- **Paywall:** gotowe integracje `llmguard_moderations`, `lakera_prompt_injection`, `hide_secrets`, `openai_moderations` oraz guardrails per klucz/zespół wymagają licencji Enterprise. Audit logs też są w Enterprise. W OSS są custom guardrails i Presidio.
- **Ryzyko:** 17 advisories GHSA opublikowanych w 2026 r., w tym krytyczne (auth bypass, SQL injection przy weryfikacji kluczy, ucieczka z sandboksu custom guardrail) ([security](https://github.com/BerriAI/litellm/security/advisories)). Duża powierzchnia ataku jak na produkt bezpieczeństwa.

### agentgateway (najbliższy naszej wizji)
- Ruch agent→LLM, agent→MCP i agent→agent (A2A) w jednym proxy ([README](https://github.com/agentgateway/agentgateway)).
- Polityki: RBAC na silniku CEL, JWT, klucze API, rate limiting, budżety i kontrola wydatków, OTel (metryki, logi, trace).
- Konfiguracja lokalna w YAML/JSON z **obserwacją pliku i dynamicznym przeładowaniem** ([architecture/configuration.md](https://github.com/agentgateway/agentgateway/blob/main/architecture/configuration.md)); metryka `config_synchronized` mówi, czy ostatni reload się udał.
- Guardrails: regex, OpenAI moderation, Bedrock Guardrails, Model Armor, webhooki. Nie ma lokalnej warstwy semantycznej ani sygnatur ataków.
- Rust oznacza, że rozszerzenia w Pythonie piszemy jako webhook `[INFERENCE]`, a cała logika trafia poza nasze repo.

### Portkey Gateway
- Konfiguracja routingu i guardrails przekazywana jako obiekt `config` po stronie klienta ([README](https://github.com/Portkey-AI/gateway)), czyli polityka nie jest scentralizowana w OSS `[INFERENCE]`.
- Wtyczki deterministyczne w [`plugins/default`](https://github.com/Portkey-AI/gateway/tree/main/plugins/default): `regexMatch`, `jsonSchema`, `modelWhitelist`, `containsCode`, `validUrls`, `webhook` i inne. Do tego adaptery partnerów (Aporia, Lasso, Pangea, Prisma AIRS…).
- Semantic caching i analityka są dostępne tylko w wersjach hostowanej i enterprise (przypis w README).

### Kong / APISIX / Higress / Agent Router / Bifrost (gatewaye API z dodatkami AI)
- Kong OSS ma `ai-proxy`, `ai-prompt-guard` (regex allow/deny), dekoratory i transformery. [ai-semantic-prompt-guard](https://developer.konghq.com/plugins/ai-semantic-prompt-guard/), [ai-rate-limiting-advanced](https://developer.konghq.com/plugins/ai-rate-limiting-advanced/) i `ai-mcp-proxy` mają oznaczenie „AI License Required”.
- APISIX ma `ai-prompt-guard`, `ai-rate-limiting`, `ai-lakera-guard`, `ai-aws-content-moderation` ([plugins](https://github.com/apache/apisix/tree/master/apisix/plugins)). Moderacja treści polega tu na wywołaniu chmury.
- Higress ma `ai-token-ratelimit` i `ai-quota`. `ai-security-guard` to integracja z Alibaba Cloud Content Security ([README](https://github.com/higress-group/higress/tree/main/plugins/wasm-go/extensions/ai-security-guard)).
- Agent Router: token rate limiting przez `llmRequestCosts` ([example](https://github.com/theagentrouter/agent-router/tree/main/examples/token_ratelimit)), konfiguracja przez CRD na K8s. Natywnych guardrails nie ma (w kodzie występują tylko przy Bedrock).
- Wspólny wzorzec: mocny routing, limity i obserwowalność, a bezpieczeństwo semantyczne delegowane do płatnych API chmurowych.

### Frameworki guardrails (biblioteki, nie proxy)
- **NeMo Guardrails:** rails typu input, dialog, retrieval, execution i output, język Colang. Gotowe moduły w [`nemoguardrails/library`](https://github.com/NVIDIA-NeMo/Guardrails/tree/develop/nemoguardrails/library): `jailbreak_detection`, `injection_detection`, `llama_guard`, `sensitive_data_detection`, `regex`, `tool_safety_check`… Serwer ma tryb auto-reload konfiguracji ([docs](https://github.com/NVIDIA-NeMo/Guardrails/blob/develop/docs/run-rails/using-fastapi-server/run-guardrails-server.mdx)). Nie obsługuje budżetów, MCP ani audytu w sensie zadania.
- **Guardrails AI:** walidatory z Hub, akcja `on_fail` (np. `EXCEPTION`). README z 2026-07-06 zapowiada przeniesienie walidatorów do zwykłych pakietów PyPI i wyłączenie hostowanego inferencingu (cutoff 2026-08-25). Licencje walidatorów sprawdzamy osobno, per pakiet.
- **LLM Guard:** zarchiwizowany. Lista skanerów może posłużyć jako checklista pokrycia, ale zależności nie bierzemy.
- **Invariant:** reguły w stylu Pythona (`raise "..." if: ...`) nad śladem wywołań narzędzi, wdrażane jako proxy MCP lub LLM ([README](https://github.com/invariantlabs-ai/invariant)). Dobry wzorzec dla kontroli sekwencji tool calls. Repo `invariantlabs-ai/mcp-scan` przekierowuje dziś do `snyk/agent-scan`.

### Gatewaye MCP
- **ContextForge:** ponad 40 wtyczek, m.in. `code_safety_linter`, `deny_filter`, `regex_filter`, `file_type_allowlist`, `harmful_content_detector`, `virus_total_checker`, `unified_pdp` ([plugins](https://github.com/IBM/mcp-context-forge/tree/main/plugins)). Ma Admin UI, OTel i rate limiting. To najbogatszy wzorzec kontroli agent→MCP.
- **Lasso:** wtyczki `basic` (maskowanie tokenów), `presidio` i `lasso` (płatne API), a także skaner reputacji serwerów MCP przed ich załadowaniem ([README](https://github.com/lasso-security/mcp-gateway)).

### Komercyjne benchmarki (nie do użycia: płatne lub chmurowe)
| Usługa | Co warto skopiować koncepcyjnie | Źródło |
|---|---|---|
| Lakera Guard (dziś pod marką Check Point AI Security) | jedno API klasyfikacji promptu i odpowiedzi | [docs](https://docs.lakera.ai/docs/api/guard) |
| Azure AI Content Safety, Prompt Shields | podział na *user prompt attacks* i *document attacks* (pośrednia injekcja) | [docs](https://learn.microsoft.com/en-us/azure/ai-services/content-safety/concepts/jailbreak-detection) |
| AWS Bedrock Guardrails | typy polityk: content filters, denied topics, word filters, sensitive information filters (block/mask), contextual grounding, Automated Reasoning, prompt attack; [ApplyGuardrail](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-use-independent-api.html) działa niezależnie od modelu | [docs](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails.html) |
| Cloudflare AI Gateway, Guardrails | akcje *flag* (tylko log) i *block* na wejściu i wyjściu | [docs](https://developers.cloudflare.com/ai-gateway/features/guardrails/) |
| Google Model Armor | filtr promptów i odpowiedzi jako usługa | [docs](https://cloud.google.com/security-command-center/docs/model-armor-overview) |

Standard odniesienia (przekazany przez ThreatCatalog): [OWASP Agent Control Standard](https://github.com/GenAI-Security-Project/agent-control-standard), Apache-2.0, deklaratywne hooki runtime dla agentów. Warto zmapować na niego nasze etapy pipeline'u.

## 3. Mapa pozycjonowania

Osie wybraliśmy wprost z oceny:
- **X: zakres ruchu.** Zadanie wymaga app→agent, agent→model, agent→MCP i agent↔agent.
- **Y: głębokość kontroli bezpieczeństwa dostępna lokalnie i bez licencji.** Kryterium „Robustness & guardrails” ma 30%. Liczy się tylko to, co działa offline w OSS, bo nie mamy płatnych API.

```
Głębokość kontroli (OSS, lokalnie)
 wysoka │ NeMo Guardrails   LlamaFirewall           ● NASZ CEL
        │ Guardrails AI     Invariant (LLM+MCP)       (polityka + determ. + semantyka
        │ (LLM Guard†)                                  lokalna + sygnatury + budżety)
średnia │                   ContextForge (MCP/A2A)
        │ Portkey OSS       Lasso (MCP)   LiteLLM OSS   agentgateway
  niska │ Kong OSS  APISIX  Higress       Bifrost OSS   Agent Router
        │                   Docker/MS MCP GW
        └────────────────────────────────────────────────────────────
          tylko model        model + MCP         model + MCP + A2A
                                                        Zakres ruchu
† zarchiwizowany. Komercyjne API (Bedrock, Azure, Lakera) leżą wysoko na Y, ale poza osią X: to detektory, a nie proxy.
```

## 4. Luka, którą wypełnia nasz projekt

Pozycjonowanie (format ze skilla):
> Dla zespołów platformowych, które wpuszczają agentów do wrażliwych systemów, AI Control Layer to proxy działające w pełni lokalnie. Jeden walidowany plik polityki steruje w nim jednocześnie decyzją ALLOW/REDACT/BLOCK, budżetami i sygnaturami ataków. W odróżnieniu od LiteLLM i agentgateway warstwa semantyczna działa lokalnie, a bezpieczeństwo nie zależy od płatnej licencji ani chmury.

Białe plamy potwierdzone przeglądem:
1. **Spójne progi block vs redact w jednej polityce** z hot reloadem i zachowaniem ostatniej poprawnej wersji. Gatewaye mają osobno wtyczki, limity i routing, a w LiteLLM guardrails per klucz są w Enterprise.
2. **Lokalna warstwa semantyczna.** Kong, APISIX, Higress i agentgateway delegują ją do API chmurowych. U nas działa na Ollamie i ma jawne `on_error`.
3. **Znane ataki z zewnętrznego feedu sygnatur** (wykonanie kodu w argumentach narzędzi, pickle, supply chain modeli). Żaden z gatewayów nie ma tego natywnie. Najbliżej są `code_safety_linter` i `virus_total_checker` w ContextForge (MCP) oraz skaner reputacji w Lasso.
4. **Budżet liczony także dla modeli lokalnych** (compute), a nie tylko z cennika dostawcy `[INFERENCE: w przejrzanych docs nie znaleźliśmy kosztu lokalnego compute]`.
5. **Self-test na żywej instancji**, czyli polecenie `selftest --target`, jako część produktu. Żadne z przejrzanych README tego nie oferuje `[INFERENCE]`.
6. **Raport bezpieczeństwa per kontrola** i eksport audytu w OSS. W LiteLLM audit logs są w Enterprise.

## 5. Build vs reuse: warstwa proxy

**Rekomendacja: budujemy własne, cienkie proxy na FastAPI** (zgodne z ADR-0001/0002). Cudzych gatewayów nie owijamy.

| Opcja | Za | Przeciw |
|---|---|---|
| **Własny FastAPI** (OpenAI-compat `/v1/chat/completions`, później adapter MCP) | jury ocenia *naszą* architekturę (20%); pełna kontrola pipeline'u i kolejności tanie→drogie; telemetria per etap; brak Postgresa; mała powierzchnia ataku | ręczna obsługa zgodności OpenAI (streaming, tools); ryzyko opisane w PLAN §9 |
| Owinięcie LiteLLM (nasze kontrole jako `CustomGuardrail`) | darmowy routing do ponad 100 dostawców, klucze i budżety | nasz kod staje się wtyczką w cudzej architekturze; hot reload polityki wymaga DB; audyt i guardrails per klucz w Enterprise; 17 GHSA w 2026; trudno pokazać heksagonalny rdzeń |
| agentgateway + nasz webhook | MCP/A2A/CEL od ręki, wydajność Rusta | logika w dwóch procesach i językach; webhook dokłada opóźnienie; jury widzi głównie cudzy produkt |

Co bierzemy bez wiązania architektury:
- **Dane:** `model_prices_and_context_window.json` z LiteLLM (MIT) jako źródło cen zewnętrznych modeli do budżetów. Plik i licencję wpisujemy do `docs/DEPENDENCIES.md`.
- **Wzorce:**
  - tryby `pre_call`/`during_call`/`post_call` i holdback przy streamingu (LiteLLM);
  - reload z obserwacji pliku plus metryka powodzenia reloadu (agentgateway);
  - typy polityk i akcje block/mask (Bedrock Guardrails);
  - flag vs block (Cloudflare);
  - user vs document attacks (Azure);
  - reguły nad sekwencją tool calls (Invariant);
  - katalog wtyczek MCP (ContextForge).
- **Argument skalowalności na pitch:** proxy mówi API OpenAI, więc można je postawić za LiteLLM, agentgateway czy Kongiem jako warstwę polityki. Nie konkurujemy z routingiem, uzupełniamy go `[INFERENCE]`.
