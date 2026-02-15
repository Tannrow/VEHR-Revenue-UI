# Engineering rules (Analytics)

- Do not invent endpoints, env vars, report IDs, or auth helpers. If unknown, search the repo and reuse existing patterns.
- Preserve Power BI embedding behavior. No changes to embed auth/token flow unless explicitly requested.
- Next.js App Router + TypeScript: keep server/client boundaries correct; no `window` usage outside client components; no module-level `window` references.
- Prefer shadcn/ui + Tailwind; follow existing design tokens and spacing conventions.
- Error handling: no silent failures; render safe fallbacks; log/trace in the app’s existing logging pattern.
- Deliver changes as small, coherent edits; avoid giant refactors unless necessary.
