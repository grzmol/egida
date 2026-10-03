# ADR-0007: Egida: konfiguracja i uruchamianie AI Control Layer w terminalu

**Status**: Accepted. Nazwy pakietu i poleceń zmienia ADR-0008.
**Data**: 2026-10-03
**Decydują**: Grzegorz

## Kontekst

Cała konfiguracja proxy jest w pliku `config/policy.yaml` (ADR-0003). Jury zmienia politykę na żywo (W1). Ręczna edycja YAML daje błędy, których proxy nie naprawia. Proxy tylko odrzuca plik. Przykłady błędów:
- literówka w polu;
- odwołanie do budżetu albo modelu, którego nie ma;
- klucz API agenta, który trzeba samemu zahashować sha256.

Polityki w `config/` są też deliverable „Sample Configuration”. Ich komentarze są dokumentacją i zapis nie może ich usuwać. Uruchomienie proxy wymaga zmiennych środowiskowych (`CONTROL_LAYER_*`) i polecenia uvicorn. Zespół pracuje w pi/omp. Narzędzie ma wyglądać jak pi.

## Decyzja

**Egida** (`src/control_layer/egida/`, `uv run egida`, `make egida`) to jedno narzędzie terminalowe do konfiguracji i uruchamiania AI Control Layer.

- **Cała polityka.** Egida zmienia defaults, limits, upstreamy, modele, agentów, budżety i kontrole. Dla kontroli zmienia kolejność, `params` każdego detektora i `disabled_rules` z listy reguł feedu. Egida dodaje wpisy, zmienia ich nazwy razem z odwołaniami i usuwa je. Egida nie usuwa wpisu, którego coś używa.
- **Ta sama walidacja co w proxy.** Każda zmiana przechodzi przez `parse_policy` z modelami `Params` detektorów. Walidacja działa na dokładnie tym tekście, który Egida zapisze. Polityki z błędami nie można zapisać.
- **Bezpieczny zapis.** Przed zapisem Egida pokazuje diff do sprawdzenia. Zapis jest atomowy (plik tymczasowy w tym samym katalogu + `os.replace`). Dzięki temu poller proxy nigdy nie czyta połowy pliku. Jeśli plik na dysku zmienił się od wczytania (sha256), Egida zgłasza konflikt.
- **Profil uruchomienia** `config/egida.yaml` (YAML, model Pydantic `RunProfile`): host, port, plik polityki, dziennik audytu, feed sygnatur, adres guard LLM, katalog modeli. Wartości domyślne są takie same jak w proxy (`Settings.from_env`, `make run`). Test sprawdza tę zgodność.
- **Uruchamianie.** Egida uruchamia proxy tym samym poleceniem co `make run`, ze zmiennymi `CONTROL_LAYER_*` z profilu uruchomienia. Proxy działa jako proces potomny w tej samej grupie procesów. Log jest w `var/egida-proxy.log`. Egida czyta status z `GET /healthz` i `GET /api/policy` i porównuje sha256 aktywnej polityki z plikiem. Wyjście z Egidy zatrzymuje proxy. `egida run` uruchamia proxy z profilu uruchomienia na pierwszym planie, bez interfejsu.
- **Klucze API agentów.** Egida generuje klucz (`secrets`) i pokazuje go jeden raz. Do pliku trafia tylko sha256.
- **Wygląd pi bez frameworka.** Terminal używa tylko biblioteki standardowej (`termios`, `tty`, `select`). Elementy wyglądu:
  - paleta motywu `dark` pi, przeliczona z okhsl kodem pi-tui;
  - kursor `→`, ramki `─`, podpowiedzi klawiszy, kolorowe ramki wyników;
  - logo-tarcza z półbloków;
  - truecolor, 256 kolorów albo `NO_COLOR`.
- **Nowa zależność: ruamel.yaml 0.19.1 (MIT).** Egida używa jej do zapisu. Zapis zachowuje komentarze, kolejność i styl list. Proxy dalej czyta politykę przez PyYAML.

## Rozważane opcje

- **Textual / prompt_toolkit / urwid**: gotowe widżety. Wady: własny wygląd zamiast pi i większa zależność. Potrzebujemy tylko kilku prostych widżetów.
- **pi-tui (TypeScript)**: oryginalny wygląd. Wady: drugi runtime (Node/Bun) i druga kopia schematu. Walidacja musi być kodem proxy.
- **Zapis przez PyYAML**: bez nowej zależności. Wada: pierwszy zapis usuwa komentarze i układ przykładowych polityk.
- **Łatanie tekstu YAML po pozycjach węzłów PyYAML**: bez nowej zależności. Wada: to własny edytor round-trip (wstawianie, usuwanie i przenoszenie razem z komentarzami). To więcej kodu do obrony.
- **Zapis przez HTTP proxy**: nowy endpoint zapisu to nowa powierzchnia ataku i wymaga uwierzytelnienia administratora. To też odejście od polityki jako pliku (ADR-0003).
- **Ustawienia uruchomienia w `.env`**: znany format. Wady: proxy go nie czyta, a host i port to argumenty uvicorn, nie zmienne aplikacji. Osobny YAML z walidacją Pydantic jest spójny z polityką.
- **Proxy odłączone od Egidy (demon)**: proxy działa dalej po zamknięciu narzędzia. Wada: zostają osierocone procesy i porty. `make run` i `egida run` pokrywają długie uruchomienia.

## Konsekwencje

**Dobre**:
- Całą politykę i uruchomienie można ustawić bez znajomości YAML i zmiennych środowiskowych.
- Błędy są widoczne przed zapisem, nie w `last_error` proxy.
- Jedno miejsce pokazuje, czy proxy działa i czy wczytało zapisaną wersję.
- Klucze API nie trafiają do plików jawnym tekstem.
- Komentarze przykładowych polityk zostają po zapisie (round-trip bajt w bajt na wszystkich politykach z `config/`).
- Kod proxy bez zmian.

**Złe**:
- Jedna zależność więcej.
- Tylko POSIX (`termios`), bez Windows.
- Własny kod terminala i zarządzania procesem do utrzymania.
- ruamel.yaml przypina linie komentarzy do poprzedniego węzła. Dlatego Egida jawnie przenosi komentarze, gdy usuwa, dodaje na końcu lub przenosi wpisy.
- Profil uruchomienia to drugi plik konfiguracyjny obok zmiennych środowiskowych. Egida jawnie ustawia te zmienne dla procesu proxy.

**Mitygacje**:
- Testy round-trip i operacji na prawdziwych politykach z `config/`.
- Test zgodności wartości domyślnych profilu uruchomienia z `Settings.from_env`.
- import-linter zabrania importu Egidy w `core/`.
- Egida działa natywnie przez `uv`, bez nowej usługi w Compose.
