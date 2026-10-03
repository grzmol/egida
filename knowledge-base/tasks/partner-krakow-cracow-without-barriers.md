# Cracow without barriers („Kraków bez barier”)
**Version 1.0.0** · HackYeah 2026 knowledge base · 2026-10-03 · Track: Partner Task — Miasto Kraków (Gmina Miejska Kraków)

---

## AI READING INSTRUCTION

Read `[SPEC]` blocks for authoritative facts.
Read `[NOTE]` only if additional context is needed.
`[?]` blocks are unverified or conflicting between sources — treat with lower confidence.
Common rules for all tasks: `../README.md` §3. This file lists only task-specific facts and deviations.
Exact wording: `../rules/Partner Task [Miasto Kraków] - Cracow without barriers/<file>.md`.

---

## 1. Snapshot
**[SPEC]**
| Field | Value |
|---|---|
| Track | Partner Task — Miasto Kraków |
| Prize sponsor | Proidea Sp. z o.o., under the auspices of Gmina Miejska Kraków; paid by Proidea (details common) |
| Prize | 5 000 PLN incl. tax (single prize) |
| Payout | within 180 days of results announcement |
| Team size | individual or team of up to 6 |
| Work window | start no earlier than 11:00 Oct 3; submit no later than 11:00 Oct 4 (see §8) |
| Submission platform | HackTribe |
| Language | Polish (RULES) |
| Evaluation | Jury of ≥2 members; simple majority; tie → Chairperson (elected by panel before competition) |
| Min score | 50% of points |
| IP | author's proprietary copyrights to the awarded solution TRANSFERRED after prize acceptance (Attachment 1 agreement, see §7) |
| Jury list | on HackYeah website by Oct 3 |
| Contact | Bartłomiej Węglarz, Karolina Grzanka, Michał Janaś — mentor zone and Discord |

## 2. Challenge
**[SPEC]**
- Design and build a prototype tool letting residents and tourists get information and assess accessibility of chosen places or routes according to individual needs; also a source of information on accessibility of the city's offer.
- Must not be limited to "accessible/inaccessible": show detailed barriers and amenities so the user decides alone (stairs, thresholds, ramps, lifts, entrance width, surface type, toilet, rest places).
- Prototype scoped to a chosen user group / need type (e.g. wheelchair users, parents with prams).
- Must show potential for further development, commercialisation and scaling to other cities/sectors.
**[NOTE]**
Data may come from open sources, OpenStreetMap, facility owners, user reports. Target adopters/commercial directions: other cities, facility owners, hotels, event organisers, property managers, booking systems, map and tourist-app providers. Business potential carries special weight in evaluation; aim is local and national market.

## 3. Requirements & Constraints
**[SPEC]**
- Data as current as possible; each accessibility item must allow indicating source, date obtained/last confirmed, and reliability status.
- User-reported/unverified data clearly distinguished from confirmed; unconfirmed info must not be presented as a formal accessibility guarantee; missing data must not be shown as confirmation of accessibility.
- Provide a way to correct wrong/outdated data.
- No manual database maintenance by the City; no access to internal systems of UMK or MJO / city organisational units.
- Any technical form (web/mobile etc.) as long as the main scenario is demoable: search a place/route → show accessibility info relevant to the chosen group.
- Architecture separates data acquisition/updating from presentation; describe main components, data flow, how to add sources, place categories, geographic areas.
- Use public data/services per provider terms; for city data name concrete datasets/public APIs, retrieval method, update frequency, behaviour when source unavailable. Publication online ≠ permission for automatic download or commercial use; per source state origin, terms of use, currency, verification method.
- Digital accessibility: WCAG 2.2 AA as development goal; in prototype ensure keyboard and screen-reader support, readability, contrast, text alternative for map-only info; list available features vs. remaining work.
- Propose launch and maintenance outside UMK infrastructure: entity responsible for hosting, updates, security, report handling, costs. Prototype need not run permanently after hackathon.
- Data protection & security: scope of user data collected, protection of reports/accounts (if any), secure connections; should not require disability information when barrier/amenity preferences suffice.
- Deployable by others: list external-provider dependencies, licences of data/components, portability to other infrastructure, how to add another city. Technology choice free.

## 4. Deliverables
**[SPEC]**
Required (KRYTERIA):
- solution description + problem solved
- prototype or demo
- target group and usage
- data sources + how currency/reliability is assessed
- business model + development potential proposal
- PDF presentation, max 10 slides
- video of the project working, max 3 min, in an accessible open repository (RULES: mp4)
Required (RULES): project title, team ID, project description, PDF ≤10 slides, mp4 video ≤3 min.
Optional: code repo, screenshots, demo link, graphics, other materials.

Live demo during presentation must:
- define chosen user group's needs, check ≥1 place/route, show concrete barriers/amenities;
- show data source, when obtained/confirmed, how incomplete/outdated/unverified data is marked; sample data clearly labelled;
- show ≥1 case of conflicting/incomplete data or unavailable source and what the user sees;
- basic accessibility check of main scenario (keyboard, screen reader, contrast, map info as text), plus known limits and fix plan;
- short prototype→service plan: product owner entity, data acquisition/verification model, hosting/maintenance funding, roadmap, conditions for launch in another city.

## 5. Judging Criteria
**[SPEC]**
KRYTERIA (proposed, Polish source):
| Criterion | Weight |
|---|---|
| Relation to challenge & usefulness for chosen user group, incl. ease of use | 25% |
| Prototype quality & completeness | 20% |
| Data reliability, presentation and updating | 15% |
| Implementation potential & scalability | 20% |
| Business model, commercialisation & market potential | 20% |

RULES:
| Criterion | Weight | What is assessed |
|---|---|---|
| Idea | 30% | creativity, extent problem solved |
| Technical aspects | 30% | technologies, interaction archiving, algorithms, code quality |
| (Project) Design | 20% | architecture, scalability, production deployability |
| Relation to category | 10% | compliance with task description |
| WOW! factor | 10% | originality, extra features beyond requirements |

## 6. Resources & Support
**[SPEC]**
- Portal Otwarte Dane Miasta Krakowa — city datasets (JSON, CSV, XLSX, APIs per resource): otwartedane.um.krakow.pl
- MSIP (Miejski System Informacji Przestrzennej) — Kraków spatial data catalogue; downloads or WMS/WFS; check scope/terms per resource: msip.krakow.pl
- dane.gov.pl — national public data catalogue (supplementary, other cities)
- OpenStreetMap — objects and road network for map/routing; licence terms and attribution required: openstreetmap.org
- Other open sources, facility-owner info, user reports allowed (with origin/terms/verification stated).

## 7. Task-specific Rules
**[SPEC]**
Deviations from README §3: prize 5 000 PLN; payout 180 days; window 11:00–11:00; Polish submission; mp4 video ≤3 min required; "team ID" instead of team name/member list; Jury ≥2, majority vote, Chairperson decides ties; jury list on HackYeah website by Oct 3; copyrights transferred (below). No task-specific AI rules.

Attachment 1 — copyright transfer agreement (Umowa o przeniesienie praw autorskich), signed by each team member:
- Parties: Acquirer (Nabywca) Gmina Miejska Kraków, pl. Wszystkich Świętych 3-4, 31-004 Kraków, NIP 676-101-37-17, REGON 351554353, represented by Paweł Schmidt, Director of Centrum Obsługi Informatycznej (power of attorney no. 100/2025 of 20.01.2025); Authors/Transferors (Autorzy/Przekazujący) bound individually and jointly.
- Authors warrant: sole authorship and exclusive unlimited economic rights, no licences granted, rights not seized, no third-party IP infringement or legal defects; they defend/indemnify the Acquirer at own cost against third-party claims.
- Transfer of economic rights + right to authorise derivative rights: unconditional, free of charge, effective on signing and sharing the GitLab repository (virtual source-code carrier); ownership of the carrier also passes. Acquirer may exercise and authorise others (incl. its units) to exercise derivative rights.
- Remuneration: none from the Acquirer; transfer is in connection with the 5 000,00 PLN prize from Proidea under GMK auspices.
- Fields of exploitation (no limit of time, territory, copies), items a–r: use for building mobile/web apps; fixation/reproduction by any technique; distribution incl. Internet/on-demand; trade in original/copies (sale, lending, rental); install/use by unlimited users and workstations; use (run, display, data entry/edit/export/import, print); load into memory; reports; translation/adaptation/changes; educational/training use; DB queries with Acquirer's tools; modification by Acquirer or third parties; third-party interface use; source-code reproduction, decompilation, disassembly, reverse engineering; licences/sublicences to third parties for maintenance/support/development.
- Handover: within 7 days of signing, give Acquirer (or its designated employee) owner role on GitLab repo with complete runnable source; joint check by compiling and running; confirmed by signed handover record (Załącznik nr 1 — Protokół odbioru kodu źródłowego Utworu: commission names, agreement no./date, code delivered, accepted without reservations / with remarks).
- Other: confidentiality of Acquirer's confidential info; agreement is public under public-finance and access-to-public-information acts; amendments only in writing as annex (else void); assignment of claims needs written consent of the Mayor of Kraków; Polish law, Polish courts (court for Acquirer's seat); severability; date = last signature; 2 copies, handwritten signatures, written form under pain of nullity.

Personal-data notice (RODO, art. 13):
- Controller: Prezydent Miasta Krakowa, pl. Wszystkich Świętych 3-4, 31-004 Kraków; it.umk@um.krakow.pl; DPO iod@um.krakow.pl.
- Purpose: conclude, perform, settle the agreement; GMK agreement register (register "Umowy Centrum Obsługi Informatycznej").
- Retention: until end of agreement, then 50 years (if social-insurance applies) or 10 years otherwise.
- Rights: access, rectification, restriction, portability; complaint to President of UODO.
- Providing data mandatory; otherwise no agreement.
- Legal bases: Civil Code; art. 6(1)(b) GDPR; PIT, accounting, VAT, public finance, social insurance acts; art. 6(1)(f) GDPR for claims.

## 8. Conflicts & Open Questions
**[?]**
Agreement §1 names the work as prototype app „Krakowskie cyfrowe centrum wolontariatu”, not this task — likely a template carry-over.
**[?]**
Criteria differ completely: KRYTERIA (25/20/15/20/20, usefulness/prototype/data/scaling/business) vs RULES (Idea 30, Technical 30, Design 20, Relation 10, WOW 10). KRYTERIA calls them "proposed".
**[?]**
Rights recipient: RULES §14 says rights go to the prize sponsor (Proidea) and agreement is with the event organizer; Attachment 1 makes Gmina Miejska Kraków the Acquirer.
**[?]**
Work window in RULES is 11:00 Oct 3 – 11:00 Oct 4, vs common 11:00 PM; KRYTERIA silent.
**[?]**
Video: RULES "mp4 video"; KRYTERIA "film in an accessible open repository". Both say max 3 min.

## 9. Sources
- [KRYTERIA Kraków Bez Barier.md](../rules/Partner%20Task%20%5BMiasto%20Krak%C3%B3w%5D%20-%20Cracow%20without%20barriers/KRYTERIA%20Krak%C3%B3w%20Bez%20Barier.md) — Polish challenge brief: context, expected result, formal/technical requirements, validation, resources, criteria, contacts.
- [RULES Cracow Without Barriers.md](../rules/Partner%20Task%20%5BMiasto%20Krak%C3%B3w%5D%20-%20Cracow%20without%20barriers/RULES%20Cracow%20Without%20Barriers.md) — English T&C + Polish copyright-transfer agreement, handover record template, RODO notice.

---

## Changelog
- 1.0.0 · 2026-10-03 · Initial summary from verbatim sources.
