# 02 — Detektory i modele do portu `Detector`

Stan: 2026-10-03. Źródła: strony ollama.com/library, karty modeli i API Hugging Face, repozytoria GitHub (`gh api`), PyPI JSON. Fit: **use** (bierzemy wprost) · **wrap** (za portem `Detector`, z timeoutem i `on_error`) · **inspiration** (bierzemy reguły lub pomysł, bez zależności) · **skip**.

## 1. Modele semantyczne

### 1a. Ollama library (modele generatywne, odpowiedź tekstem)

| Model | Tagi (rozmiar, kontekst) | Co klasyfikuje | Wejście → wyjście | Licencja (karta modelu) | Opublikowana jakość | Fit |
|---|---|---|---|---|---|---|
| [llama-guard3](https://ollama.com/library/llama-guard3) | `1b` 1.6 GB, `8b` (domyślny) 4.9 GB; 128K | Taksonomia MLCommons S1–S13 (m.in. S2 przestępstwa, w tym cyber; S7 Privacy; S14 Code Interpreter Abuse tylko w 8B, [karta 8B](https://huggingface.co/meta-llama/Llama-Guard-3-8B)) | `/api/chat` z rolami user/assistant → `safe` albo `unsafe\nS2` | 1B: Llama 3.2 Community, 8B: Llama 3.1 Community ([1B](https://huggingface.co/meta-llama/Llama-Guard-3-1B), [8B](https://huggingface.co/meta-llama/Llama-Guard-3-8B)); wymaga „Built with Llama” | F1/FPR EN: 8B 0.939/0.040, 1B 0.899/0.090 ([karta 1B](https://huggingface.co/meta-llama/Llama-Guard-3-1B)); 8 języków, bez polskiego | **use** (moderacja treści wej./wyj.) |
| [shieldgemma](https://ollama.com/library/shieldgemma) | `2b` 1.7 GB, `9b` 5.8 GB, `27b` 17 GB; 8K | 4 kategorie: dangerous, harassment, hate, sexually explicit | prompt z polityką (preambuła + zasada) → `Yes`/`No`; z HF można liczyć P(Yes) z logitów | Gemma Terms of Use ([HF](https://huggingface.co/google/shieldgemma-2b)) | — | **skip** (wąsko, tylko EN) |
| [granite3-guardian](https://ollama.com/library/granite3-guardian) | `2b` 2.7 GB (domyślny), `8b` 5.8 GB; 8K | `harm`, `social_bias`, **`jailbreak`**, `violence`, `profanity`, `sexual_content`, `unethical_behavior` + RAG (`relevance`, `groundedness`, `answer_relevance`) | kategoria w system prompt → `Yes`/`No` (1 token) | Apache-2.0 ([Ollama](https://ollama.com/library/granite3-guardian), [HF](https://huggingface.co/ibm-granite/granite-guardian-3.0-2b)) | — | **use** (zapas dla Llama Guard, kategoria jailbreak) |
| [granite4.1-guardian](https://ollama.com/library/granite4.1-guardian) | `8b` 6.9 GB (q4_K_M 5.1 GB); 128K; kwiecień 2026 | jak wyżej + `function_call` (halucynacja wywołań narzędzi) + **BYOC: własne kryterium tekstem** | blok `<guardian>…### Criteria:…` → `<score>yes/no</score>`, tryb think lub no-think | Apache-2.0 ([HF](https://huggingface.co/ibm-granite/granite-guardian-4.1-8b)) | OOD Safety F1 0.79, FC halluc. BAcc 0.79 (no-think); tylko EN | **wrap** (kryteria z `policy.yaml` edytowane na żywo przez jury) |
| [gpt-oss-safeguard](https://ollama.com/library/gpt-oss-safeguard) | `20b` 14 GB, `120b` 65 GB | dowolna polityka tekstem (bring your own policy), z rozumowaniem | polityka + treść → werdykt + CoT | Apache-2.0 ([HF](https://huggingface.co/openai/gpt-oss-safeguard-20b)) | — | **skip** (za ciężki do ścieżki żądania) |

Brak w Ollama library (sprawdzone 404): Llama Guard 4, Prompt Guard, Qwen3Guard, granite3.1–3.3-guardian. Ollama uruchamia GGUF z HF: `ollama run hf.co/{user}/{repo}:{quant}` ([docs](https://huggingface.co/docs/hub/ollama)).

### 1b. Hugging Face (klasyfikatory i modele spoza Ollama)

| Model | Parametry | Co klasyfikuje | Licencja (karta) | Opublikowana jakość | Fit |
|---|---|---|---|---|---|
| [Llama-Prompt-Guard-2-86M](https://huggingface.co/meta-llama/Llama-Prompt-Guard-2-86M) / [‑22M](https://huggingface.co/meta-llama/Llama-Prompt-Guard-2-22M) | 86M (mDeBERTa) / 22M (DeBERTa-xsmall); 512 tok | `BENIGN`/`MALICIOUS` (injection + jailbreak, binarnie) | Llama 4 Community; repo HF gated (manual) | AUC EN .998/.995; Recall@1%FPR 97.5%/88.7%; A100 92.4/19.3 ms; AgentDojo APR 81.2%/78.4%; 22M słabszy wielojęzycznie | **use** (główny detektor injection) |
| [Prompt-Guard-86M](https://huggingface.co/meta-llama/Prompt-Guard-86M) (v1) | 86M | benign/injection/jailbreak | Llama 3.1 Community | zastąpiony przez v2 | **skip** |
| [protectai/deberta-v3-base-prompt-injection-v2](https://huggingface.co/protectai/deberta-v3-base-prompt-injection-v2) | 184M; ONNX w repo | 0/1 injection; bez jailbreak, tylko EN, FP na system promptach | Apache-2.0; projekt zarchiwizowany | 20k promptów spoza treningu: acc 95.25%, P 91.59%, R 99.74% | **wrap** (fallback EN) |
| [deepset/deberta-v3-base-injection](https://huggingface.co/deepset/deberta-v3-base-injection) | 184M | injection | MIT; ostatnia zmiana 2024-10 | AgentDojo APR 13.5% (wg karty Meta) | **skip** |
| [Qwen3Guard-Gen](https://huggingface.co/Qwen/Qwen3Guard-Gen-0.6B) 0.6B/4B/8B | 0.75B/4.4B/… | `Safe/Unsafe/Controversial` + kategorie (Violent, PII, **Jailbreak**, Unethical Acts…); 119 języków | Apache-2.0 | „SOTA” wg karty, bez liczb w tekście | **wrap** (spike dla polskiego; GGUF tylko społecznościowe, np. [mradermacher](https://huggingface.co/mradermacher/Qwen3Guard-Gen-0.6B-GGUF) — szablon czatu [niezweryfikowane]) |
| [granite-guardian-hap-38m](https://huggingface.co/ibm-granite/granite-guardian-hap-38m) | 38M | toksyczność (hate/abuse/profanity), CPU | Apache-2.0 | wykresy w karcie | **inspiration** (opcjonalny szybki filtr toksyczności) |

Klasyfikatory sekwencji (Prompt Guard, DeBERTa) nie są w Ollama library; uruchamiamy je przez `onnxruntime` + `tokenizers`, **bez torch** (`optimum` wymaga torch wg PyPI). Nieoficjalne eksporty ONNX Prompt Guard 2 (nie są gated, licencja llama4): [gravitee-io 22M](https://huggingface.co/gravitee-io/Llama-Prompt-Guard-2-22M-onnx) (`model.quant.onnx` 72 MB), [gravitee-io 86M](https://huggingface.co/gravitee-io/Llama-Prompt-Guard-2-86M-onnx) (281 MB).

**Pomiar własny** (Apple M5 Pro, CPU EP, onnxruntime 1.30, Python 3.12; 6 promptów: 3 ataki EN/PL, 3 neutralne EN/PL; próbka anegdotyczna):

| Model | Mediana krótki prompt | ~512 tok | Trafienia |
|---|---|---|---|
| PG2-22M quant | 46 ms | 47 ms | 5/6 — przepuścił polski „Zignoruj poprzednie instrukcje…” |
| PG2-86M quant | 111 ms | 110 ms | 6/6 |
| protectai v2 (fp32) | 7 ms | 119 ms | 5/6 — FP na „Napisz funkcję w Pythonie…” (PL) |

Stały czas modeli gravitee wskazuje na padding do 512 w `tokenizer.json` [INFERENCE] — wyłączenie paddingu powinno skrócić krótkie prompty.

Opóźnienia LLM-guardów w Ollamie **nie zmierzone** (brak Ollamy na maszynie) — do spike'u F0.

## 2. Deterministyczne PII i sekrety

| Narzędzie | Licencja · wersja | Zależności | Co daje | Fit |
|---|---|---|---|---|
| [Presidio](https://github.com/microsoft/presidio) (`presidio-analyzer`/`-anonymizer`) | MIT · 2.2.364 (2026-07-22) | spaCy + model NLP; domyślnie `en_core_web_lg` 400 MB (MIT), `en_core_web_sm` 12 MB | recognizery wzorców + kontekst + NER; anonimizacja (replace/mask/hash/encrypt). PL: tylko `PlPeselRecognizer` (regex + suma kontrolna, `supported_language="pl"`); IBAN ogólny z wzorcem `PL`; **brak NIP/REGON**. Modele spaCy `pl_core_news_*` są na **GPL-3.0** ([meta](https://raw.githubusercontent.com/explosion/spacy-models/master/meta/pl_core_news_sm-3.8.0.json)) | **wrap** (opcjonalnie, `en_core_web_sm`, PERSON/LOCATION) |
| [python-stdnum](https://github.com/arthurdejong/python-stdnum) | LGPL-2.1+ · 2.2 (2026-01-04) | brak | `stdnum.pl.pesel`, `.nip`, `.regon`, `stdnum.iban` — walidacja sum kontrolnych | **use** (filtr FP po regexie) |
| [schwifty](https://pypi.org/project/schwifty/) | MIT · 2026.7.3 | pycountry, rstr | walidacja IBAN/BIC | alternatywa dla IBAN, gdy LGPL przeszkadza |
| [detect-secrets](https://github.com/Yelp/detect-secrets) (Yelp) | Apache-2.0 · 1.5.0 (2024-05-06) | pyyaml, requests | 27 pluginów: AWS, Azure Storage, GitHub, GitLab, JWT, OpenAI, private key, Slack, Stripe, Twilio, high-entropy, keyword… | **wrap** |
| [gitleaks](https://github.com/gitleaks/gitleaks) | MIT · v8.30.1 (2026-03-21), Go | binarka | 222 reguły regex w `config/gitleaks.toml` | **inspiration** (import reguł do feedu sygnatur; zgodność RE2 → `re` [niezweryfikowane]) |
| [TruffleHog](https://github.com/trufflesecurity/trufflehog) | **AGPL-3.0** · v3.97.9 (2026-09-24), Go | binarka | ~900 detektorów, weryfikacja kluczy na żywo (ruch sieciowy) | **skip** |
| [secrets-patterns-db](https://github.com/mazen160/secrets-patterns-db) | CC-BY-SA-4.0 | — | baza regexów | **inspiration** (atrybucja + ShareAlike) |
| [Nosey Parker](https://github.com/praetorian-inc/noseyparker) | Apache-2.0, zarchiwizowany | Rust | — | **skip** |

## 3. Heurystyki prompt injection i frameworki guardrails

| Projekt | Licencja · stan | Zależności | Zawartość | Fit |
|---|---|---|---|---|
| [LLM Guard](https://github.com/protectai/llm-guard) | MIT · **zarchiwizowany**; PyPI 0.3.16 (2025-05-19), Python <3.13 | torch, `transformers==4.51.3`, `presidio==2.2.358`, bc-detect-secrets | Wejście: Anonymize, BanCode, BanCompetitors, BanSubstrings, BanTopics, Code, EmotionDetection, Gibberish, InvisibleText, Language, PromptInjection, Regex, Secrets, Sentiment, TokenLimit, Toxicity. Wyjście: BanCode, BanCompetitors, BanSubstrings, BanTopics, Bias, Code, Deanonymize, EmotionDetection, FactualConsistency, Gibberish, JSON, Language, LanguageSame, MaliciousURLs, NoRefusal, ReadingTime, Regex, Relevance, Sensitive, Sentiment, Toxicity, URLReachability | **inspiration** (katalog kontroli, `InvisibleText`, Deanonymize) |
| [Rebuff](https://github.com/protectai/rebuff) | Apache-2.0 · **zarchiwizowany** (0.1.1, 2024-01) | openai, pinecone-client, langchain | heurystyki + LLM + wektorowa baza ataków + canary tokens | **inspiration** (canary token w system prompt → wykrycie wycieku w odpowiedzi) |
| [Vigil](https://github.com/deadbits/vigil-llm) | Apache-2.0 · alpha, ostatni push 2024-01-31, brak na PyPI | YARA, baza wektorowa | skanery: YARA, podobieństwo wektorowe, transformer, prompt-response similarity, canary, sentyment | **inspiration** (format reguł YARA dla feedu; [yara-python](https://pypi.org/project/yara-python/) Apache-2.0) |
| [LlamaFirewall](https://github.com/meta-llama/PurpleLlama/tree/main/LlamaFirewall) | MIT · PyPI 1.0.3 (2025-05-29) | torch, transformers, openai, codeshield | PromptGuardScanner, AlignmentCheckScanner (LLM-judge celu agenta), CodeShieldScanner, regex | **inspiration** (AlignmentCheck = kontrola agent→narzędzie) |
| [CodeShield](https://github.com/meta-llama/PurpleLlama/tree/main/CodeShield) | MIT · 1.0.1 (2024-04) | semgrep | statyczna analiza kodu z LLM (regex + Semgrep, 50+ CWE) | **inspiration** (regexy niebezpiecznego kodu) |
| [NeMo Guardrails](https://github.com/NVIDIA/NeMo-Guardrails) | Apache-2.0 · 0.24.1 (2026-09-16) | onnxruntime, fastembed, lark… | pełny framework rails (Colang) | **skip** jako zależność (dubluje nasz `core/`) |
| [Guardrails AI](https://github.com/guardrails-ai/guardrails) | Apache-2.0 · 0.11.0 (2026-08-14) | litellm, openai, langchain-core, OTel | walidatory z Hub | **skip** |

## 4. Supply chain i niebezpieczna deserializacja

| Narzędzie | Licencja · wersja | Zależności | Co wykrywa | Fit |
|---|---|---|---|---|
| [modelscan](https://github.com/protectai/modelscan) (Protect AI) | Apache-2.0 · 0.8.8 (2026-02-18); Python <3.13 | click, numpy, rich, tomlkit | skanery `pickle` (pickle, dill, joblib, cloudpickle, `torch.save`), `h5`, `keras`, `saved_model` (np. operatory `ReadFile`/`WriteFile`); wyniki wg severity; API Python + CLI z kodami wyjścia | **wrap** (pliki modeli) |
| [picklescan](https://github.com/mmaitre314/picklescan) | MIT · 1.0.5 (2026-07-01); Python ≥3.11 | brak (numpy dla `.npy`) | niebezpieczne `global` w pickle (np. `__builtin__ eval`), archiwa zip (PyTorch), skan URL z HF | **use** (lekki, także pickle base64 w argumentach narzędzi) |
| [fickling](https://github.com/trailofbits/fickling) (Trail of Bits) | **LGPL-3.0+** · 0.1.12 (2026-06-26) | brak wymaganych (torch opcjonalny) | dekompilacja pickle do AST, `is_likely_safe()`, allowlista importów ML, hooki na `pickle.load`, poligloty PyTorch | **wrap** (dekompilat jako dowód w raporcie audytu) |
| [safetensors](https://github.com/huggingface/safetensors) | Apache-2.0 · 0.8.0 (2026-06-09) | brak | format bez wykonywania kodu — nie detektor | **use** w polityce: allowlista `.safetensors`/`.gguf`, blok `.pkl/.pt/.bin/.ckpt` bez skanu |
| [model-transparency](https://github.com/sigstore/model-transparency) (Sigstore) | Apache-2.0 · v1.1.1 (2025-10-10) | sigstore | podpisywanie i weryfikacja modeli | **inspiration** (sygnatury źródeł modeli) |

## 5. Rekomendowany stack na 24 h (MacBook, Apple Silicon)

| Klasa kontroli | Główny | Fallback (za wolny/niedostępny) | Uwagi |
|---|---|---|---|
| PII (EN + PL) | własne regexy + `python-stdnum` (PESEL, NIP, REGON, IBAN) | — (deterministyczne, <1 ms [INFERENCE]) | Presidio z `en_core_web_sm` tylko dla imion/lokalizacji, za flagą w polityce; nie używać `pl_core_news_*` (GPL-3.0) |
| Sekrety | `detect-secrets` (pluginy przez API) + regexy z `gitleaks.toml` w feedzie | sam feed regexów | entropia → tylko `redact`, nie `block` (FP) |
| Prompt injection / jailbreak | PG2-86M ONNX (`onnxruntime` + `tokenizers`), ~110 ms CPU | PG2-22M (~46 ms, słabszy PL) → protectai v2 (EN) | wejście >512 tok dzielić na okna; próg z polityki; „Built with Llama” w README |
| Treść szkodliwa (wej./wyj.) | `llama-guard3:1b` (Ollama) | `granite3-guardian:2b` → wyłączenie z `on_error` | `8b` tylko gdy RAM i czas pozwalają |
| Kryteria własne z polityki | `granite4.1-guardian:8b` no-think | `granite3-guardian:2b` z kategorią w system prompt | droga kontrola: na końcu pipeline'u, z timeoutem |
| Język polski (semantycznie) | spike: Qwen3Guard-Gen-0.6B GGUF przez `hf.co/…` | PG2-86M (wielojęzyczny) | potwierdzić szablon czatu GGUF |
| Pickle / modele | `picklescan` + `modelscan` | allowlista formatów (`safetensors`, `gguf`) | `fickling` dla raportu |
| Kod w argumentach narzędzi | sygnatury (regex/YARA) w feedzie | — | inspiracja: Vigil YARA, CodeShield |

Zasady fallbacku: kolejność tanie → drogie; każdy detektor semantyczny z timeoutem i `on_error` z polityki; detektor można wyłączyć w `policy.yaml` bez restartu.

**Do potwierdzenia w spike'u F0:** latencja i trafność `llama-guard3:1b`, `granite3-guardian:2b`, `granite4.1-guardian:8b`, Qwen3Guard-0.6B na ~30 promptach (EN + PL); działanie PG2 bez paddingu.
