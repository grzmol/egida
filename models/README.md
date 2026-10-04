# models/

Lokalne pliki modeli. **Git ich nie śledzi** (w repo jest tylko ten README).

| Katalog | Model | Źródło (przypięta rewizja) | Licencja |
|---|---|---|---|
| `prompt-guard-2-86m/` | Llama Prompt Guard 2 86M, ONNX (kwantyzowany) | `gravitee-io/Llama-Prompt-Guard-2-86M-onnx@45a05fb` | Llama 4 Community |
| `prompt-guard-2-22m/` | Llama Prompt Guard 2 22M, ONNX (kwantyzowany), wersja zapasowa | `gravitee-io/Llama-Prompt-Guard-2-22M-onnx@da68d0f` | Llama 4 Community |

Aby pobrać modele i sprawdzić sha256, uruchom `uv run python scripts/fetch_models.py` (`--small` dla 22M).
Jeśli plik jest zmieniony, suma kontrolna się nie zgadza i skrypt kończy pracę z kodem 1.

Modele Ollamy (pobierane osobno, Ollama je przechowuje): `llama3.2:3b` (model czatu na demo),
`llama-guard3:1b` i `granite3-guardian:2b` (guard LLM, praca nocna B6).

Built with Llama.
