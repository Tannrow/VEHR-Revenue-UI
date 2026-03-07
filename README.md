# VEHR Revenue UI

VEHR Revenue UI is the **Revenue Operating System front end** for the VEHR platform. It is built with Next.js App Router and is designed to connect to the FastAPI backend using environment-configured endpoints.

## Environment variables

Create `.env.local` (or configure Azure Container App environment variables):

```bash
NEXT_PUBLIC_BACKEND_URL=https://api.360-encompass.com
# Optional: internal/private backend URL used by server-side rendering.
BACKEND_INTERNAL_URL=http://vehr-api.internal
```

- `NEXT_PUBLIC_BACKEND_URL` is safe to expose to the browser and should point to the public API origin.
- `BACKEND_INTERNAL_URL` is optional and intended for server-side runtime calls from Next.js to a private/internal API endpoint.

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

## Backend connectivity

- `/dashboard` now runs a server-side health probe against the configured backend URL.
- `/api/health` exposes the same health status as JSON for CI, monitoring, and app-level checks.
- `/dashboard` now runs in dynamic server-render mode, so health checks happen at request time (not at build time).
- The probe checks common health paths (`/health`, `/api/health`, `/api/v1/health`, `/healthz`) and reports status in the UI.
- Backend URL configuration is validated before requests are made, and malformed URLs fail fast with a readable error state.
- Authentication flow is unchanged; this only validates transport-level reachability.

## Framework conventions

- Shared page layout primitives live in `src/components/page-shell.tsx`.
- Route-level resilience lives in the App Router special files: `src/app/loading.tsx`, `src/app/error.tsx`, and `src/app/not-found.tsx`.
- Backend requests should go through `src/lib/backend.ts`, which now includes a reusable typed fetch helper.

## CI

- GitHub Actions workflow `.github/workflows/ci.yml` runs lint, type-check, and build validation on pushes to `main` and on pull requests.

## Bringing `360-encompass.com` live

To make the site operational in Azure Container Apps:

1. Deploy this frontend container with `NEXT_PUBLIC_BACKEND_URL` set to the VEHR API domain.
2. Ensure API ingress is reachable from the frontend container (public or internal via `BACKEND_INTERNAL_URL`).
3. Bind custom domain `360-encompass.com` (and `www`/`app` as needed) to the frontend Container App.
4. Validate DNS records point to Container Apps managed ingress.
5. Provision and verify TLS cert binding for each hostname.
6. Confirm backend CORS allows the frontend origin(s) and JWT issuer/audience settings are correct.

If deployment is failing before startup, check build logs for external fetch failures and runtime logs for missing environment variables.
