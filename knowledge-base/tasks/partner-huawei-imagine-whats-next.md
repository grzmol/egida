# Huawei Challenge: Imagine What's Next
**Version 1.0.0** · HackYeah 2026 knowledge base · 2026-10-03 · Track: Partner Task — Huawei

---

## AI READING INSTRUCTION

Read `[SPEC]` blocks for authoritative facts.
Read `[NOTE]` only if additional context is needed.
`[?]` blocks are unverified or conflicting between sources — treat with lower confidence.
Common rules for all tasks: `../README.md` §3. This file lists only task-specific facts and deviations.
Exact wording: `../rules/Partner Task [Huawei] - Imagine what_s  next/<file>.md`.

---

## 1. Snapshot
**[SPEC]**
| Field | Value |
|---|---|
| Track | Partner Task — Huawei |
| Organizer | Huawei Polska sp. z o.o., ul. Domaniewska 39A, 02-672 Warsaw (organizes, funds prizes, evaluates, selects winners); PROIDEA = HackYeah organizer, submission platform, pays prizes on Huawei's behalf, no role in evaluation |
| Event | HackYeah 2026, 3–4 Oct 2026, Tauron Arena Kraków |
| Prize | PLN 25,000 total: 1st 12,000 · 2nd 8,000 · 3rd 5,000 (reduced by taxes/contributions/fees) |
| Team size | 1–6, only registered HackYeah 2026 participants |
| Work window | Official HackYeah 2026 schedule (common) |
| Submission platform | "Platform specified by HackYeah" |
| Language | English only (all submissions, presentations, demos, docs) |
| Evaluation | Jury scores 1–10 per criterion; weighted average across jurors; replaces HackYeah Rules §5.5 criteria |
| Min score | Jury may withhold prize if solution < 50% of max final score |
| IP/licence | Participants keep IP; non-exclusive licences to Huawei (§7) |
| Results | 4 Oct 2026, closing ceremony |

## 2. Challenge
**[SPEC]**
- Design and build an innovative system feature or mobile app for an OpenHarmony-based mobile device.
- Must sit in ≥1 area (cross-area combos welcomed):
  - **Intelligent Experiences** — AI agents, contextual awareness, personalization, intelligent interaction, on-device AI.
  - **Spatial Experiences** — spatial UI, 3D content, immersive media, sensing, positioning, new interaction with environment.
  - **Human-Centric Technology** — accessibility, digital wellbeing, inclusive design, education, cultural experiences, responsible tech.
- Final solution should show clear value, functional implementation, innovation current platforms lack.
**[NOTE]**
HarmonyOS is proprietary (Huawei); OpenHarmony is open source (OpenAtom Foundation); Oniro is its European distribution (Eclipse Foundation). Framed around European digital sovereignty; code also runs on HarmonyOS devices.

## 3. Requirements & Constraints
**[SPEC]**
- Allowed stacks: native ArkTS + ArkUI or C/C++ platform APIs; cross-platform framework (e.g. React Native for OpenHarmony, RNOH); OpenHarmony/Oniro system dev frameworks and source-level build tools.
- Must: target HarmonyOS, OpenHarmony or Oniro; target API 20+ (declare API 20 as minimum where applicable); compatible SDK/dev env; run on OpenHarmony/HarmonyOS emulator or compatible physical device; reproducible setup/build/launch instructions; use or improve ≥1 platform/device/system capability.
- Recommended (optional) setup: DevEco Studio, SDK Manager, hvigor, HDC, app signing + emulator/device. Alternatives allowed if reproducible and demonstrable.
- Cross-platform submissions must include an OpenHarmony/HarmonyOS target with native container, bridge and build config producing a working package; Android/iOS/web/desktop build alone insufficient.
- An "improvement" = ready-to-install app or component adding/improving a system capability without modifying the system itself; must explain what it does, platform integration, installation, how to verify.
- Solution created or substantially developed during the Challenge (as a whole); pre-existing code, templates, OSS, AI tools allowed if legally entitled/licence-compliant; material pre-existing/third-party components and AI use must be identified in docs.
- Hygiene (judged): no secrets in repo, input validation, no unnecessary permissions or risky dependencies.

## 4. Deliverables
**[SPEC]**
Required:
1. Public source code repository.
2. Reproducible setup, build, installation and launch instructions.
3. Working `.hap` package.
4. Brief recorded demonstration.
5. Concise architecture and implementation description.
6. `AI_WORKFLOW.md` if AI tools used in development or solution has AI feature.
7. Additional AI integration documentation if solution includes AI features.

`AI_WORKFLOW.md` contents:
- AI feature: model/service, inference flow, data handling, limitations, validation approach, privacy.
- Dev tools: all models, coding agents, MCP servers, Agent Skills, other AI tools; main prompts, reusable instructions, config; workflow ideation→architecture→implementation→testing→debugging; how output was reviewed/tested/validated; limitations, failed approaches, lessons learned.
- Document prompts/tool use as fully as reasonably possible; strip API keys, credentials, personal data, confidential info.

## 5. Judging Criteria
**[SPEC]**
| Criterion | Weight | What is assessed |
|---|---|---|
| Originality | 20% | New idea or fresh take; ports can count if solving something non-obvious; purposeful cross-area combos are a plus |
| Demonstrated usefulness | 20% | Who uses it, what problem; challenge-area link visible in function; working narrow solution > broad slideware |
| Technical execution | 20% | Works as claimed (code/demo/logs/tests); justified architecture; readable modular code, error handling; behaviour on API errors, timeouts, missing data, bad input, wrong model output; some tests for key scenarios; hygiene |
| Use/enhancement of platform capabilities | 20% | Real use of system services, APIs, distributed features; OS-agnostic app scores lower; cross-platform OK if it uses platform features |
| Quality of demonstration | 10% | Actually running (emulator default), not mockups; clear what was built at hackathon; explain parts not runnable on emulator; mentors have devices on site |
| Reproducibility & workflow transparency | 10% | Buildable from README + repo; documented deps/versions/SDKs/config; commit history shows progress; AI use described |

**[NOTE]**
Repositories may undergo automated technical pre-review; final assessment by jury. Jury may invite teams to present/demo.

## 6. Resources & Support
**[SPEC]**
- Mentors have physical devices on site.
- Detailed description published on www.hackyeah.pl on 3 Oct 2026.

## 7. Task-specific Rules
**[SPEC]**
- Rules supplement HackYeah 2026 Rules; unregulated matters governed by them. Participation implies acceptance.
- Eligibility: persons directly involved in organizing or evaluating the Huawei Challenge excluded.
- Prize split equally among team members listed in submission; paid by PROIDEA to individual members' bank accounts within **60 days** of results (deviates from common 90), counted from data delivery if payment/tax data supplied later.
- Winner licence (on accepting prize, each member): to Huawei Polska sp. z o.o. and Huawei Technologies Co., Ltd.; non-exclusive, royalty-free, no territorial limit, 3 years from results; purposes: evaluating/testing, demonstrating/presenting (incl. conferences, fairs), promoting Challenge, HackYeah, HarmonyOS ecosystem. Fields: (a) fixation/reproduction, install, run, store; (b) public display/presentation/performance incl. recorded; (c) making available to public (solution, description, screenshots, recordings), broadcasting/rebroadcasting; (d) translation/adaptation/modification only as needed to run/demo on other devices, software versions, languages — results usable only in (a)–(c), same purposes and term.
- Licence excludes commercial exploitation, distribution as product/service, integration into Huawei products; covers only rights held by team, not pre-existing/third-party components; no ownership transfer; team free to commercialize and grant rights (incl. exclusive) to third parties.
- All submitters' licence: to Huawei and PROIDEA, non-exclusive, royalty-free, no territorial limit, 3 years: project name, team name, description, screenshots, presentation materials, demo recordings in Challenge/HackYeah communications, fields (a)–(c).
- Huawei may invite awarded/notable teams to voluntary talks on further cooperation (promotion, technical collaboration, commercial licensing) — separate agreement, no obligation.
- Participants responsible for not infringing third-party rights and OSS licence compliance.
- Disqualification by Huawei for: rule violations (Challenge or HackYeah), late submission, false/misleading info, third-party rights infringement, fraud/unfair conduct.
- Amendments only for important reasons (law change, technical failure, force majeure); cannot harm acquired rights, reduce pool/prizes, or change criteria/weights after detailed description published; effective on publication on www.hackyeah.pl and official channels.
- AI tools permitted and strongly encouraged (coding agents, assistants, MCP servers, Agent Skills); AI may run local, remote or hybrid. Documentation duty (`AI_WORKFLOW.md`) goes beyond common baseline, which requires no prompt history.

## 8. Conflicts & Open Questions
**[?]**
CRITERIA says alternative tools may include "the open-source options listed below", but no such list exists in the source.
**[?]**
Common baseline says no prompt history required; CRITERIA requires main prompts documented in `AI_WORKFLOW.md` (partner-specific AI rules override per baseline).
**[?]**
Common baseline: PDF presentation ≤10 slides, English or Polish, prize payout 90 days, min 50% "in 1 step" required. Huawei: English only, deliverables list has no PDF deck (RULES §4 says requirements "may include" presentation), payout 60 days, 50% threshold is discretionary ("may decide not to award").

## 9. Sources
- [CRITERIA Imagine What_s Next.md](../rules/Partner%20Task%20%5BHuawei%5D%20-%20Imagine%20what_s%20%20next/CRITERIA%20Imagine%20What_s%20Next.md) — challenge description, technical requirements, AI use, deliverables, criteria with notes.
- [RULES Imagine What_s Next.md](../rules/Partner%20Task%20%5BHuawei%5D%20-%20Imagine%20what_s%20%20next/RULES%20Imagine%20What_s%20Next.md) — legal rules: organizer, teams, submissions, jury scoring, prizes, IP licences, disqualification, amendments.

---

## Changelog
- 1.0.0 · 2026-10-03 · Initial summary from verbatim sources.
