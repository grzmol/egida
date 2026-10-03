# AI Control Layer
**Version 1.0.1** · HackYeah 2026 knowledge base · 2026-10-03 · Track: Partner Task — Goldman Sachs

---

## AI READING INSTRUCTION

Read `[SPEC]` blocks for authoritative facts.
Read `[NOTE]` only if additional context is needed.
`[?]` blocks are unverified or conflicting between sources — treat with lower confidence.
Common rules for all tasks: `../README.md` §3. This file lists only task-specific facts and deviations.
Exact wording: `../rules/Partner Task [Goldman Sachs] - AI Control Layer/<file>.md`.

---

## 1. Snapshot
**[SPEC]**
| Field | Value |
|---|---|
| Track | Partner Task — Goldman Sachs (partner name from folder name only) |
| Prize sponsor | common (Proidea Sp. z o.o.) |
| Prize | PLN 15,000 incl. tax: 1st 6,000 · 2nd 5,000 · 3rd 4,000 |
| Team size | common (1–6) |
| Work window | common (Oct 3 11:00 → Oct 4 11:00; draft by Oct 3 20:00 — README §3.2) |
| Submission platform | HackTribe (RULES) |
| Language | common (English or Polish) |
| Evaluation | common 2 phases; judges also run the team's test suite and test live (§5) |
| Min score | common (50%) |
| IP | common (copyrights not transferred) |
| Paid services | None provided; must run entirely on own setup |

## 2. Challenge
**[SPEC]**
- Build a lightweight, flexible AI Control Layer (gateway, proxy, middleware, SDK wrapper or other component) that intercepts and governs interactions with Agentic AI systems (AI agents, MCP services, LLMs, APIs): agent↔agent, app→agent, agent→MCP, agent→model, etc.
- Enforce security, privacy and resource controls defined in a centralized configuration source (e.g. control catalog).
- Hybrid defense: deterministic (non-AI) + AI-based (semantic) controls; inspect, redact or block unsafe interactions in real time.
- Manage budgets for external commercial APIs and locally hosted models.
- Detect/mitigate known historical attacks on AI infrastructure; signatures may be fed from an externally managed system.
- Reporting for security teams and management (UI or otherwise).
**[NOTE]**
Example risks: weak authentication/access control for agents (impersonation, harmful irreversible actions), prompt injection, sensitive data in outputs, unauthorized memory/shared-context retrieval, runaway loops and unexpected resource consumption. Listed threats are only examples; teams should analyze the ecosystem and sources such as OWASP for further controls toward a production-ready defense.

## 3. Requirements & Constraints
**[SPEC]**
Formal requirements:
1. Centralized Policy Engine: single config source for controls, sensitivity thresholds (Block vs Redact or adherence %), allowed LLM models, resource/financial budgets.
2. Controls/Guardrails: deterministic (e.g. PII/secret pattern matching, authentication/access checks) and semantic AI-based where possible.
3. Budget & Resource Governance: enforce limits (e.g. resource access, compute time, LLM token spend).
4. Historical Attack Mitigation: detect/block patterns of successful historical exploits, e.g. malicious code execution, unsafe deserialization, supply-chain exploits targeting model repositories.
5. Security Reporting & Auditing: real-time metrics (blocked interactions, budget usage) for management + exportable audit logs for security teams (threats, policy violations, usage); dashboard or otherwise.
6. Self-Testing Suite: automated, positive (allowed) and negative (blocked) cases.

Technical:
- Any stack (e.g. Go, Rust, Python) from scratch or on open-source tools — check licences.
- Agents, LLMs, apps using the layer may be pre-existing; they are not assessed.
- No datasets, proprietary APIs, hardware or paid subscriptions (OpenAI, Anthropic, Copilot, etc.) provided; use public OSS libraries, local models (e.g. Ollama), self-created test prompts.

## 4. Deliverables
**[SPEC]**
Task-specific (in addition to common submission package):
1. AI Control Layer — functional, easily integrable; showcase with own or existing agent; simple architecture diagram.
2. Sample Configuration — documented policy file showing different strictness/adherence levels and budget rules.
3. Simple Interactive Dashboard — controls, overall security posture, blocked threats, metrics (e.g. resource consumption/cost).
4. Executable Test Suite — ready to run; verifies controls incl. budget limits and exploit mitigation; positive and negative cases.
- Performance telemetry must be producible (may be used for evaluation).

## 5. Judging Criteria
**[SPEC]**
| Criterion | Weight (CRITERIA) | Weight (RULES) |
|---|---|---|
| Robustness of the Solution and Quality of Guardrails | 30% | 30% |
| Architecture and Performance Efficiency | 20% | 20% |
| Security Reporting | 20% | 20% |
| Completeness of the Self-Testing Suite | 15% | 20% |
| Practical Implementability and Scalability | 15% | 10% |

Validation approach (zero-preparation by judges):
- Judges execute the team's automated test suite.
- Judges interactively test the running layer with spontaneous ad-hoc prompts.
- Judges may modify config files/feeds (change rules, remove controls, adjust thresholds) to see how/whether changes apply, incl. in real time.
- Judges review architecture, dashboards, and logging for management and security teams.

## 6. Task-specific Rules
**[SPEC]**
- Prize pool PLN 15,000 incl. tax (6,000 / 5,000 / 4,000) replaces open-task default 8,000 PLN.
- Criteria replace open-task defaults (see §5).
- Otherwise same as common rules (README §3).

## 7. Conflicts & Open Questions
**[?]**
Criterion weights differ: CRITERIA file gives Self-Testing Suite 15% / Practical Implementability and Scalability 15%; RULES file (§11) gives 20% / 10%. Other weights match.
**[?]**
Partner "Goldman Sachs" appears only in the folder name; neither source names the partner.

## 8. Sources
- [`CRITERIA AI Control Layer.md`](../rules/Partner%20Task%20%5BGoldman%20Sachs%5D%20-%20AI%20Control%20Layer/CRITERIA%20AI%20Control%20Layer.md) — task brief: context, challenge, expected outcome, formal/technical requirements, validation, resources, criteria.
- [`RULES AI Control Layer.md`](../rules/Partner%20Task%20%5BGoldman%20Sachs%5D%20-%20AI%20Control%20Layer/RULES%20AI%20Control%20Layer.md) — competition T&C: sponsor, eligibility, submission, prizes, phases, criteria.

---

## Changelog
- 1.0.0 · 2026-10-03 · Initial summary from verbatim sources.
- 1.0.1 · 2026-10-03 · Work window updated to team-confirmed 11:00 → 11:00 + 20:00 draft.
