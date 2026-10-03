# ADR-0002: Stack — Python 3.12, FastAPI, Pydantic v2, Ollama

**Status**: Proposed — do akceptacji przez zespół na początku F0
**Data**: 2026-10-03

## Kontekst

Regulamin zostawia dowolność stacku (przykłady: Go, Rust, Python). Nie dostajemy płatnych API — modele muszą działać lokalnie (np. Ollama). Kod będzie pisany głównie z pomocą AI, więc liczy się, jak dobrze modele znają ekosystem, oraz szybkość pisania testów.

## Decyzja

- **Python 3.12**, zarządzanie zależnościami i lockfile: **uv**.
- **FastAPI** + **uvicorn** — adapter wejścia zgodny z API OpenAI i dashboard.
- **Pydantic v2** — schemat polityki i walidacja danych na granicach.
- **httpx** — klient do Ollamy i zewnętrznych API.
- **pytest** — testy; przypadki testowe w YAML.
- Jakość: **ruff** (lint + format), **mypy** (`--strict` dla `core/`), **import-linter**.
- **Ollama** — lokalne modele do kontroli semantycznych i jako upstream w demo.

## Rozważane opcje

- **Go** — wydajniejszy proxy, ale słabszy ekosystem ML/NLP i wolniejsze pisanie testów danych.
- **Rust** — najlepsza wydajność, najwolniejsza iteracja w 24 h.
- **TypeScript/Node** — dobre wsparcie AI, ale słabsze biblioteki do analizy treści.

## Konsekwencje

**Dobre**: modele AI dobrze znają ten stack; szybkie testy; bogate biblioteki do PII, sekretów i analizy plików modeli.

**Złe**: wydajność proxy niższa niż w Go/Rust.

**Mitygacje**: tanie kontrole deterministyczne przed semantycznymi; pomiar opóźnień per etap w telemetrii; porty pozwalają przepisać gorące ścieżki później.
