# AGENTS.md — froggers

Team repository for the HackYeah 2026 hackathon (Kraków, Oct 3–4, 2026). Read this before doing any work.

## Project State

- Chosen task: **AI Control Layer** (Partner Task, Goldman Sachs) — spec: `knowledge-base/tasks/partner-goldman-sachs-ai-control-layer.md`. Runner-up: HubMI.pl. Selected 2026-10-03.
- No application code yet. Plan: `docs/PLAN.md` (phases F0–F7, debt rules, definition of done). Decisions: `docs/adr/`. Stack proposed in ADR-0002 (Python 3.12 + uv + FastAPI + Pydantic v2 + Ollama), status Proposed — confirm with the user before scaffolding code.
- `Dockerfile`, `compose.yaml`, `.dockerignore`, `README.Docker.md` are the unmodified `docker init` scaffold: Alpine image printing "Hello world" via `/bin/hello.sh`. No ports exposed, no services besides `app`.
- `README.md` describes the chosen task, the selection analysis, risks, MVP scope and open questions (in Polish). Keep it in sync when the decision or scope changes.
- The user writes in Polish. Reply in Polish unless asked otherwise.

## Repository Layout

| Path | Purpose |
|---|---|
| `knowledge-base/README.md` | Index: task comparison, common hackathon rules, judging criteria, cross-task conflicts, query routing |
| `knowledge-base/tasks/<slug>.md` | One AI-optimized summary per task (10 tasks: 5 Open, 5 Partner) |
| `knowledge-base/rules/<task folder>/*.md` | Verbatim text of the official PDFs/DOCX (originals deleted; these are the source of truth) |
| `docs/PLAN.md` | Project plan: scope, anti-debt rules, architecture, phases, requirement→test matrix, definition of done, risks |
| `docs/adr/` | Architecture Decision Records + index |
| `Dockerfile`, `compose.yaml` | Container scaffold (placeholder) |
| `docs/research/` | Landscape of existing tools, threat catalog, test design, persona brainstorms; synthesis + proposed plan changes in `docs/research/README.md` |
| `docs/WORKPLAN.md` | Two-developer parallel work plan: file ownership, timeline, sync points, git and Claude Code workflow |
| `CLAUDE.md` | Imports `AGENTS.md` and `docs/WORKPLAN.md` for Claude Code sessions |

## Answering Questions About the Hackathon

1. Start at `knowledge-base/README.md`: §2 comparison, §3 common rules, §4 criteria, §5 conflicts, §6 routing table.
2. Open `knowledge-base/tasks/<slug>.md` for the task in question; it lists only deviations from README §3.
3. Open `knowledge-base/rules/…` only for exact wording, legal clauses (copyright transfer, RODO, licences) or quotes.
- Precedence: `rules/` > `tasks/` > `README.md`. Partner rules override common rules for their task.
- Facts in `**[?]**` blocks are conflicting or unverified in the official sources. Always tell the user when an answer depends on one (e.g. HackTribe vs Challenge Rocket, Goldman Sachs and Kraków criteria weights).
- Work window is confirmed by the team: all tasks 11:00 Oct 3 → 11:00 Oct 4, first draft due 20:00 Oct 3 (`knowledge-base/README.md` §3.2).
- Never answer from memory or general HackYeah knowledge; cite the file.

## Editing the Knowledge Base

- `rules/`: verbatim. Change only to fix a proven transcription error against the original document. Keep source typos and original language (PL/EN).
- `tasks/` and `knowledge-base/README.md` follow HADS (`skill://hads`):
  - H1, `**Version X.Y.Z**` line, `## AI READING INSTRUCTION` manifest, numbered `##` sections, `## Changelog` at the end.
  - Bold tags on their own line, content directly below: `**[SPEC]**` facts (terse, tables/bullets), `**[NOTE]**` context, `**[?]**` conflicts/unverified. No `[BUG]`.
  - English text; keep official Polish names in parentheses; copy amounts, dates, IDs, URLs exactly.
  - Task files list only deviations from README §3 — never repeat common rules.
  - Every fact must trace to a file in `rules/`. No advice, no inferred facts outside `**[?]**`.
- On any change: bump the file's version, add a changelog line, and update the README comparison/criteria tables if the change affects them.
- New task: add verbatim `rules/<folder>/*.md`, a `tasks/<track>-<partner>-<name>.md` summary using an existing task file as template, and a row in README §1, §2, §4.

## Hackathon Constraints for Development Work

These come from `knowledge-base/README.md` §3 and apply to all code written here:
- Only work done during the competition window counts. Keep pre-existing code clearly separated and disclosed.
- The team must be able to explain and defend every part of the solution, including AI-generated code. Prefer simple, explainable designs over clever ones.
- Disclose significant AI tools, external models, APIs, datasets and libraries; cite reused repositories/materials; respect OSS licences.
- Some partner tasks have stricter requirements (e.g. Huawei requires `AI_WORKFLOW.md` with main prompts; Kraków and HubMI transfer copyright to the sponsor; HubMI is 18+ and on-site). Check the chosen task's file before starting.
- Never commit secrets, API keys or personal data; `.env` is already excluded from the Docker build context.

## Architecture Guardrails

Source: `docs/PLAN.md` §2–§4 and ADR-0001…0004. Summary for agents:
- `core/` is framework-free: no FastAPI, httpx, Ollama, file or network imports. Outside world only through ports in `core/ports.py`. Enforced by `import-linter`.
- Adapters are constructed only in `app.py` (composition root).
- New control = new `Detector` + policy entry + cases in `tests/cases/`. Never change the pipeline to add a control.
- Detectors return findings; they never decide or swallow errors. Every control has `timeout` and `on_error` (default `block`).
- Policy is a versioned Pydantic schema; invalid policy is rejected and the last valid one stays active.
- No new dependency, model, data format, protocol or port change without an ADR. Pin in `uv.lock`, record licence in `docs/DEPENDENCIES.md`.
- Work in one vertical increment from `docs/PLAN.md` §5 at a time: failing test first, then code.

## Definition of Done

Every increment must pass `docs/PLAN.md` §8 (based on `skill://ai-debt-detector`): green `make check`, positive and negative cases, failure modes handled with specific exceptions, no orphaned resources, no unverified imports, no architecture drift, no TODOs, `docs/ai-usage/<dev>.md` updated, plan status updated.

## Parallel Work (four developers)

`docs/WORKPLAN.md` is binding. **Dev A = Grzegorz** (git author `grzegorz.moldawa@gmail.com`, Claude Code) owns platform files (`core/`, `app.py`, `pyproject.toml`, `Makefile`, proxy/policy/budget/audit adapters, `config/`). **Dev B = Sebastian** (git author `skowron.sebastian`, Claude Code) owns `detectors/`, `metrics_memory.py`, `dashboard/`, `tests/cases/` (except `kamil-*.yaml`), `tests/test_cases.py`. **Dev C = Kamil** (git author: to be added, Gemini CLI via `GEMINI.md`) owns `tests/cases/kamil-*.yaml`, `scripts/prepare_eval_data.py`, `docs/eval/`, `docs/owasp-mapping.md`, `docs/pitch/`, `docs/submission/`, `docs/qa/` — never source code under `src/`. Tasks: `docs/tasks/<grzegorz|sebastian|kamil>/`. Determine the current developer from `git config user.email`; if unclear, ask. Touch only that developer's files; request changes to others' files instead of editing them. AI usage log: `docs/ai-usage/<name>.md`. Workflow per push: `git pull --rebase origin main && make check && git push`.

**Dev D = Maciej** (git author: to be added, Claude Code Pro, branch `maciej`) owns `.github/workflows/ci.yml`, `Dockerfile`, `compose.yaml`, `.dockerignore`, `config/policy.compose.yaml`, `tests/unit/deploy/`, `scripts/demo_agent.py`, `scripts/demo_tools.json`, `scripts/bench.py`, `examples/`, `docs/deploy.md`, `docs/recording.md` — never source code under `src/`. Tasks: `docs/tasks/maciej/`. Grzegorz works on branch `grzegorz`.

## Docker

- Run: `docker compose up --build`.
- When the stack is chosen, replace the `build` stage and `ENTRYPOINT` in `Dockerfile`, uncomment/adjust `ports` in `compose.yaml`. Keep the non-root `appuser` in the final stage.
- Build for amd64 hosts from Apple Silicon: `docker build --platform=linux/amd64 -t <name> .`.
