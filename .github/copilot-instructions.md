# Copilot Instructions for Tannrow/VEHR

- Read `AGENTS.md` and `CODEX_RULES.md` first: keep diffs minimal, do not refactor unrelated code, and do not weaken auth, isolation, encryption, or audit logging. No tokens in URLs; avoid logging PHI; audit tool invocations (attempt + result).
- Locked files: do not edit `app/main.py` or `app/db/base.py` without explicit approval. Default scope lives in `frontend/src/app/**`, `frontend/src/components/**`, `frontend/src/lib/**`, and `app/api/v1/**`; only touch `app/db/models/**` when a task explicitly calls for it.
- Frontend: Next.js App Router + TypeScript; keep server/client boundaries correct (no `window` at module scope); prefer shadcn/ui + Tailwind tokens; preserve existing Power BI embedding behavior.
- Assistant architecture touchpoints: `app/services/assistant/agent_registry.py`, `tool_gateway.py`, `enterprise_copilot.py`; reminders via `assistant_reminder`/`assistant_notification` and worker `app.workers.reminder_dispatcher`; SSE notifications at `/api/v1/ai/notifications/stream`.
- Startup: backend `python -m uvicorn app.main:app --reload`; frontend `cd frontend && npm run dev`; API docs at `http://127.0.0.1:8000/docs`.
- Tests before handoff: backend `pytest` (when available) and `python -m compileall app`; frontend `cd frontend && npm run lint` then `npm run build`; worker smoke `python -m app.workers.reminder_dispatcher` in a dev-safe mode.
- General rules: do not invent endpoints/env vars/report IDs/auth helpers—reuse existing patterns. Keep new changes small, coherent, and aligned with existing modules and design tokens.
