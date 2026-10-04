# ADR-0002: Stack: Python 3.12, FastAPI, Pydantic v2, Ollama

**Status**: Accepted (3.10, Sync 0), z poprawkami Z-1. Poprawki: Python 3.12 (modelscan wymaga <3.13), proxy natywnie przez `uv run`, modele ONNX w procesie, Ollama jako natywny proces obok (Metal), Docker Compose jako deliverable. Zależności i modele: ADR-0005.
**Data**: 2026-10-03

## Kontekst

Regulamin zostawia dowolność stacku (przykłady: Go, Rust, Python). Nie dostajemy płatnych API: modele muszą działać lokalnie (np. Ollama). Kod będzie pisany głównie z pomocą AI, więc liczy się, jak dobrze modele znają ekosystem, oraz szybkość pisania testów.

## Decyzja

- **Python 3.12**, zarządzanie zależnościami i lockfile: **uv**.
- **FastAPI** + **uvicorn**: adapter wejścia zgodny z API OpenAI i dashboard.
- **Pydantic v2**: schemat polityki i walidacja danych na granicach.
- **httpx**: klient do Ollamy i zewnętrznych API.
- **pytest**: testy; przypadki testowe w YAML.
- Jakość: **ruff** (lint + format), **mypy** (`--strict` dla `core/`), **import-linter**.
- **Ollama**: lokalne modele do kontroli semantycznych i jako upstream w demo.

## Rozważane opcje

- **Go**: wydajniejszy proxy, ale słabszy ekosystem ML/NLP i wolniejsze pisanie testów danych.
- **Rust**: najlepsza wydajność, najwolniejsza iteracja w 24 h.
- **TypeScript/Node**: dobre wsparcie AI, ale słabsze biblioteki do analizy treści.

## Konsekwencje

**Dobre**: modele AI dobrze znają ten stack; szybkie testy; bogate biblioteki do PII, sekretów i analizy plików modeli.

**Złe**: wydajność proxy niższa niż w Go/Rust.

**Mitygacje**: tanie kontrole deterministyczne przed semantycznymi; pomiar opóźnień per etap w telemetrii; porty pozwalają przepisać gorące ścieżki później.
