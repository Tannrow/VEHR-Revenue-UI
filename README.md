# VEHR Revenue UI

VEHR Revenue UI is the **Revenue Operating System front end** for the VEHR platform. It is built with Next.js App Router and is designed to connect to the FastAPI backend using environment-configured endpoints.

## Environment variables

Create `.env.local` from `.env.example` (or configure Azure Container App environment variables):

```bash
NEXT_PUBLIC_API_URL=https://api-staging.360-encompass.com
# Optional internal override for server-side requests only.
BACKEND_INTERNAL_URL=https://api-staging.360-encompass.com
```

- `NEXT_PUBLIC_API_URL` is the preferred public backend origin for the server-side proxy routes.
- `BACKEND_INTERNAL_URL` is optional and overrides server-side requests when an internal network URL is available.
- Legacy fallback vars `NEXT_PUBLIC_API_BASE_URL` and `NEXT_PUBLIC_BACKEND_URL` are still supported for compatibility.

## Local development

```bash
npm install
npm run dev
```

Then open `http://localhost:3000`.

## Build

```bash
npm run typecheck
npm run lint
npm run build
npm run start
```

## Route availability

- The App Router lives under `src/app`.
- `/login` renders the sign-in form and posts to `/api/auth/login`.
- `/dashboard`, `/era`, `/era/[eraFileId]`, and `/claims` fetch real backend data through same-origin App Router API routes and show a sign-in-required state when auth is missing.
- `/era` handles upload/process and surfaces recent ERA files so operators can jump straight into the file lab.
- `/era/[eraFileId]` is the file-specific replay lab for redacted extract previews, merged claim lines, work item previews, and replay controls.
- `/api/health`, `/api/dashboard`, `/api/claims`, `/api/era`, `/api/era/[eraFileId]/lab`, `/api/era/[eraFileId]/replay`, `/api/mcp-health`, `/api/readyz/components`, and `/api/auth/*` proxy requests to the configured backend origin.

## Framework conventions

- Shared page layout primitives live in `src/components/page-shell.tsx`.
- Route-level resilience lives in the App Router special files: `src/app/loading.tsx`, `src/app/error.tsx`, and `src/app/not-found.tsx`.
- Backend proxy requests should go through `src/lib/backend.ts`, which includes the shared backend fetch/discovery helpers.

## CI

- GitHub Actions workflow `.github/workflows/ci.yml` runs lint, type-check, and build validation on pushes to `main` and on pull requests.
- Container deployment is now driven from Azure CLI or the VS Code terminal: build the image, push it to ACR, then update the frontend Container App directly.

## Control Tower

- Frontend deploy path: Azure CLI / VS Code terminal → build image → push to ACR → update the staging frontend Container App.
- Rollback path: update the frontend Container App back to a known-good image tag with Azure CLI.
- Keep the repo and infrastructure parameter files as the source of truth for runtime env names, ports, and image contracts. Avoid manual Azure portal drift.

## Bringing `360-encompass.com` live

To make the site operational in Azure Container Apps:

1. Deploy this frontend container with `NEXT_PUBLIC_API_URL` set to the VEHR API domain.
2. Optionally provide `NEXT_PUBLIC_API_BASE_URL` as a fallback backend origin.
3. Bind custom domain `360-encompass.com` (and `www`/`app` as needed) to the frontend Container App.
4. Validate DNS records point to Container Apps managed ingress.
5. Provision and verify TLS cert binding for each hostname.
6. Confirm backend CORS allows the frontend origin(s) and JWT issuer/audience settings are correct.

If deployment is failing before startup, check build logs for external fetch failures and runtime logs for missing environment variables.
