# SUPERTEAM POLAND CHALLENGE

## Finance Without Intermediaries

Imagine a transaction with someone you don’t know. No history, no reputation, no way to go after them if they disappear with your money. Blockchain makes this irrelevant: the terms execute themselves, regardless of what the other party wants. Put this capability to use in an application.

### 1. Introduction: the organization, the context and the current state

Superteam is a non-profit organization supporting developers, designers and entrepreneurs building on Solana. We operate in more than a dozen countries, and Superteam Poland brings together Polish builders creating products on open financial infrastructure. We are not a company commissioning a project, but a community that helps people enter the ecosystem: we connect people with grants, mentors and teams looking for support.

Most of the financial systems we use every day rely on trust in an intermediary. When you make a bank transfer, you trust the bank to carry out your instruction. When you take out a loan, both parties trust the institution that assesses creditworthiness and enforces repayment. When you buy something online, you trust the payment operator to pass the money on to the seller. This model works, but it comes at a cost: the intermediary charges a fee, decides who gets served, can block or reverse a transaction, and when it fails, everyone stops.

Blockchain technology changes this dependency. Instead of trusting an institution, you trust code that anyone can read, and a network in which no single party decides the outcome on its own. Solana is one such network, designed for high throughput and low fees. A transaction is confirmed in a fraction of a second and costs a fraction of a cent, which in practice means you can build things on it that were not economically viable before: micropayments, per-second settlements, automatic revenue sharing between many parties.

The best example of what this shift enables is lending protocols. A traditional loan requires an institution that verifies creditworthiness, keeps a record of the obligation and collects the debt. In a lending protocol there is no such institution: the loan terms, the collateral and the liquidation point are written into a program running on the network, and they execute automatically, identically for every participant. The lender does not need to know or trust the borrower, because they rely not on the borrower’s honesty, but on a rule that neither party can circumvent.

This is the pattern that interests us most: take a financial relationship that today requires a trusted intermediary and redesign it so that the intermediary is no longer needed. Lending is just one example. The same pattern applies to escrow, settlements between freelancers and clients, fundraisers with conditional refunds, revenue sharing, parametric insurance, loyalty programs and business-to-business settlements.

### 2. The challenge

**Design and build a solution on Solana that removes the need for trust from a financial transaction.**

The starting point is a question: where in your surroundings (at work, in business, in everyday life) do you have to trust someone for a transaction to go through? The other party, to keep to the terms? An intermediary who is supposed to guarantee this? Or perhaps both at once? Who profits from it, how much does it cost, and what happens when that trust turns out to be misplaced?

Then redesign this relationship so that the terms of the transaction are written into a program running on the network and execute automatically, identically for every participant, with no possibility of unilateral change. Party A does not need to trust party B, because both rely on a rule that neither of them can circumvent. Nor do they need anyone to enforce that rule.

The challenge is open: we do not impose a domain or a form. You can take a market you know from the inside and tackle a specific problem, or build a general-purpose tool that others will use. We care about the quality of the reasoning behind the project as much as about the code itself.

### 3. Expected outcome

We expect a working application: not a concept, not a mockup, but something that can be launched and clicked through. We do not expect a production-ready product. We expect the user to be able to go through the full flow from start to finish and see the result.

We consider the application complete when:

- it implements at least one full use case, from user input to a completed transaction;
- it can demonstrate the moment at which the intermediary is no longer needed; this is the heart of the project, and we want to see how it works in practice;
- it works live during the presentation, not just in a recording.

The interface can be rough. We prefer a simple application where everything works over a polished design with nothing happening underneath.

**Who you are building for.** You define your target user, and we expect you to name them explicitly: “freelancers invoicing foreign clients”, “fundraiser organizers”, “developers building on Solana”. This determines the language of the interface and how much of the technical layer is hidden from the user. A tool for developers and an app for people outside the crypto world are two different things. We value both equally, as long as the choice is deliberate.

In addition to the application itself, we expect a short design rationale: which financial relationship was redesigned, who the intermediary in it was, and what specifically changes once they are removed.

### 4. Submission requirements

The project submitted for evaluation should include:

- the project title and a detailed description, including the design rationale;
- a presentation in PDF format (maximum 10 slides);
- a video hosted in a publicly accessible location (link), no longer than 3 minutes, presenting the project;
- a code repository.

It may additionally include:

- screenshots;
- links to demos;
- graphics or other materials related to the project.

### 5. Technical requirements

The solution must run on Solana. Devnet is sufficient: we do not expect a mainnet deployment or the use of real funds. You can get test SOL from a public faucet.

**Environment.** Setting up Rust, the Solana CLI and Anchor from scratch can take several hours. Our materials include a ready-made dev container: you launch it in VS Code or GitHub Codespaces and have the entire toolchain at hand, without installing anything locally. If you would rather skip even that, Solana Playground lets you compile and deploy a program straight from your browser.

**The logic that replaces the intermediary must live in the on-chain program.** This is the essence of the challenge: if your backend enforces the transaction terms, the intermediary has not disappeared; it has simply become you.

For the rest of the stack, you have a free hand:

- **On-chain program:** Anchor (the easiest entry point), native Rust, Pinocchio, Steel or anything else that compiles.
- **Frontend:** any framework, any language. Communication with the network is typically handled with @solana/kit or @solana/web3.js, and wallet handling with Wallet Adapter.
- **Ready-made building blocks:** it is worth using what the ecosystem already offers, such as the SPL Token and Token-2022 standards, price oracles (Pyth, Switchboard), and existing protocols and their SDKs. There is no need to write everything from scratch.

### 6. Testing and validation

Evaluation takes place during a live presentation in front of the judges.

**What the demo looks like.** You show the application in action, live, not from a recording. You walk through at least one full scenario from start to finish: the user arrives, connects a wallet, performs an operation and sees the result. We want to see a confirmed transaction on the network. Keep a block explorer (Solana Explorer, Solscan) at hand: the quickest way to prove that something really happened is to show the transaction on-chain.

Prepare your environment in advance: wallets funded with test SOL, accounts in the right state, and ideally two wallets if your scenario involves two parties. A faucet outage or lack of internet will not disqualify your project, but it will make the conversation much harder, so have a recording ready as a backup.

**What we will ask about.** We will not test you on blockchain theory. The questions concern what you have built:

- Where exactly in the code does the intermediary disappear? Which part of the program enforces the terms that neither party can circumvent?
- What happens if one of the parties disappears halfway through the transaction? Where are the funds then, and who can recover them?
- Who has permission to perform which operations? Can you, as the author, change anything after deployment?
- Why blockchain and not a regular database? This question will definitely come up, so have an answer ready.
- What would you do next if you had another week?

**What we do not evaluate.** We do not test resistance to attacks, we do not run an audit, and we will not nitpick design quality or test coverage. We do not require everything to work flawlessly: if something breaks during the demo, say plainly what went wrong and why. We value awareness of your project’s limitations more highly than pretending they don’t exist.

**Code.** We look at the repository, both before and after the presentation. We don’t read everything line by line, but we check whether the on-chain program does what the demo shows. Make sure you have a clear README describing what is where.

### 7. Available resources

Everything is publicly available; you don’t need to download anything from us on site.

**Superteam Poland bootcamp “From Zero to Blockchain Developer”:** slides, a handbook and review questions. If you are starting from scratch, start here.

- matzayonc.github.io/stpl-bootcamp: theoretical materials
- github.com/matzayonc/solana-live-course-2026: examples and the dev container

**Solana documentation** (available in Polish): solana.com/pl/docs. You will also find a browser quickstart and npx create-solana-dapp there.

**Anchor**, the simplest path to an on-chain program: anchor-lang.com/docs, book.anchor-lang.com.

**On site:** Solana Playground (deployment without a local environment), a devnet faucet, and Solana Explorer for showing transactions during the demo. Mentors will be at the booth throughout the entire hackathon, including when you don’t yet know what to build.

### 8. Evaluation criteria

| Criterion | Weight |
|---|---|
| Relevance to the challenge | 30% |
| Completeness and functionality | 25% |
| Idea and choice of problem | 20% |
| Implementation potential | 15% |
| Originality | 10% |

### 9. Additional notes and implementation context

**What happens after the hackathon.** Superteam’s involvement does not end with the announcement of the results. We invite the most interesting projects to continue development within the community: we help refine the idea, find co-founders and users, and prepare a grant application to the Solana ecosystem. For teams that want to keep going, the hackathon is a starting point, not the finish line.

**Grants and funding.** The Solana Foundation and funds operating in the ecosystem regularly finance early-stage projects. We know these paths and will gladly advise which one suits your project, what the process looks like and what the reviewers expect. Taking part in the challenge does not guarantee funding, but it gives you access to people who have been through it.

**Jobs and paid work.** Teams building on Solana are looking for developers, and Superteam is where the two sides meet. A strong performance at the hackathon is a real portfolio piece; several people from our community have joined projects this way. We also publish paid bounties for community members.

**The code remains yours.** We claim no rights to anything you create. We only ask that the repository be public for the duration of the evaluation. What you do with the project afterwards is entirely up to you, even if that means nothing at all.

**If you don’t know Solana.** This challenge is not only for people with on-chain experience. Our mentors will be available throughout the hackathon and will help you go from first launching the environment to a working prototype. If you want to get started earlier, reach out to us before the event: we will send you materials and help you set up your environment so you don’t lose time on it on Saturday morning.

### 10. Contact

We are available throughout the hackathon.

- **Superteam Poland booth:** the fastest way to get answers.
- **Telegram:** @matzayonc, @matjanisz (also before the event, if you want to set up your environment early).
- **Email:** pl@superteam.fun
- **Our channels:** linktr.ee/superteampoland

There are no stupid questions. If you are approaching something on-chain for the first time, just say so, and we will tailor the help to your level.

---

# WYZWANIE SUPERTEAM POLAND

## Finanse bez pośrednika

Wyobraź sobie transakcję z kimś, kogo nie znasz. Bez historii, bez reputacji, bez możliwości ścigania go, gdy zniknie z Twoimi pieniędzmi. Blockchain sprawia, że to przestaje mieć znaczenie - warunki wykonują się same, niezależnie od tego, czego chce druga strona. Użyj tych możliwości w aplikacji.

### 1. Wprowadzenie – opis organizacji, sytuacji i stanu aktualnego

Superteam to organizacja non-profit wspierająca deweloperów, projektantów i przedsiębiorców budujących na Solanie. Działamy w kilkunastu krajach, a Superteam Poland zrzesza polskich builderów, którzy tworzą produkty w otwartej infrastrukturze finansowej. Nie jesteśmy firmą zlecającą projekt, a społecznością, która pomaga wejść w ekosystem: łączymy ludzi z grantami, mentorami i zespołami szukającymi wsparcia.

Większość systemów finansowych, z których korzystamy na co dzień, opiera się na zaufaniu do pośrednika. Robiąc przelew, ufasz bankowi, że wykona dyspozycję. Biorąc kredyt, obie strony ufają instytucji, która ocenia zdolność kredytową i egzekwuje spłatę. Kupując coś w internecie, ufasz operatorowi płatności, że przekaże pieniądze sprzedawcy. Ten model działa, ale ma koszt: pośrednik pobiera prowizję, decyduje kto zostanie obsłużony, może transakcję zablokować lub cofnąć, a jego awaria zatrzymuje wszystkich.

Technologia Blockchain zmienia tę zależność. Zamiast ufać instytucji, ufasz kodowi, który każdy może przeczytać, i sieci, w której żadna pojedyncza strona nie decyduje samodzielnie o wyniku. Solana jest jedną z takich sieci, zaprojektowaną pod dużą przepustowość i niskie opłaty. Transakcja potwierdza się w ułamku sekundy i kosztuje ułamek grosza, co w praktyce oznacza, że da się na niej budować rzeczy, które wcześniej nie były ekonomicznie praktyczne – mikropłatności, rozliczenia sekundowe, automatyczne podziały przychodu między wiele stron.

Najlepszym przykładem tego, co daje ta zmiana, są protokoły lendingowe. Klasyczny kredyt wymaga instytucji, która sprawdza wiarygodność, prowadzi rejestr zobowiązania i ściąga należność. W protokole lendingowym nie ma tej instytucji: warunki pożyczki, zabezpieczenie i moment likwidacji są zapisane w programie działającym w sieci i wykonują się same, identycznie dla każdego uczestnika. Pożyczkodawca nie musi znać ani ufać pożyczkobiorcy, bo nie polega na jego uczciwości, tylko na regule, której żadna ze stron nie może obejść.

To jest wzorzec, który interesuje nas najbardziej: wziąć relację finansową, która dziś wymaga zaufanego pośrednika, i przeprojektować ją tak, żeby pośrednik przestał być potrzebny. Lending jest tylko jednym przykładem. Ten sam schemat pasuje do escrow, rozliczeń między freelancerem a klientem, zbiórek z warunkowym zwrotem, podziału przychodów, ubezpieczeń parametrycznych, systemów lojalnościowych czy rozliczeń między firmami.

### 2. Wyzwanie

**Zaprojektuj i zbuduj na Solanie rozwiązanie, które usuwa z transakcji finansowej konieczność zaufania.**

Punktem wyjścia jest pytanie: gdzie w Twoim otoczeniu (w pracy, w biznesie, w codziennym życiu) musisz komuś zaufać, żeby transakcja doszła do skutku? Drugiej stronie, że dotrzyma warunków? Pośrednikowi, który ma to zagwarantować? A może obu naraz? Kto na tym zarabia, ile to kosztuje i co się dzieje, gdy zaufanie okaże się nieuzasadnione.

Następnie przeprojektuj tę relację tak, żeby warunki transakcji były zapisane w programie działającym w sieci i wykonywały się automatycznie – identycznie dla każdego uczestnika, bez możliwości jednostronnej zmiany. Strona A nie musi ufać stronie B, bo obie polegają na regule, której żadna z nich nie jest w stanie obejść. Nie potrzebują też nikogo, kto tej reguły dopilnuje.

Wyzwanie jest otwarte: nie narzucamy obszaru ani formy. Możesz wziąć rynek, który znasz od środka, i zaatakować konkretny problem, albo zbudować narzędzie ogólnego przeznaczenia, z którego skorzystają inni. Interesuje nas jakość rozumowania stojącego za projektem tak samo jak sam kod.

### 3. Oczekiwany rezultat

Oczekujemy działającej aplikacji – nie koncepcji, nie makiety, tylko czegoś, co da się uruchomić i przeklikać. Nie oczekujemy produktu gotowego do wdrożenia. Oczekujemy, że użytkownik przejdzie pełną ścieżkę od początku do końca i zobaczy efekt.

Aplikację uznajemy za kompletną, gdy:

- realizuje przynajmniej jeden pełny scenariusz użycia – od wejścia użytkownika do zakończonej transakcji,
- da się w niej pokazać moment, w którym pośrednik przestaje być potrzebny; to serce projektu i chcemy zobaczyć, jak działa w praktyce,
- działa na żywo podczas prezentacji, a nie tylko na nagraniu.

Interfejs może być surowy. Wolimy prostą aplikację, w której wszystko działa, niż dopracowany design, pod którym nic się nie dzieje.

**Dla kogo budujesz.** To Ty definiujesz odbiorcę i oczekujemy, że nazwiesz go wprost – "freelancerzy rozliczający się z klientami zagranicznymi", "organizatorzy zbiórek", "deweloperzy budujący na Solanie". Od tego zależy język interfejsu i to, ile warstwy technicznej zostaje ukryte przed użytkownikiem. Narzędzie dla devów i aplikacja dla ludzi spoza świata krypto to dwie różne rzeczy – obie są dla nas równie wartościowe, o ile wybór jest świadomy.

Poza samą aplikacją oczekujemy krótkiego uzasadnienia projektowego: jaka relacja finansowa została przeprojektowana, kto był w niej pośrednikiem, co konkretnie zmienia jego usunięcie.

### 4. Wymagania formalne

Projekt przesyłany do oceny powinien zawierać:

- tytuł projektu i jego szczegółowy opis z uzasadnieniem projektowym,
- prezentację w formacie PDF (maksymalnie 10 slajdów),
- film umieszczony w dostępnym, otwartym repozytorium (link), trwający maksymalnie 3 minuty i prezentujący projekt.
- repozytorium kodu,

Dodatkowo może zawierać:

- zrzuty ekranu,
- linki do demonstracji,
- materiały graficzne lub inne elementy związane z projektem.

### 5. Wymagania techniczne

Rozwiązanie musi działać na Solanie. Wystarczy devnet – nie oczekujemy wdrożenia na mainnet ani operowania prawdziwymi środkami. Testowe SOL pobierzesz z publicznego faucetu.

**Środowisko.** Stawianie Rusta, Solana CLI i Anchora od zera potrafi zająć kilka godzin. W naszych materiałach znajdziesz gotowy dev container – odpalasz go w VS Code albo w GitHub Codespaces i masz cały toolchain od ręki, bez instalowania czegokolwiek lokalnie. Jeśli wolisz obejść się nawet bez tego, Solana Playground pozwala skompilować i wdrożyć program prosto z przeglądarki.

**Logika, która zastępuje pośrednika, musi znajdować się w programie on-chain.** To jest istota wyzwania: jeśli warunki transakcji egzekwuje Twój backend, pośrednik nie zniknął – zmienił się w Ciebie.

Co do reszty stosu masz wolną rękę:

**Program on-chain** - Anchor (najprostsze wejście), natywny Rust, Pinocchio, Steel lub cokolwiek innego, co się kompiluje.

**Frontend** – dowolny framework, dowolny język. Do komunikacji z siecią typowo @solana/kit lub @solana/web3.js, do obsługi portfela Wallet Adapter.

**Gotowe klocki** - warto korzystać z tego, co ekosystem już oferuje: standardu SPL Token i Token-2022, oracli cenowych (Pyth, Switchboard), istniejących protokołów i ich SDK. Nie ma potrzeby pisać wszystkiego od zera.

### 6. Sposób testowania i/lub walidacji

Ocena odbywa się podczas prezentacji na żywo przed jurorami.

**Jak wygląda demo.** Pokazujesz aplikację w działaniu - na żywo, nie z nagrania. Przechodzisz przynajmniej jeden pełny scenariusz od początku do końca: użytkownik wchodzi, podłącza portfel, wykonuje operację, widzi efekt. Chcemy zobaczyć potwierdzoną transakcję w sieci. Trzymaj pod ręką eksplorator (Solana Explorer, Solscan) - najszybszy sposób udowodnienia, że coś naprawdę się wydarzyło, to pokazanie transakcji na łańcuchu.

Przygotuj środowisko wcześniej: portfele z testowym SOL, konta w odpowiednim stanie, a najlepiej dwa portfele, jeśli Twój scenariusz wymaga dwóch stron. Awaria faucetu albo brak internetu nie zdyskwalifikuje projektu, ale znacznie utrudni rozmowę - miej nagranie jako plan awaryjny.

**O co będziemy pytać.** Nie sprawdzamy Cię z teorii blockchaina. Pytania dotyczą tego, co powstało:

- Gdzie dokładnie w kodzie znika pośrednik? Który fragment programu egzekwuje warunki, których żadna ze stron nie może obejść?
- Co się stanie, gdy jedna ze stron zniknie w połowie transakcji? Gdzie są wtedy środki i kto może je odzyskać?
- Kto ma uprawnienia do jakich operacji? Czy Ty jako autor możesz coś zmienić po wdrożeniu?
- Dlaczego blockchain, a nie zwykła baza danych? To pytanie padnie na pewno - przygotuj odpowiedź.
- Co dalej, gdyby był jeszcze tydzień na przygotowanie?

**Czego nie oceniamy.** Nie testujemy odporności na ataki, nie robimy audytu, nie czepiamy się jakości designu ani pokrycia testami. Nie wymagamy, żeby wszystko działało bezbłędnie - jeśli coś się wysypie w trakcie demo, powiedz wprost, co poszło nie tak i dlaczego. Świadomość ograniczeń własnego projektu oceniamy wyżej niż udawanie, że ich nie ma.

**Kod.** Zaglądamy do repozytorium - także przed prezentacją i po niej. Nie czytamy wszystkiego linijka po linijce, ale sprawdzamy, czy program on-chain robi to, co pokazuje demo. Zadbaj o czytelne README z opisem, co gdzie leży.

### 7. Dostępne zasoby

Wszystko jest publicznie dostępne - niczego nie trzeba od nas pobierać na miejscu.

**Bootcamp Superteam Poland „Od Zera do Blockchain Developera"** - slajdy, podręcznik i pytania kontrolne. Jeśli zaczynasz od zera, zacznij tutaj.

- matzayonc.github.io/stpl-bootcamp - Materiały teoretyczne
- https://github.com/matzayonc/solana-live-course-2026 – przykłady i Devcontainer

**Dokumentacja Solany** (jest po polsku) – solana.com/pl/docs. Tam też quickstart w przeglądarce i npx create-solana-dapp.

**Anchor** - najprostsza droga do programu on-chain: anchor-lang.com/docs, book.anchor-lang.com.

**Na miejscu:** Solana Playground (deploy bez lokalnego środowiska), faucet devnetowy, Solana Explorer do pokazania transakcji na demie. Mentorzy przy stoisku przez cały hackathon - również wtedy, gdy nie wiesz jeszcze, co budować.

### 8. Kryteria oceny

| Kryterium | Waga |
|---|---|
| Związek z wyzwaniem | 30% |
| Kompletność i działanie | 25% |
| Pomysł i wybór problemu | 20% |
| Potencjał wdrożeniowy | 15% |
| Oryginalność | 10% |

### 9. Dodatkowe uwagi / kontekst wdrożeniowy

**Co dzieje się po hackathonie.** Superteam nie kończy współpracy na ogłoszeniu wyników. Najciekawsze projekty zapraszamy do dalszego rozwoju w ramach społeczności - pomagamy dopracować pomysł, znaleźć współzałożycieli i użytkowników, a także przygotować aplikację o grant z ekosystemu Solany. Dla zespołów, które chcą ciągnąć temat dalej, hackathon jest punktem startowym, nie metą.

**Granty i finansowanie.** Fundacja Solany oraz działające w ekosystemie fundusze regularnie finansują projekty na wczesnym etapie. Znamy te ścieżki i chętnie podpowiemy, która pasuje do Twojego projektu, jak wygląda proces i czego oczekują oceniający. Udział w wyzwaniu nie gwarantuje finansowania, ale daje dostęp do ludzi, którzy przez to przechodzili.

**Praca i zlecenia.** Zespoły budujące na Solanie szukają deweloperów, a Superteam jest miejscem, w którym te dwie strony się spotykają. Dobre wykonanie na hackathonie jest realnym portfolio - kilka osób z naszej społeczności trafiło do projektów właśnie tą drogą. Publikujemy też płatne zlecenia dla członków społeczności.

**Kod zostaje Twój.** Nie rościmy sobie żadnych praw do tego, co powstanie. Prosimy jedynie o publiczne repozytorium na czas oceny. Co zrobisz z projektem dalej, zależy wyłącznie od Ciebie - również jeśli to nic.

**Jeśli nie znasz Solany.** To nie jest wyzwanie tylko dla osób z doświadczeniem on-chain. Nasi mentorzy będą dostępni przez cały hackathon i pomogą przejść od pierwszego uruchomienia środowiska do działającego prototypu. Jeśli chcesz zacząć wcześniej, odezwij się do nas przed wydarzeniem - podeślemy materiały i pomożemy postawić środowisko, żeby nie tracić na to czasu w sobotę rano.

### 10. Kontakt

Jesteśmy dostępni przez cały hackathon.

- **Stoisko Superteam Poland** - najszybsza droga do odpowiedzi.
- **Telegram:** @matzayonc, @matjanisz - również przed wydarzeniem, jeśli chcesz postawić środowisko wcześniej.
- **Mailowo:** pl@superteam.fun
- **Nasze kanały:** linktr.ee/superteampoland

Nie ma głupich pytań - jeśli podchodzisz do czegoś on-chain pierwszy raz, powiedz wprost, dobierzemy pomoc do poziomu.
