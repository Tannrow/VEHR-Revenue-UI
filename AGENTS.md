# Engineering rules (Analytics)

- Do not invent endpoints, env vars, report IDs, or auth helpers. If unknown, search the repo and reuse existing patterns.
- Preserve Power BI embedding behavior. No changes to embed auth/token flow unless explicitly requested.
- Next.js App Router + TypeScript: keep server/client boundaries correct; no `window` usage outside client components; no module-level `window` references.
- Prefer shadcn/ui + Tailwind; follow existing design tokens and spacing conventions.
- Error handling: no silent failures; render safe fallbacks; log/trace in the app’s existing logging pattern.
- Deliver changes as small, coherent edits; avoid giant refactors unless necessary.

# Valley AI – Codex Agent Instructions (VEHR Enterprise Assistant)

## Goal
Work inside this repo to evolve the Enterprise Assistant:
- Per-user, per-org secure assistant inside VEHR dock UI
- Persistent threads + memory + reminders
- Microsoft 365 reminder channels (To Do + Outlook) via Tool Gateway
- Auditable, PHI-safe, org-aware

## Non-negotiables
- Do not weaken auth, isolation, encryption, or audit logging.
- PHI guardrails: never log sensitive content; keep metadata minimal.
- No tokens in URLs. Cookies/headers only.
- Keep tool invocations fully audited (attempt + result).

## Architecture map (high level)
- Agent runtime: `agent_registry.py`, `tool_gateway.py`, `enterprise_copilot.py`
- Chat: `POST /api/v1/ai/chat`, threads/messages endpoints
- Memory: `/api/v1/ai/memory` (server-side, user+org scoped)
- Reminders: `assistant_reminder`, `assistant_notification`, worker `app.workers.reminder_dispatcher`
- Notifications: SSE `/api/v1/ai/notifications/stream` (cookie auth)

## How to work
1. Start by locating the closest existing patterns before adding new ones.
2. Make minimal, reviewable diffs. Prefer extending existing modules.
3. Add/extend tests for any new behavior.
4. Update docs when behavior changes.

## Commands you should run (adjust if repo differs)
- Backend tests: `pytest`
- Typecheck/lint (if present): `ruff .` / `mypy .`
- Migrations: use the repo’s standard migration tool (Alembic or equivalent)
- Worker smoke: run `python -m app.workers.reminder_dispatcher` in a dev-safe mode (no external calls)

## Microsoft 365 specifics
- Use existing Entra config + scopes already planned:
  - Tasks.ReadWrite, Calendars.ReadWrite, offline_access
- Implement OAuth connect/disconnect endpoints + persistence table:
  - `user_microsoft_connections`
- Tool Gateway contracts:
  - `ms.todo.task.create_draft`
  - `ms.outlook.event.create_draft`
- Reminder dispatch rules:
  - Date+Time => Outlook event draft + chat reminder
  - Date only/relative => To Do task draft + chat reminder

## Deliverables expectations
- DB migration(s) included
- Endpoints implemented with auth + org scoping
- Tool Gateway actions implemented + audited
- Tests + docs updated
