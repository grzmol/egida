# HackYeah 2026 — Task Knowledge Base
**Version 1.0.0** · HackYeah 2026 knowledge base · 2026-10-03 · 10 tasks (5 Open, 5 Partner) · Language: English summaries, original-language sources

---

## AI READING INSTRUCTION

Read `[SPEC]` blocks for authoritative facts.
Read `[NOTE]` only if additional context is needed.
`[?]` blocks are unverified or conflicting between sources — treat with lower confidence and say so in answers.

Navigation (token-efficient order):
1. This file: §2 comparison, §3 common rules, §4 criteria, §5 cross-task conflicts, §6 query routing.
2. `tasks/<slug>.md`: one HADS summary per task; lists ONLY facts that deviate from or add to §3.
3. `rules/<task folder>/*.md`: verbatim full text (source of truth). Open only when exact wording, legal clauses, or a quote is needed.

Precedence when facts disagree: verbatim `rules/` > `tasks/` summary > this index. Partner-specific rules override §3 for that task.

---

## 1. File Map

**[SPEC]**
| Slug (`tasks/<slug>.md`) | Track | Verbatim sources (`rules/…/`) |
|---|---|---|
| `open-artificial-intelligence` | Open | `Open Task - ARTIFICIAL INTELLIGENCE/` Details, Rules |
| `open-defence` | Open | `Open Task - Defence/` Details, Rules |
| `open-impact-her` | Open | `Open Task - IMPACT HER/` Details, Rules |
| `open-smart-city` | Open | `Open Task - SMART CITY/` Details, Rules |
| `open-sport-healthcare` | Open | `Open Task - SPORT & HEALTHCARE/` Details, Rules |
| `partner-goldman-sachs-ai-control-layer` | Partner — Goldman Sachs | `Partner Task [Goldman Sachs] - AI Control Layer/` CRITERIA, RULES |
| `partner-huawei-imagine-whats-next` | Partner — Huawei | `Partner Task [Huawei] - Imagine what_s  next/` (two spaces before `next`) CRITERIA, RULES |
| `partner-krakow-cracow-without-barriers` | Partner — Miasto Kraków | `Partner Task [Miasto Kraków] - Cracow without barriers/` KRYTERIA (PL), RULES (EN + PL agreement) |
| `partner-superteam-finance-without-intermediaries` | Partner — SuperTeam | `Partner Task [SuperTeam] - Finance without intermediaries/` CRITERIA (PL+EN), RULES |
| `partner-umwm-hubmi` | Partner — UMWM (Województwo Małopolskie) | `Partner Task [UMWM] - HubMi.pl/` CRITERIA (PL), RULES (PL + EN + PL agreement) |

**[NOTE]**
Details/CRITERIA files describe the challenge and judging; Rules/RULES files are the legal terms. Open tasks and the Goldman Sachs / SuperTeam RULES use one shared T&C template (§3); Huawei, Kraków and HubMi have their own legal terms.

---

## 2. Task Comparison

**[SPEC]**
| Task | One-line challenge | Prize (incl. tax unless noted) | Payout | Work window | Language | IP to sponsor |
|---|---|---|---|---|---|---|
| ARTIFICIAL INTELLIGENCE | Solution where AI plays a meaningful role for a specific user need | 8 000 PLN | 90 d | Oct 3 11:00 PM → Oct 4 11:00 PM | EN/PL | No |
| Defence | Tool that prevents threats, detects them earlier or reduces their consequences | 8 000 PLN | 90 d | same | EN/PL | No |
| ImpactHer: Technology for Real Change | Tech solution for a real challenge affecting women | 8 000 PLN | 90 d | same | EN/PL | No |
| SMART CITY | Tool for a concrete problem of a city or its residents | 8 000 PLN | 90 d | same | EN/PL | No |
| SPORT & HEALTHCARE | Tool helping a user group take an active role in health, activity, wellbeing | 8 000 PLN | 90 d | same | EN/PL | No |
| AI Control Layer (Goldman Sachs) | Gateway/proxy/middleware governing agentic-AI traffic: hybrid guardrails, budgets, reporting | 15 000 PLN: 6 000 / 5 000 / 4 000 | 90 d | same | EN/PL | No |
| Imagine What's Next (Huawei) | System feature or app for OpenHarmony-based mobile device (API 20+) | 25 000 PLN: 12 000 / 8 000 / 5 000 (reduced by taxes/fees) | 60 d | HackYeah official schedule | EN only | No; non-exclusive 3-yr licences to Huawei (+PROIDEA promo) |
| Cracow without barriers (Kraków) | Accessibility info for places/routes per individual needs, with data reliability | 5 000 PLN (single) | 180 d | Oct 3 11:00 → Oct 4 11:00 | PL | **Yes** — to Gmina Miejska Kraków (agreement) |
| Finance Without Intermediaries (SuperTeam) | Solana program removing a trusted intermediary from a financial transaction | 1 500 / 1 000 / 500 PLN (pool stated "USD 3,000") | 90 d | Oct 3 11:00 PM → Oct 4 11:00 PM | EN/PL | No; repo public during evaluation |
| HubMI.pl (UMWM / ROPS Kraków) | AI platform for Małopolska Social Innovation Hub; mandatory social-matchmaking module | 6 000 / 5 000 / 4 000 PLN (reduced by taxes) | 60 d from agreement | Oct 3 11:00 → Oct 4 11:00, on-site | PL | **Yes** — to Proidea, then Województwo Małopolskie |

**[SPEC]**
Required deliverables beyond the common set (§3.3):
| Task | Extra required deliverables / hard constraints |
|---|---|
| AI Control Layer | Control layer + architecture diagram; policy config (strictness levels, budgets); dashboard; executable test suite (positive + negative); telemetry. No paid services provided; local models (e.g. Ollama) |
| Imagine What's Next | Public repo; reproducible build/install/launch instructions; working `.hap`; recorded demo; architecture description; `AI_WORKFLOW.md` (incl. main prompts) if AI used; AI integration docs if AI feature. Target HarmonyOS/OpenHarmony/Oniro, API 20+ |
| Cracow without barriers | mp4 video ≤3 min; team ID; data sources + reliability assessment; business model; live demo incl. conflicting/missing-data case and accessibility check; WCAG 2.2 AA goal |
| Finance Without Intermediaries | Video ≤3 min (public); public code repo with README; design rationale; on-chain intermediary logic on Solana (devnet OK); live demo with confirmed on-chain transaction |
| HubMI.pl | MP4 video ≤3 min; team ID; mandatory matchmaking module; WCAG 2.1 AA; age 18+; signed copyright-transfer agreement; source-code handover |

---

## 3. Common Rules

Applies to all Open Tasks and, unless their task file says otherwise, to Partner Tasks. Source: shared T&C template (`rules/Open Task - */Rules - *.md`, items 1–15) and Open Task Details.

### 3.1 Organizer and eligibility

**[SPEC]**
- Event: HackYeah. Competition terms are an annex to the general HackYeah T&C.
- Prize sponsor ("promising the prize", art. 921 § 3 Civil Code): Proidea Sp. z o.o., ul. Zakopiańska 9, 30-418 Kraków; NIP 6793088842; REGON 122769022; KRS 0000448243; biuro@proidea.org.pl.
- Excluded: persons related/affined to the competition jury members, and employees of the prize sponsor.
- Task details presented at competition start.

### 3.2 Timing

**[SPEC]**
- Start solving no earlier than 11:00 PM Oct 3; submit no later than 11:00 PM Oct 4.
- Changes after the deadline are not considered.
- Jury members posted on Discord (HackYeah communication platform) by Oct 4.

### 3.3 Team and submission

**[SPEC]**
- Individuals or teams of 1–6.
- Required: project title; team name; team members list (1–6); project description; PDF presentation, max 10 slides.
- Optional: snapshots, code repository, demo links, graphic materials, other materials (incl. those suggested in task details).
- Language: English or Polish.
- Platform: HackTribe (Rules). HubMI rules give the URL https://hackyeah2026.hacktribe.co/.

### 3.4 Evaluation

**[SPEC]**
- Phase 1: submitted projects evaluated on HackTribe by a task commission of ≥3 Mentors.
- Phase 2: finalists from phase 1 pitch live to the Jury. Commission and Jury may overlap.
- Jury elects a chairman. Tie: "the Jury's vote shall decide in both phases".
- Award requires ≥50% of points "in 1 step". Decisions final, no appeal.

### 3.5 Default Open Task criteria

**[SPEC]**
| Criterion | Weight | What is assessed |
|---|---|---|
| Idea & Innovation | 30% | Uniqueness, creativity, inventiveness of concept |
| Relation to Category | 20% | Fit with the task's category and objectives |
| Practical Applicability / Usability | 20% | Real-world utility, ease of use, UX |
| Design | 20% | Visual appeal: UI, graphics, look and feel |
| Completeness & Implementation Value | 10% | Completeness, technical robustness, readiness for real deployment |

### 3.6 Prizes and IP

**[SPEC]**
- Open-task prize: 8 000 PLN incl. tax.
- Prizes issued within 90 days of results unless a task states otherwise.
- Author's proprietary copyrights to the awarded solution are NOT transferred to the sponsor.

### 3.7 Existing resources and AI policy

**[SPEC]**
- Existing repositories, materials, resources allowed if properly cited.
- AI tools allowed at every stage (concept, research, coding, debugging, design, docs).
- Team is fully responsible for the solution (originality, functionality, security, licensing, legal compliance).
- Disclose significant use of AI tools and external models, APIs, datasets, libraries. Prompt history and AI-generated share NOT required.
- Jury judges actual technical work done at HackYeah: complexity, architecture, integrations, implementation approach, functionality, team understanding — not lines of code.
- Team must explain and defend technical decisions, incl. AI-generated parts; unexplainable AI-built features may lower the technical score.
- Clearly separate pre-existing work from hackathon work; OSS libraries, frameworks, APIs, models allowed per licences.
- Possible disqualification: plagiarism, unauthorised third-party IP, misleading jury/organiser about scope, hiding significant pre-existing parts.
- Partner-specific AI rules override this policy for their task.

---

## 4. Judging Criteria by Task

**[SPEC]**
| Task | Criteria (weight) |
|---|---|
| All 5 Open Tasks | Default §3.5: Idea & Innovation 30 · Relation to Category 20 · Practical Applicability/Usability 20 · Design 20 · Completeness & Implementation Value 10 |
| AI Control Layer | Robustness & Guardrails 30 · Architecture & Performance Efficiency 20 · Security Reporting 20 · Self-Testing Suite 15 (RULES: 20) · Practical Implementability & Scalability 15 (RULES: 10) |
| Imagine What's Next | Originality 20 · Demonstrated usefulness 20 · Technical execution 20 · Platform capabilities 20 · Demo quality 10 · Reproducibility & workflow transparency 10; each scored 1–10 |
| Cracow without barriers | KRYTERIA: usefulness for user group 25 · prototype quality 20 · data reliability 15 · implementation & scalability 20 · business model 20. RULES: Idea 30 · Technical 30 · Design 20 · Relation 10 · WOW 10 |
| Finance Without Intermediaries | Relevance 30 · Completeness & functionality 25 · Idea & problem choice 20 · Implementation potential 15 · Originality 10 |
| HubMI.pl | Challenge fulfilment 40 (matchmaking 10 + 5 per extra module) · Implementation potential 20 · Accessibility & intuitiveness 20 · Bonus: interface appeal 10 · Bonus: materials & MVP 10; each scored 1–10 |

---

## 5. Cross-task Conflicts

**[?]**
Submission platform: every Open Task Details file says "Challenge Rocket"; every Rules file says "HackTribe". Rules (legal terms) name HackTribe for both submission and phase-1 evaluation.

**[?]**
Work window: shared template says 11:00 PM Oct 3 → 11:00 PM Oct 4; Kraków and HubMI rules say 11:00 Oct 3 → 11:00 Oct 4. Sources do not explain the difference.

**[?]**
Tie-break wording in template ("the Jury's vote shall decide") does not say whose vote; Kraków and HubMI rules give the chairperson the deciding vote.

**[?]**
Task-specific conflicts (details in each task file §Conflicts): Goldman Sachs criteria weights (CRITERIA vs RULES); Kraków two different criteria sets, agreement naming another project („Krakowskie cyfrowe centrum wolontariatu”), rights recipient Proidea vs Gmina Miejska Kraków; SuperTeam USD vs PLN prize pool and video/repo required only in CRITERIA; Huawei missing "open-source options listed below" list; HubMI PDF *and* video (Rules) vs PDF *or* video (CRITERIA), PL vs EN regulation wording.

---

## 6. Query Routing

**[SPEC]**
| Question type | Read |
|---|---|
| Which task fits idea X / compare tasks | §2 |
| Deadline, team size, submission format, AI use | §3, then task file §Task-specific Rules for deviations |
| How a task is scored | §4, then task file §Judging Criteria |
| Tech stack, required deliverables of a partner task | task file §Requirements, §Deliverables |
| Copyright transfer, agreements, personal data (RODO) | task file §Task-specific Rules; exact clauses in `rules/` |
| Exact quote / legal wording | `rules/<task folder>/*.md` |

---

## Changelog
- 1.0.0 · 2026-10-03 · Initial knowledge base: index, common rules, 10 HADS task summaries over verbatim sources.
