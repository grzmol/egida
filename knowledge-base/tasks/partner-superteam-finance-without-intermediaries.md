# Finance Without Intermediaries („Finanse bez pośrednika”)
**Version 1.0.0** · HackYeah 2026 knowledge base · 2026-10-03 · Track: Partner Task — SuperTeam (Superteam Poland)

---

## AI READING INSTRUCTION

Read `[SPEC]` blocks for authoritative facts.
Read `[NOTE]` only if additional context is needed.
`[?]` blocks are unverified or conflicting between sources — treat with lower confidence.
Common rules for all tasks: `../README.md` §3. This file lists only task-specific facts and deviations.
Exact wording: `../rules/Partner Task [SuperTeam] - Finance without intermediaries/<file>.md`.

---

## 1. Snapshot
**[SPEC]**
| Field | Value |
|---|---|
| Track | Partner Task — SuperTeam |
| Prize sponsor | SUPERTEAM Spółka z o.o., Warsaw, ul. Kaleńska 7/7, 04-367, NIP 1133152620 (replaces Proidea) |
| Prize | 1st PLN 1,500 · 2nd PLN 1,000 · 3rd PLN 500 (incl. tax); pool stated as USD 3,000 — see §8 |
| Team size | common (1–6) |
| Work window | common (Oct 3 11:00 PM – Oct 4 11:00 PM) |
| Submission platform | HackTribe (RULES) |
| Language | common (English or Polish) |
| Evaluation | common 2 phases; final = live demo to judges |
| Min score | common (50% "in 1 step") |
| Network | Solana (devnet sufficient) |
| IP | Copyrights not transferred; repo must be public during evaluation |
| Contact | Superteam Poland booth; Telegram @matzayonc, @matjanisz; pl@superteam.fun; linktr.ee/superteampoland |

## 2. Challenge
**[SPEC]**
- Design and build a solution on Solana that removes the need for trust from a financial transaction.
- Pick a financial relationship that today requires a trusted intermediary (other party and/or intermediary); redesign so terms are in an on-chain program, execute automatically, identically for every participant, with no unilateral change and no enforcer needed.
- Open domain/form: specific market problem or general-purpose tool. Quality of reasoning valued as much as code.
**[NOTE]**
Organizer: Superteam, non-profit supporting builders on Solana; Superteam Poland is the Polish community. Example patterns: lending protocols (main example), escrow, freelancer–client settlements, fundraisers with conditional refunds, revenue sharing, parametric insurance, loyalty programs, B2B settlements. Solana: sub-second confirmation, fraction-of-a-cent fees → enables micropayments, per-second settlements, multi-party revenue splits.

## 3. Requirements & Constraints
**[SPEC]**
- Working app (not concept/mockup), launchable and clickable; not production-ready. User goes through full flow and sees result.
- Complete when: ≥1 full use case from user input to completed transaction; demonstrates the moment the intermediary is no longer needed; works live during presentation (not only recording).
- Rough UI acceptable; working simple app preferred over polished design.
- Name the target user explicitly (e.g. "freelancers invoicing foreign clients"); determines UI language and how much tech is hidden. Dev tools and non-crypto apps valued equally if choice is deliberate.
- Must run on Solana; devnet sufficient; no mainnet or real funds expected; test SOL from public faucet.
- Logic replacing the intermediary MUST live in the on-chain program (backend-enforced terms = you became the intermediary).
- Free stack: on-chain — Anchor, native Rust, Pinocchio, Steel, anything that compiles; frontend — any framework/language (typically @solana/kit or @solana/web3.js, Wallet Adapter); may use SPL Token, Token-2022, oracles (Pyth, Switchboard), existing protocols/SDKs.

## 4. Deliverables
**[SPEC]**
| Required (CRITERIA) | Optional |
|---|---|
| Project title + detailed description incl. design rationale | Screenshots |
| PDF presentation, max 10 slides | Demo links |
| Video, publicly accessible link, max 3 min | Graphics / other materials |
| Code repository (public during evaluation; clear README of what is where) | |
- Design rationale: which financial relationship was redesigned, who the intermediary was, what specifically changes once removed.
- RULES additionally require (common): team name, team members list.

## 5. Judging Criteria
**[SPEC]**
| Criterion | Weight |
|---|---|
| Relevance to the challenge | 30% |
| Completeness and functionality | 25% |
| Idea and choice of problem | 20% |
| Implementation potential | 15% |
| Originality | 10% |
- Live demo: walk ≥1 full scenario (arrive, connect wallet, perform operation, see result); show confirmed on-chain transaction (Solana Explorer / Solscan).
- Prepare: wallets funded with test SOL, accounts in right state, ideally two wallets for two-party scenarios; have a backup recording (faucet/internet failure does not disqualify).
- Judges ask: where in code the intermediary disappears / which part enforces terms; what happens if a party disappears mid-transaction (where funds are, who recovers them); who has which permissions, can the author change anything after deployment; why blockchain not a regular database (will definitely be asked); next steps with another week.
- Not evaluated: attack resistance, audit, design quality, test coverage, flawlessness. If something breaks, explain what and why; awareness of limitations valued.
- Repo checked before and after presentation: whether on-chain program does what the demo shows.

## 6. Resources & Support
**[SPEC]**
- Bootcamp „Od Zera do Blockchain Developera” (From Zero to Blockchain Developer): slides, handbook, review questions — matzayonc.github.io/stpl-bootcamp (theory); github.com/matzayonc/solana-live-course-2026 (examples + dev container for VS Code / GitHub Codespaces).
- Solana docs (Polish available): solana.com/pl/docs — browser quickstart, `npx create-solana-dapp`.
- Anchor: anchor-lang.com/docs, book.anchor-lang.com.
- Solana Playground: compile/deploy from browser. On site: Playground, devnet faucet, Solana Explorer.
- Mentors at Superteam Poland booth throughout the hackathon; pre-event setup help via Telegram.
**[NOTE]**
Post-hackathon: selected projects invited to continue in community (idea refinement, co-founders, users, Solana ecosystem grant applications); grant advice (no funding guarantee); jobs and paid bounties for community members.

## 7. Task-specific Rules
**[SPEC]**
- Prize sponsor/promisor (art. 921 § 3 Civil Code): SUPERTEAM Spółka z o.o. (not Proidea); its employees excluded.
- Prizes: 3 places (see §1), not the 8 000 PLN open-task default.
- Criteria weights differ from open-task default (see §5).
- Extra required deliverables vs baseline: ≤3 min video, code repository, design rationale.
- Code stays yours; Superteam claims no rights; only asks repo public during evaluation.
- RULES contain no AI-policy or existing-materials clause (baseline applies per README).

## 8. Conflicts & Open Questions
**[?]**
RULES §7: "total prize pool ... USD 3,000 (including tax)" but places listed as PLN 1,500 / 1,000 / 500 (sum PLN 3,000). Currency of the pool is inconsistent.
**[?]**
Required items differ: RULES require only title, team name, members, description, PDF (repo/demo optional); CRITERIA require video (≤3 min) and code repository. Polish CRITERIA say video placed "w dostępnym, otwartym repozytorium" (open repository) vs English "publicly accessible location".

## 9. Sources
- [CRITERIA Finance Without Intermediaries PL_ENG.md](../rules/Partner%20Task%20%5BSuperTeam%5D%20-%20Finance%20without%20intermediaries/CRITERIA%20Finance%20Without%20Intermediaries%20PL_ENG.md) — bilingual EN/PL challenge brief: context, outcome, submission, tech, demo, resources, criteria, contact.
- [RULES Finance Without Intermediaries.md](../rules/Partner%20Task%20%5BSuperTeam%5D%20-%20Finance%20without%20intermediaries/RULES%20Finance%20Without%20Intermediaries.md) — competition T&C: sponsor, eligibility, prizes, evaluation, criteria, IP.

---

## Changelog
- 1.0.0 · 2026-10-03 · Initial summary from verbatim sources.
