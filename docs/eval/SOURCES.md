# Publiczne i własne zbiory ewaluacyjne (FP/FN)

Dokumentacja źródeł, licencji i atrybucji dla zbiorów wykorzystywanych do pomiaru odporności (False Negatives) oraz nadmiernego blokowania (False Positives) w warstwie AI Control Layer.

**Właściciel:** Kamil (Dev C), zadanie K2.  
**Pliki wynikowe:** `var/eval/*.jsonl` (ignorowane w repozytorium gita).

---

## 1. Tabela zbiorów danych

| Plik | Źródło / Link | Split | Liczność (Attack / Benign) | Licencja | Wymagana atrybucja | Data pobrania |
|---|---|---|---|---|---|---|
| `deepset.jsonl` | [deepset/prompt-injections](https://huggingface.co/datasets/deepset/prompt-injections) | `test` | 116 (60 / 56) | `apache-2.0` (karta: też `cc-by-4.0`) | deepset.ai (Apache 2.0 / CC-BY-4.0) | 2026-10-03 |
| `gandalf.jsonl` | [Lakera/gandalf_ignore_instructions](https://huggingface.co/datasets/Lakera/gandalf_ignore_instructions) | `train` (pierwsze 150) | 150 (150 / 0) | `MIT` | Lakera AI (MIT License) | 2026-10-03 |
| `jbb.jsonl` | [JailbreakBench/JBB-Behaviors](https://huggingface.co/datasets/JailbreakBench/JBB-Behaviors) | `harmful`<br>`benign` | 200 (100 / 100) | `MIT` | JailbreakBench Team (MIT License) | 2026-10-03 |
| `xstest.jsonl` | [Paul/XSTest](https://huggingface.co/datasets/Paul/XSTest) | `train` (`label == safe`) | 250 (0 / 250) | `CC-BY-4.0` | Paul Röttger et al., XSTest: A Test Suite for Identifying Exaggerated Safety Behaviors in Large Language Models (CC-BY-4.0) | 2026-10-03 |
| `pl-manual.jsonl` | `docs/eval/pl-manual.yaml` | — | 40 (20 / 20) | `własne` (`froggers`) | Zespół froggers (HackYeah 2026) | 2026-10-03 |

---

## 2. Format rekordów (`var/eval/*.jsonl`)

Każda linia pliku JSONL to pojedynczy obiekt o schemacie:
```json
{
  "id": "deepset-test-0007",
  "text": "Tekst promptu",
  "label": "attack",
  "lang": "en",
  "source": "deepset/prompt-injections",
  "license": "apache-2.0"
}
```

* `label`: dokładnie jedna z dwóch wartości: `attack` lub `benign`.
* `lang`: kod ISO 639-1 (`en` lub `pl`).

---

## 3. Polecenie odtworzenia

Pobranie i wygenerowanie wszystkich 5 plików w katalogu `var/eval/`:
```bash
python scripts/prepare_eval_data.py
```
lub z poziomu `uv`:
```bash
uv run python scripts/prepare_eval_data.py
```

Pobranie tylko wybranych zbiorów (np. szybki test):
```bash
python scripts/prepare_eval_data.py --only deepset,pl-manual
```

---

## 4. Wyjaśnienie licencji i wykluczeń

Zgodnie z analizą w [docs/research/03-testy-i-red-teaming.md](../research/03-testy-i-red-teaming.md) §2:
- Wszystkie użyte zbiory posiadają licencje otwarte kompatybilne z celami hackathonu (`MIT`, `Apache-2.0`, `CC-BY-4.0`).
- Wykluczono zbiory o restrykcyjnych licencjach niekomercyjnych (`CC-BY-NC-4.0`: np. `qualifire/prompt-injections-benchmark`, `lmsys/toxic-chat`, `BeaverTails`) oraz zbiory bez jasnej licencji (np. `Tensor Trust`, `safe-guard-prompt-injection`).
- Zbiory nie są commitowane do repozytorium git (katalog `var/` jest w `.gitignore`); repozytorium zawiera wyłącznie powtarzalny skrypt i metadane.
