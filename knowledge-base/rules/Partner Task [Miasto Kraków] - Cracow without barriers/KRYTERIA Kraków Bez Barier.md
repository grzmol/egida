# Nazwa wyzwania

**Kraków bez barier**

## Krótki opis wyzwania

Stwórz narzędzie, które pomoże mieszkańcom i turystom ocenić dostępność miejsc i tras zgodnie z ich indywidualnymi potrzebami, a jednocześnie będzie źródłem informacji o dostępności oferty miasta. Rozwiązanie powinno prezentować konkretne informacje o barierach i udogodnieniach, a jednocześnie mieć potencjał do dalszego rozwoju, komercjalizacji i skalowania na inne miasta.

## 1. Wprowadzenie - opis organizacji, sytuacji i stanu aktualnego

Kraków jest miastem odwiedzanym przez mieszkańców oraz turystów o bardzo różnych potrzebach i sposobach poruszania się. Dostępność przestrzeni, obiektów i tras może mieć istotne znaczenie dla osób poruszających się na wózkach, rodziców z wózkami dziecięcymi, a także innych użytkowników, dla których schody, progi, wąskie wejścia czy określony rodzaj nawierzchni mogą stanowić przeszkodę.

Problemem nie jest wyłącznie brak informacji, ale również sposób jej prezentowania. Proste oznaczenie miejsca jako „dostępnego” lub „niedostępnego” nie zawsze pozwala użytkownikowi ocenić, czy dane miejsce lub trasa odpowiada jego indywidualnym potrzebom. Potrzebne są bardziej szczegółowe informacje, m.in. o schodach, progach, podjazdach, windach, szerokości wejścia, rodzaju nawierzchni, dostępności toalety czy miejscach odpoczynku. Ważne jest, aby dane te były w miarę możliwości aktualne.

Dane wykorzystane przez rozwiązanie mogą pochodzić z otwartych źródeł, OpenStreetMap, informacji publikowanych przez właścicieli obiektów oraz zgłoszeń użytkowników. Istotne jest wskazanie źródła danych, daty ich aktualizacji oraz poziomu ich wiarygodności. Informacje niepotwierdzone nie powinny być prezentowane jako formalne zapewnienie dostępności.

Rozwiązanie powinno być możliwe do rozwijania bez konieczności ręcznego utrzymywania bazy danych przez Miasto oraz bez dostępu do wewnętrznych systemów UMK lub MJO. Powinno być także proste w obsłudze i łatwe do wdrożenia w podmiotach, które mogą uznać je za użyteczne (np.hotele, organizatorzy wydarzeń). Jednocześnie powinno mieć potencjał do zastosowania także poza Krakowem, np. przez inne miasta, właścicieli obiektów, hotele, organizatorów wydarzeń, zarządców nieruchomości, systemy rezerwacyjne oraz dostawców map i aplikacji turystycznych.

## 2. Wyzwanie

Zaprojektuj i przygotuj prototyp narzędzia, które umożliwi mieszkańcom i turystom uzyskanie informacji oraz ocenę dostępności wybranych miejsc lub tras zgodnie z ich indywidualnymi potrzebami. Rozwiązanie nie powinno ograniczać się do prostego komunikatu „dostępne/niedostępne”, lecz przedstawiać szczegółowe informacje pozwalające użytkownikowi samodzielnie ocenić, czy dane miejsce lub trasa odpowiada jego potrzebom.

Prototyp powinien zostać ograniczony do wybranej grupy użytkowników lub określonego rodzaju potrzeb, np. osób poruszających się na wózkach oraz rodziców z wózkami dziecięcymi.

## 3. Oczekiwany rezultat

Oczekiwanym rezultatem jest działający prototyp rozwiązania, które pozwala sprawdzić dostępność wybranego miejsca lub trasy i prezentuje szczegółowe informacje istotne dla określonej grupy użytkowników.

Prototyp powinien w szczególności:

- prezentować jak najaktualniejsze informacje o konkretnych barierach i udogodnieniach, np. schodach, progach, podjazdach, windach, szerokości wejścia, nawierzchni, toalecie i miejscach odpoczynku;
- wskazywać źródło informacji, datę jej aktualizacji oraz poziom wiarygodności;
- wykorzystywać dane z dostępnych źródeł, bez konieczności ręcznego utrzymywania bazy przez Miasto;
- nie wymagać dostępu do wewnętrznych systemów UMK lub MJO;
- uwzględniać potrzeby wybranej grupy użytkowników;
- być łatwy w użytkowaniu oraz wdrożeniu u potencjalnych odbiorców;
- pokazywać potencjał dalszego rozwoju, komercjalizacji i skalowania rozwiązania na inne miasta lub sektory.

## 4. Wymagania formalne

Projekt przesyłany do oceny powinien zawierać:

- opis rozwiązania i wskazanie problemu, który rozwiązuje;
- prototyp lub demonstrację działania rozwiązania;
- informację o grupie docelowej i sposobie wykorzystania rozwiązania;
- opis źródeł danych oraz sposobu oceny ich aktualności i wiarygodności;
- propozycję modelu biznesowego i możliwości dalszego rozwoju rozwiązania;
- prezentację projektu w formacie PDF (maksymalnie 10 slajdów);
- film prezentujący działanie projektu, umieszczony w dostępnym, otwartym repozytorium (maksymalnie 3 minuty).

Dodatkowo projekt może zawierać repozytorium kodu, zrzuty ekranu, link do demonstracji oraz inne materiały związane z projektem.

## 5. Wymagania techniczne i organizacyjne

- Rozwiązanie może mieć dowolną formę techniczną, np. aplikacji internetowej lub mobilnej, pod warunkiem że umożliwia demonstrację głównego scenariusza: wyszukania miejsca lub trasy i przedstawienia informacji o dostępności istotnych dla wybranej grupy użytkowników.
- Architektura powinna oddzielać pozyskiwanie i aktualizację danych od sposobu ich prezentacji. Zespół powinien wskazać główne komponenty rozwiązania, przepływ danych oraz sposób dodawania kolejnych źródeł, kategorii miejsc i obszarów geograficznych.
- Należy korzystać z publicznie dostępnych danych i usług na warunkach określonych przez ich dostawców. W przypadku danych miejskich należy wskazać konkretne zbiory lub publiczne interfejsy API, sposób ich pobierania, częstotliwość aktualizacji i postępowanie w razie niedostępności źródła. Rozwiązanie nie może zakładać dostępu do wewnętrznych systemów UMK lub miejskich jednostek organizacyjnych.
- Przy każdej informacji o dostępności należy przewidzieć możliwość wskazania jej źródła, daty pozyskania lub ostatniego potwierdzenia oraz statusu wiarygodności. Dane pochodzące ze zgłoszeń użytkowników lub innych niezweryfikowanych źródeł muszą być wyraźnie odróżnione od informacji potwierdzonych. Rozwiązanie powinno przewidywać sposób poprawiania błędnych i nieaktualnych danych.
- Interfejs należy projektować z uwzględnieniem dostępności cyfrowej, przyjmując WCAG 2.2 na poziomie AA jako cel rozwoju rozwiązania. Już w prototypie należy zadbać zwłaszcza o obsługę klawiaturą i czytnikiem ekranu, czytelność treści, odpowiedni kontrast oraz tekstową alternatywę dla informacji przedstawianych wyłącznie na mapie. Ocena prototypu powinna uwzględniać wykaz funkcji już dostępnych oraz elementów wymagających dalszych prac.
- Należy przedstawić propozycję uruchomienia i dalszego utrzymania rozwiązania poza infrastrukturą UMK, w tym wskazać podmiot odpowiedzialny za hosting, aktualizacje, bezpieczeństwo, obsługę zgłoszeń i koszty działania. Prototyp nie musi być dostępny jako stała usługa po hackathonie, ale przyjęty model powinien umożliwiać jego dalszy rozwój.
- Należy opisać podstawowe zasady ochrony danych i bezpieczeństwa, w szczególności zakres zbieranych danych użytkowników, sposób ochrony zgłoszeń i kont, jeżeli są przewidziane, oraz korzystanie z bezpiecznych połączeń. Projekt nie powinien wymagać podawania informacji o niepełnosprawności, jeżeli do dopasowania wyników wystarczą preferencje dotyczące barier i udogodnień.
- Rozwiązanie powinno nadawać się do rozwijania i wdrażania przez inne podmioty. Zespół powinien wskazać zależności od zewnętrznych dostawców, licencje wykorzystywanych danych i komponentów, możliwość przeniesienia rozwiązania na inną infrastrukturę oraz sposób dodania kolejnego miasta. Wybór konkretnych technologii pozostaje po stronie zespołu.

## 6. Sposób testowania i/lub walidacji

- Podczas prezentacji zespół powinien przeprowadzić **działającą demonstrację** dla wybranej grupy użytkowników: określić jej potrzeby, sprawdzić co najmniej jedno miejsce lub trasę i pokazać konkretne bariery oraz udogodnienia, które pozwalają samodzielnie ocenić przydatność wyniku.
- Należy pokazać, skąd pochodzą prezentowane informacje, kiedy zostały pozyskane lub potwierdzone oraz jak aplikacja oznacza dane niepełne, nieaktualne bądź niezweryfikowane. Jeżeli demonstracja wykorzystuje dane przykładowe, trzeba je jednoznacznie oznaczyć.
- Należy sprawdzić działanie rozwiązania w co najmniej jednym przypadku, w którym dane są sprzeczne, niepełne albo źródło danych jest niedostępne, i wyjaśnić, co zobaczy wówczas użytkownik. Aplikacja nie powinna przedstawiać braku informacji jako potwierdzenia dostępności miejsca lub trasy.
- Zespół powinien wykonać podstawową kontrolę dostępności głównego scenariusza użytkownika, obejmującą co najmniej obsługę klawiaturą, odczyt informacji przez czytnik ekranu, kontrast oraz dostępność informacji z mapy w formie tekstowej. Należy wskazać stwierdzone ograniczenia prototypu i plan ich usunięcia.
- W ramach prezentacji należy przedstawić krótki plan przejścia od prototypu do usługi: podmiot odpowiedzialny za produkt, model pozyskiwania i weryfikowania danych, sposób finansowania hostingu i utrzymania, plan dalszych prac oraz warunki uruchomienia rozwiązania w kolejnym mieście.

## 7. Dostępne zasoby

Uczestnicy mogą korzystać z poniższych źródeł oraz z innych publicznie dostępnych danych przydatnych do rozwiązania wyzwania:

- **Portal Otwarte Dane Miasta Krakowa** – zbiory danych miejskich udostępniane m.in. w formatach JSON, CSV i XLSX oraz przez interfejsy API, zależnie od zasobu. otwartedane.um.krakow.pl
- **Miejski System Informacji Przestrzennej (MSIP)** – katalog danych przestrzennych Krakowa. Wybrane zasoby są dostępne do pobrania lub przez usługi WMS i WFS. Zakres danych i warunki ich wykorzystania należy sprawdzić dla konkretnego zasobu. msip.krakow.pl
- **Portal Otwarte Dane (dane.gov.pl)** – ogólnopolski katalog danych publicznych, który może dostarczyć danych uzupełniających oraz zasobów przydatnych przy rozwijaniu rozwiązania na inne miasta. dane.gov.pl
- **OpenStreetMap** – społecznościowe dane o obiektach i sieci dróg, które mogą stanowić podstawę mapy i wyszukiwania tras. Wykorzystanie danych wymaga przestrzegania warunków licencji i oznaczenia źródła. openstreetmap.org

Można również wykorzystać inne otwarte źródła oraz informacje udostępniane przez właścicieli obiektów lub zgłaszane przez użytkowników. **Samo opublikowanie informacji w internecie nie oznacza jednak, że wolno ją automatycznie pobierać i wykorzystywać komercyjnie.** Zespół powinien dla każdego użytego źródła wskazać jego pochodzenie, warunki wykorzystania, aktualność oraz sposób weryfikacji danych.

## 8. Kryteria oceny

Proponowane kryteria oceny:

| Kryterium | Waga |
|---|---|
| Związek z wyzwaniem i użyteczność dla wskazanej grupy użytkowników, w tym łatwość użytkowania | 25% |
| Jakość i kompletność prototypu | 20% |
| Wiarygodność oraz sposób prezentacji i aktualizacji danych | 15% |
| Potencjał wdrożeniowy i możliwość skalowania | 20% |
| Model biznesowy, potencjał komercjalizacji i rozwoju rynkowego | 20% |

## 9. Dodatkowe uwagi / kontekst wdrożeniowy

Celem wyzwania jest nie tylko stworzenie rozwiązania odpowiadającego na konkretną potrzebę miasta, ale również rozwój pomysłu z myślą o jego dalszej komercjalizacji i skalowaniu – zarówno na rynku lokalnym, jak i krajowym.

Dlatego w ocenie szczególne znaczenie będzie miał potencjał biznesowy projektu, w tym model biznesowy, możliwość uruchomienia i rozwoju aplikacji oraz jej potencjał rynkowy.

Potencjalne kierunki komercjalizacji obejmują usługi dla właścicieli obiektów, hoteli, organizatorów wydarzeń, zarządców nieruchomości, systemów rezerwacyjnych oraz dostawców map i aplikacji turystycznych.

## 10. Kontakt

- Bartłomiej Węglarz- w strefie mentorskiej i na discord
- Karolina Grzanka- w strefie mentorskiej i na discord
- Michał Janaś- w strefie mentorskiej i na discord
