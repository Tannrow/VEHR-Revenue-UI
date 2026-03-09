# VEHR Revenue UI

VEHR Revenue UI is the **Revenue Operating System front end** for the VEHR platform. It is built with Next.js App Router and is designed to connect to the FastAPI backend using environment-configured endpoints.

## Environment variables

Create `.env.local` (or configure Azure Container App environment variables):

```bash
NEXT_PUBLIC_API_URL=https://api-staging.360-encompass.com
# Optional fallback if NEXT_PUBLIC_API_URL is not set.
NEXT_PUBLIC_API_BASE_URL=https://api-staging.360-encompass.com
```

- `NEXT_PUBLIC_API_URL` is used by the server-side proxy routes to reach the backend.
- `NEXT_PUBLIC_API_BASE_URL` is an optional fallback for the same backend origin.

## Local development

```bash
npm install
npm run dev
```

## Build

```bash
npm run typecheck
npm run lint
npm run build
npm run start
```

## Route availability

- The App Router lives under `src/app`.
- `/dashboard`, `/era`, and `/claims` fetch real backend data through same-origin App Router API routes.
- `/api/health`, `/api/dashboard`, `/api/claims`, `/api/era`, and `/api/auth/*` proxy requests to the configured backend origin.

## Framework conventions

- Shared page layout primitives live in `src/components/page-shell.tsx`.
- Route-level resilience lives in the App Router special files: `src/app/loading.tsx`, `src/app/error.tsx`, and `src/app/not-found.tsx`.
- Backend proxy requests should go through `src/lib/backend.ts`, which includes the shared backend fetch/discovery helpers.

## CI

- GitHub Actions workflow `.github/workflows/ci.yml` runs lint, type-check, and build validation on pushes to `main` and on pull requests.
- GitHub Actions workflow `.github/workflows/build-and-push-ui.yml` builds the Docker image on pushes to `main` and on manual dispatch, then authenticates to Azure with OIDC and pushes `vehrrevostagingacr.azurecr.io/vehr-revenue-ui:<short-sha>` when the required Azure secrets are configured.

## Bringing `360-encompass.com` live

To make the site operational in Azure Container Apps:

1. Deploy this frontend container with `NEXT_PUBLIC_API_URL` set to the VEHR API domain.
2. Optionally provide `NEXT_PUBLIC_API_BASE_URL` as a fallback backend origin.
3. Bind custom domain `360-encompass.com` (and `www`/`app` as needed) to the frontend Container App.
4. Validate DNS records point to Container Apps managed ingress.
5. Provision and verify TLS cert binding for each hostname.
6. Confirm backend CORS allows the frontend origin(s) and JWT issuer/audience settings are correct.

If deployment is failing before startup, check build logs for external fetch failures and runtime logs for missing environment variables.
