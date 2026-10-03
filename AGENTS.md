# AGENTS.md — froggers

Team repository for the HackYeah 2026 hackathon (Kraków, Oct 3–4, 2026). Read this before doing any work.

## Project State

- No application code yet. Stack and chosen task are not decided in the repo — ask the user; do not assume.
- `Dockerfile`, `compose.yaml`, `.dockerignore`, `README.Docker.md` are the unmodified `docker init` scaffold: Alpine image printing "Hello world" via `/bin/hello.sh`. No ports exposed, no services besides `app`.
- `README.md` is a placeholder.
- The user writes in Polish. Reply in Polish unless asked otherwise.

## Repository Layout

| Path | Purpose |
|---|---|
| `knowledge-base/README.md` | Index: task comparison, common hackathon rules, judging criteria, cross-task conflicts, query routing |
| `knowledge-base/tasks/<slug>.md` | One AI-optimized summary per task (10 tasks: 5 Open, 5 Partner) |
| `knowledge-base/rules/<task folder>/*.md` | Verbatim text of the official PDFs/DOCX (originals deleted; these are the source of truth) |
| `Dockerfile`, `compose.yaml` | Container scaffold (placeholder) |

## Answering Questions About the Hackathon

1. Start at `knowledge-base/README.md`: §2 comparison, §3 common rules, §4 criteria, §5 conflicts, §6 routing table.
2. Open `knowledge-base/tasks/<slug>.md` for the task in question; it lists only deviations from README §3.
3. Open `knowledge-base/rules/…` only for exact wording, legal clauses (copyright transfer, RODO, licences) or quotes.
- Precedence: `rules/` > `tasks/` > `README.md`. Partner rules override common rules for their task.
- Facts in `**[?]**` blocks are conflicting or unverified in the official sources. Always tell the user when an answer depends on one (e.g. HackTribe vs Challenge Rocket, 11:00 vs 11:00 PM work window, Goldman Sachs and Kraków criteria weights).
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

## Docker

- Run: `docker compose up --build`.
- When the stack is chosen, replace the `build` stage and `ENTRYPOINT` in `Dockerfile`, uncomment/adjust `ports` in `compose.yaml`. Keep the non-root `appuser` in the final stage.
- Build for amd64 hosts from Apple Silicon: `docker build --platform=linux/amd64 -t <name> .`.
