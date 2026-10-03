# ADR-0003: Polityka jako wersjonowany kontrakt z przeładowaniem na żywo

**Status**: Accepted
**Data**: 2026-10-03

## Kontekst

Wymaganie R1: jedno źródło konfiguracji dla kontroli, progów (blokuj vs redaguj), dozwolonych modeli i budżetów. Jury zmienia konfigurację w trakcie działania (usuwa kontrole, zmienia progi) i sprawdza, czy zmiany działają na żywo. Źródło konfiguracji może być plikiem albo zewnętrznym systemem.

## Decyzja

- Polityka w pliku YAML (`config/policy.yaml`) z polem `version`.
- Schemat Pydantic w `core/policy.py`; każda kontrola ma: `enabled`, `action` (`block | redact | allow`), `threshold`, `on_error`, parametry własne.
- Źródło polityki za portem `PolicySource`: plik teraz, system zewnętrzny później bez zmian w rdzeniu.
- Przeładowanie na żywo: wykrycie zmiany → walidacja → atomowa podmiana niezmiennego obiektu polityki. Proxy odrzuca błędną politykę i dalej używa ostatniej poprawnej. Błąd trafia do dziennika audytu i na dashboard.
- Każde żądanie używa jednej migawki polityki od początku do końca.
- Warianty `policy.strict.yaml` i `policy.lenient.yaml` jako deliverable „Sample Configuration”.

## Konsekwencje

**Dobre**: zmiany jury nigdy nie wywracają instancji; jeden schemat dokumentuje wszystkie kontrole; spójne decyzje w trakcie przeładowania.

**Złe**: zmiana schematu wymaga podbicia `version` i aktualizacji przykładowych polityk.

**Mitygacje**: test ładujący wszystkie pliki z `config/`; test, że każda kontrola z polityki ma przypadki w `tests/cases/`.
