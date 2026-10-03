# HubMI.pl — Małopolska Social Innovation Hub tool
**Version 1.0.1** · HackYeah 2026 knowledge base · 2026-10-03 · Track: Partner Task — Województwo Małopolskie (UMWM) / ROPS Kraków

---

## AI READING INSTRUCTION

Read `[SPEC]` blocks for authoritative facts.
Read `[NOTE]` only if additional context is needed.
`[?]` blocks are unverified or conflicting between sources — treat with lower confidence.
Common rules for all tasks: `../README.md` §3. This file lists only task-specific facts and deviations.
Exact wording: `../rules/Partner Task [UMWM] - HubMi.pl/<file>.md`.

---

## 1. Snapshot
**[SPEC]**
| Field | Value |
|---|---|
| Track | Partner Task (competition „HubMI.pl”) |
| Partner / organizer | Initiator: Województwo Małopolskie (Host Region HackYeah 2026); challenge owner: Regionalny Ośrodek Polityki Społecznej w Krakowie (ROPS Kraków); legal organizer & prize payer: Proidea Sp. z o.o. (common details) |
| Prize | 1st PLN 6 000 · 2nd PLN 5 000 · 3rd PLN 4 000; max 3 laureates; reduced by due taxes/contributions/fees |
| Team size | 1–6 (common); each participant natural person, 18+ on start day, full legal capacity |
| Work window | 3 Oct 2026 11:00 → 4 Oct 2026 11:00 (max 24 h); on-site only, Tauron Arena Kraków, ul. Stanisława Lema 7, 31-571 |
| Submission platform | HackTribe — https://hackyeah2026.hacktribe.co/ |
| Language | Polish (submission and pitch to Jury) |
| Evaluation | Jury mainly of Województwo Małopolskie reps + Organizer delegates; each criterion scored 1–10, weighted average |
| Min score | 50% of max possible score to become laureate |
| IP / licence | Full transfer of proprietary copyrights to Proidea (then to Województwo Małopolskie) upon prize payment; agreement mandatory |
| Results | 4 Oct 2026 at closing ceremony (~17:45) and on official event messenger |
| Contact | ROPS mentors at the ROPS info stand during the hackathon; organizer biuro@proidea.org.pl |

## 2. Challenge
**[SPEC]**
- Design, name and prototype an AI-based interactive platform: the „digital heart” of the Małopolska Social Innovation Hub (Małopolski Hub Innowacji Społecznych).
- Purpose: automate Hub processes, match social problems with existing/new solutions, build cooperation between residents, local governments (JST) and organisations; support finding, developing, testing and disseminating social innovations.
- Modules (participants may rename them, design UI and logic):

| # | Module | Status | Function |
|---|---|---|---|
| I | Social matchmaking (Matchmaking społeczny) | **Mandatory** | User describes problem → system finds similar cases/info and proposes ready solutions/social innovations |
| II | Knowledge store (Zasobnik wiedzy) | Optional | Presents ROPS resources: Małopolska social challenges (reports, Social Challenges Map / Mapa Wyzwań Społecznych), Social Innovation Library (Biblioteka Innowacji Społecznych, incl. videos), educational materials; fast data updates; accessible, creative presentation; aggregates needs data into areas/trends — admin-only view |
| III | Idea creator (Kreator pomysłów) | Optional | Always: idea „flashcard” (fiszka: short description, essence, target group, stage). Time-limited (during grant calls): application generator adapted to each call. Access to Social Innovation Canvas boards. Welcome: AI Innovation Creator Assistant (helps build/develop idea, suggests unusual solutions, visualises e.g. an innovative object) |
| IV | Innovation tester (Tester innowacji) | Optional | Sign up for tests, rate solutions, give feedback, propose improvements |
| V | Active communication platform | Optional | Direct dialogue ROPS ↔ users, quick questions, mentor support, cross-sector partnerships |
| VI | Admin panel | Optional | Fast modification, verification and publishing of knowledge |
| VII | Innovation Middleman (Middleman Innowacji) | Optional | AI assistant adapting an innovation into a service form per requesting institution's needs |

- End users: residents & NGOs (report ideas/problems; need simple UI, clear process); JST (diagnose challenges, use catalogue of ready innovations); ROPS Kraków staff (admins/coordinators); sector experts (consult innovators, advise JST; need fast feedback/communication).

**[NOTE]**
ROPS Kraków is a regional-government social-policy institution, ~10 years as regional innovation incubator, ~200 social innovations in portfolio. Regional challenges: ageing, mental-health crisis, loneliness, digital exclusion, limited access to social services, need for cross-sector coordination, settlement change (depopulation vs growth around Kraków). Winning prototype may become the Hub's foundation; ROPS plans further work, integration with regional innovation-leader network and use for implementation grants.

## 3. Requirements & Constraints
**[SPEC]**
- Must: functional MVP prototype with key modules; social matchmaking obligatory; each extra module scores additionally.
- Must: at least UX/UI mock-ups.
- Accessibility: target WCAG 2.1 level AA; usable by seniors and people with disabilities.
- Scalability: data for the whole voivodeship, many concurrent users; extensible.
- Integration & automation: ultimately work with other Hub systems (e.g. grant database); automate notifications about new ideas / grant-call changes.
- Data security to be considered.
- Must NOT use real personal data or sensitive data from ROPS-provided materials.
- No equipment, hardware, tech support or repair provided by Województwo Małopolskie or Organizer.

## 4. Deliverables
**[SPEC]**
Required (Regulations §4.9): project title, team ID, project description, PDF presentation max 10 slides, MP4 video max 3 min. Optional: screenshots, code repo, demo links, graphics, other materials. Submit via HackTribe in Polish, by 4 Oct 2026 11:00; late submissions not assessed.

Required by CRITERIA §4 additionally: solution name and description; link to working demo and UX/UI mock-ups; estimated operating/maintenance cost and description of resources needed.

## 5. Judging Criteria
**[SPEC]**
| Criterion | Weight | What is assessed |
|---|---|---|
| Challenge fulfilment (Stopień spełnienia wyzwania) | 40% | Quality of key elements + number of extra functions; mandatory matchmaking = 10%, each further module +5% (CRITERIA only) |
| Implementation potential (Potencjał wdrożeniowy) | 20% | Readiness for deployment: practical use, scalability, flexibility, optimisation, cost-effectiveness, easy maintenance |
| Prototype accessibility & intuitiveness | 20% | Clear, easy UI for all target groups regardless of age/digital skills; WCAG 2.1 AA design |
| Bonus: interface appeal, creativity, quality | 10% | Novel, unconventional approach; visual appeal of UX/UI mock-ups |
| Bonus: quality of materials and MVP | 10% | How concept is communicated; quality of submitted materials |

Testing/validation focus (CRITERIA §6): intuitiveness for users of any age/digital skill; communication speed (how admin is notified of new idea, reply path to author); matching accuracy (suggests existing innovations from keywords in need description); ingenuity (new quality vs re-integrating existing portal features). Also: ease of reporting a problem, relevance of proposed solutions, quality of user communication, platform growth potential.

## 6. Resources & Support
**[SPEC]**
- Małopolska social challenges map + links to reports.
- Link to Social Innovation Library.
- Materials on ROPS Kraków experience.
- Social Innovation Canvas boards.
- Sample data for demonstrating MVP functions.
- Mentors on site (ROPS info stand).

## 7. Task-specific Rules
**[SPEC]**
- Timing: 11:00 → 11:00 (same as confirmed common window, README §3.2); task published on www.hackyeah.pl at 11:00 on start day; solving starts after official opening.
- Eligibility: Hackathon participants only; natural persons 18+ with full legal capacity. No baseline-style sponsor/jury-relative exclusion stated.
- Jury: elects chairperson; simple majority with all members present; tie → chairperson decides (also for ranking ties). Jury composition published on Hackathon website by start day. No two-phase mentor/pitch process described; pitch to Jury in Polish.
- Prize payment: conditional on (a) signing copyright-transfer agreement with Proidea, (b) providing tax/settlement data. Paid within 60 days of the agreement (unless agreement says otherwise). Team prize split proportionally per member, paid to each member's bank account.
- Exclusion: Województwo Małopolskie or Organizer may exclude for breach of Regulations/law; suspected crime reported to authorities. Withdrawal any time = loss of prize; breach found = loss of prize. Not liable if wrong data prevents payout.
- Cancellation/early end only for important reasons (force majeure, safety, technical failure). No appeal. Post-start changes only for important reason, without worsening prizes, criteria or IP rules. Disputes: amicable, else Województwo Małopolskie decides (binding). Precedence: agreement with Organizer > these Regulations > Hackathon rules.
- Personal data: controller Proidea; processed to run Hackathon/Competition, contact, prize settlement, legal duties; see Organizer privacy policy.
- No task-specific AI policy stated.

**[SPEC]** Copyright (Regulations §7) — deviates from baseline (rights ARE transferred):
- Laureates' solutions, fragments, elements, materials and documentation = Works (Polish Copyright Act of 4 Feb 1994).
- On prize payment Proidea acquires ownership of all copies (incl. source code) and media plus all proprietary copyrights, exclusive, unlimited in time/territory, with right to transfer further. Fields: reproduction/fixation, new versions/adaptations, marketing/lending/rental, computer memory & network/Internet availability, public dissemination/on-demand, radio/TV/cable/satellite broadcast, naming incl. trade names, marketing/promotion/education use, disposing of elaborations & licensing third parties, authorising dependent rights, foreign-language & accessibility versions, online video (excluding public TV broadcast of films).
- Source code: transfer covers modification, compilation, combination, testing, deployment, use; laureates must hand over source code.
- Laureate consents to changes/elaborations (rights to Organizer), transfers exclusive dependent rights without remuneration; authorises Organizer to decide first publication, authorship attribution or anonymity, and supervise use (transferable). No separate remuneration per field. Organizer may use Works from submission until acquisition; laureate guarantees this infringes no rights and causes no extra costs.
- Laureate undertakes: future transfer to Województwo Małopolskie of fields unknown at signing, free, for their independent part; not to exercise moral rights vs Organizer and Województwo Małopolskie (they may omit authors' names).
- Refusal by any team member to sign = resignation from prize; no claims.

**[SPEC]** Copyright-transfer agreement template (Umowa o przeniesienie praw autorskich), dated 04.10.2026, up to 6 co-creators (Twórcy) ↔ Proidea (Nabywca, represented by Jakub Kozioł, President):
- Declarations: co-authors with equal joint shares; Work made personally, unpublished (only shared for HackYeah evaluation), not a derivative of others' work, free of encumbrances/third-party rights; patent rights/priority not disposed of; no third-party IP infringement. Creators cover any costs/damages if declarations are untrue. Repository contents listed in agreement.
- Delivery: whole work zipped, sent within 24 h of signing; software also as readable, compilable source code on a data carrier with full list of tools/libraries needed to build; no encryption or access-hindering techniques.
- Transfer on prize payment: all fields known at signing — software per art. 74(4) (reproduction, translation/modification, distribution incl. sale/licensing/rental, public access, dependent rights); non-software per art. 50 (same list as Regulations §7.4). Exclusive right to authorise dependent rights; carrier ownership passes. Until payment: free non-exclusive licence for competition, evaluation, presentation, results publication, prize handling.
- Moral rights not exercised vs Acquirer and its successors (anonymous distribution allowed); Acquirer may first-publish; authorisations transferable by Organizer and Województwo Małopolskie.
- Prize claim arises on signing; amount stated „z podatkiem” (tax-inclusive); 10% flat income tax withheld (art. 30(1)(2) PIT Act); net amount per co-creator to their bank account; payment exhausts all claims.
- Confidentiality: processing/publication data, Acquirer's business info, agreement terms. Polish law; amendments in writing/electronic annex or void; severability; court of defendant's seat; 7 identical copies.

## 8. Conflicts & Open Questions
**[?]**
Deliverable format: Regulations §4.9 (PL and EN) require BOTH PDF (≤10 slides) AND MP4 video (≤3 min); CRITERIA §4 says PDF presentation OR video (≤3 min), plus demo link, mock-ups and maintenance-cost estimate not listed in Regulations.

**[?]**
PL vs EN Regulations §7.3: Polish says refusing participants have no claims against the Organizer nor Województwo Małopolskie; English mentions only Województwo Małopolskie.

**[?]**
PL vs EN §7.9: Polish lets authorisations pass to entities acquiring the economic rights or obtaining the right to use the Works; English says entities acquiring economic rights „from the Organizer” (no right-to-use clause). PL §7.10 is split into EN §7.10–7.11, so EN §7.12 = PL §7.11 (numbering only).

**[?]**
Prize tax: Regulations say prizes reduced by due taxes/contributions; agreement says amount is tax-inclusive with 10% flat tax withheld; net per-person amounts left blank.

**[?]**
Payment term: 60 days from signing the agreement here vs baseline 90 days from results. Prize payer is Proidea, but rights pass onward to Województwo Małopolskie.

**[?]**
CRITERIA bonus scheme (10% + 5% per extra module) with 6 optional modules gives exactly 40% but how it combines with the 1–10 scale in Regulations §5.3 is unspecified.

## 9. Sources
**[SPEC]**
- [CRITERIA Wojewodztwo Malopolskie HUBMI.md](../rules/Partner%20Task%20%5BUMWM%5D%20-%20HubMi.pl/CRITERIA%20Wojewodztwo%20Malopolskie%20HUBMI.md) — Polish challenge template: context, 7 modules, expected result, formal/technical requirements, validation, resources, weighted criteria, contact.
- [RULES Wojewodztwo Malopolskie HUBMI.md](../rules/Partner%20Task%20%5BUMWM%5D%20-%20HubMi.pl/RULES%20Wojewodztwo%20Malopolskie%20HUBMI.md) — Polish Regulamin, Polish copyright-transfer agreement template, English Regulations, duplicate of the agreement.

---

## Changelog
- 1.0.0 · 2026-10-03 · Initial summary from verbatim sources.
- 1.0.1 · 2026-10-03 · Work window aligned with team-confirmed common window.
