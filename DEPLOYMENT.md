**Overview**
This guide prepares The Daily Dose (EHR) for always-on dev deployment with Neon Postgres, Render (Docker), and Vercel. Alembic remains the single source of truth for schema changes.

**Neon Postgres**
1. Create a Neon project and database.
2. Copy the connection string and ensure it uses SSL.
3. Use this connection string as `DATABASE_URL` everywhere.

Example `DATABASE_URL` format:
```text
postgresql://USER:PASSWORD@HOST:PORT/DB?sslmode=require
```

**Run Alembic Against Neon**
1. From the repo root, set `DATABASE_URL` and run migrations.

PowerShell:
```powershell
cd C:\VEHR
.\.venv\Scripts\Activate.ps1
$env:DATABASE_URL="postgresql://USER:PASSWORD@HOST:PORT/DB?sslmode=require"
alembic upgrade head
```

**Render Web Service (Docker)**
1. Ensure `render.yaml` is at the repo root and `Dockerfile` is present.
2. Create a Render Blueprint service from the repo. The blueprint config is ready for Docker.
3. Set these environment variables for the service:

`DATABASE_URL` = Neon connection string  
`AUTO_CREATE_TABLES` = `false`  
`CORS_ALLOWED_ORIGINS` = `https://<your-vercel-domain>`
`JWT_SECRET` = strong random secret  
`ACCESS_TOKEN_EXPIRE_MINUTES` = `60` (optional)
`AUDIT_RETENTION_YEARS` = `7` (policy setting; used by future retention jobs)
`S3_BUCKET` = bucket name for document storage  
`S3_REGION` = AWS region (optional for MinIO)  
`S3_ENDPOINT_URL` = MinIO endpoint (leave empty for AWS)  
`S3_ACCESS_KEY_ID` = access key  
`S3_SECRET_ACCESS_KEY` = secret key  
`S3_USE_PATH_STYLE` = `true` for MinIO, `false` for AWS  
`S3_PRESIGN_EXPIRES_SECONDS` = `900` (optional; default 15 minutes)
`MS_CLIENT_ID` = Microsoft Entra app client ID  
`MS_CLIENT_SECRET` = Microsoft Entra app client secret  
`MS_REDIRECT_URI` = `https://api.360-encompass.com/api/v1/integrations/microsoft/callback`  
`MS_GRAPH_SCOPES` = `openid profile email offline_access User.Read Sites.Read.All Files.ReadWrite.All`  
`MS_POST_CONNECT_REDIRECT` = `https://360-encompass.com/admin/integrations/microsoft`  
`INTEGRATION_TOKEN_KEY` = secret used to encrypt refresh tokens at rest  
`RINGCENTRAL_CLIENT_ID` = RingCentral OAuth app client ID  
`RINGCENTRAL_CLIENT_SECRET` = RingCentral OAuth app client secret  
`RINGCENTRAL_SERVER_URL` = `https://platform.ringcentral.com`  
`RINGCENTRAL_REDIRECT_URI` = `https://api.360-encompass.com/api/v1/integrations/ringcentral/callback` (must exactly match RingCentral app setting)  
`RINGCENTRAL_POST_CONNECT_REDIRECT` = `https://360-encompass.com/admin-center` (optional)
  
Optional (required for webhook subscription flow):  
`RINGCENTRAL_WEBHOOK_SHARED_SECRET` = shared secret for webhook authentication  
`PUBLIC_WEBHOOK_BASE_URL` = `https://api.360-encompass.com`  

Notes:
`AUTO_CREATE_TABLES` stays off so Alembic is the schema source of truth.  
Render supplies `PORT` automatically for the Docker container.

**Vercel Frontend**
1. Deploy the `frontend` directory as the project root.
2. Set the environment variable:

`NEXT_PUBLIC_API_BASE_URL` = `https://<your-render-service-domain>`
`NEXT_PUBLIC_API_TOKEN` = `Bearer token` (optional for dev; use a token from `/api/v1/auth/login`)
`NEXT_PUBLIC_AUTH_COOKIE_DOMAIN` = `.360-encompass.com` (optional; ensures auth cookies are sent to both app + api subdomains)

3. Build with the default Next.js build command. The API base URL is used for all frontend requests.

**Assistant SSE (Notifications Stream)**
The Enterprise Assistant notifications stream (`GET /api/v1/ai/notifications/stream`) authenticates via cookies (EventSource `withCredentials: true`).

Requirements:
1. **CORS must list explicit origins** in `CORS_ALLOWED_ORIGINS` (no wildcard `"*"`), because the API uses `allow_credentials=True`.
2. Cookies must be scoped so the API host receives them:
   - For production subdomains, set `NEXT_PUBLIC_AUTH_COOKIE_DOMAIN` (frontend) so the `vehr_access_token` cookie is valid for the API domain.
   - For local dev, keep frontend + API on the same hostname (`localhost` vs `127.0.0.1` matters for cookies).
3. Transition-only fallback (dev only): `FEATURE_SSE_QUERY_TOKEN_COMPAT=true` temporarily allows `?access_token=...` on the SSE URL. Leave this **off** in production.

**Operational Checklist**
1. Confirm `DATABASE_URL` is set for Alembic, Render, and any local scripts.
2. Confirm `AUTO_CREATE_TABLES` is not set or is `false`.
3. Confirm `CORS_ALLOWED_ORIGINS` includes the Vercel domain.
4. Confirm `/health` returns `{"status":"ok"}` on the deployed API.
5. Bootstrap the first organization/admin via `POST /api/v1/auth/bootstrap`.
6. Verify frontend `/api -> /api/v1` rewrites against the deployed frontend domain:
   ```bash
   cd frontend
   npm run build
   FRONTEND_URL="https://360-encompass.com" \
   FRONTEND_DEPLOY_BRANCH="main" \
   EXPECTED_COMMIT_SHA="<merged-commit-sha>" \
   API_BASE_URL="https://api.360-encompass.com" \
   ACCESS_LOG_PATH="<optional-access-log-path>" \
   npm run test:api-rewrite:deployment
   ```
   This check validates local build rewrites, runtime `/api` behavior (`/api/health`, `/api/v1/health`, `/api`, `/api/v1/v1/health`), deployed SHA resolution via `/api/v1/version` (or `API_BASE_URL/version` fallback), OpenAPI upload schema for `POST /api/v1/revenue/era-pdfs/upload`, optional access-log signals, and hardcoded absolute API callsites in `frontend/src/**`.
7. Microsoft delegated OAuth checklist:
   - Confirm all Microsoft env vars above are set in API service config.
   - Sign in as an org admin and open `/admin/integrations/microsoft` in the frontend.
   - Click **Connect Microsoft** and complete Microsoft consent.
   - Confirm redirect returns to `/admin/integrations/microsoft?status=connected`.
   - Confirm a row exists in `integration_accounts` for `provider='microsoft'` with `revoked_at` null.
8. RingCentral OAuth + webhook checklist:
   - Confirm all RingCentral env vars above are set in API service config.
   - In Admin Center, open Integrations status and click **Connect RingCentral**.
   - Complete RingCentral consent and confirm redirect returns with `?connected=1` (or `?connected=0&err=<code>`).
   - Confirm a row exists in `ringcentral_credentials` for your `(organization_id, user_id)`.
   - Click **Ensure subscription** and confirm status is `ACTIVE`.
   - Configure RingCentral webhook target URL:
     `https://api.360-encompass.com/api/v1/integrations/ringcentral/webhook?organization_id=<ORG_ID>&secret=<RINGCENTRAL_WEBHOOK_SHARED_SECRET>`
   - Trigger a test call event and confirm rows are created in `call_events`.
   - Open **Calls & Reception** and confirm call feed/presence update without manual refresh.

Example bootstrap payload:
```json
{
  "organization_name": "The Daily Dose",
  "admin_email": "admin@example.com",
  "admin_password": "ChangeMeNow!",
  "admin_name": "Admin User"
}
```

Login example:
```json
{
  "email": "admin@example.com",
  "password": "ChangeMeNow!",
  "organization_id": "<org-id-from-bootstrap>"
}
```

## Incident Response: Production `500` on Login (`POST /api/v1/auth/login`)

### Probable cause ranking (most likely first)
1. **Alembic revision graph mismatch/cycle** causing schema drift on deployed DB (recent CI shows `FAILED: Cycle is detected in revisions (...)`).
2. **Missing/renamed column in auth tables** (`users`, `organization_memberships`) after recent migration chain changes.
3. **`DATABASE_URL` misconfiguration or connectivity failure** (bad scheme, stale creds, network/SSL issues).
4. **JWT config/runtime issue** (`JWT_SECRET`/`JWT_ALGORITHM` invalid or missing in runtime env).
5. **Password hashing runtime issue** (`passlib`/`bcrypt` backend mismatch).
6. **Null/constraint mismatch introduced by migration** on rows read during login path.

### Where to look in code (auth + boot path only)
- Login route + query flow: `/home/runner/work/VEHR/VEHR/app/api/v1/endpoints/auth.py` (`login` at `@router.post("/auth/login")`).
- DB session creation: `/home/runner/work/VEHR/VEHR/app/db/session.py` (`get_db`, `SessionLocal`, `_normalize_database_url`).
- Password verify + JWT creation: `/home/runner/work/VEHR/VEHR/app/core/security.py` (`verify_password`, `create_access_token`).
- Membership lookup model: `/home/runner/work/VEHR/VEHR/app/db/models/organization_membership.py`.
- User model fields used on login: `/home/runner/work/VEHR/VEHR/app/db/models/user.py`.
- App boot/router wiring: `/home/runner/work/VEHR/VEHR/app/create_app.py`, `/home/runner/work/VEHR/VEHR/app/api/v1/router.py`.
- Migration chain: `/home/runner/work/VEHR/VEHR/alembic/versions/*.py`.

### Render log queries to run (exact search terms)
- **Migration chain mismatch**
  - Query: `"Cycle is detected in revisions"`
  - Query: `"No such revision"` or `"Revision .* is present more than once"`
  - Confirms via: `alembic.util.messaging`, `CommandError`, migration abort on startup/deploy jobs.
- **Missing column/table from drift**
  - Query: `"UndefinedColumn"` / `"column .* does not exist"`
  - Query: `"UndefinedTable"` / `"relation .* does not exist"`
  - Confirms via: `sqlalchemy.exc.ProgrammingError`, `psycopg.errors.UndefinedColumn`, `psycopg.errors.UndefinedTable`.
- **DB URL/config/connectivity**
  - Query: `"DATABASE_URL must use Postgres"`
  - Query: `"OperationalError"` / `"could not connect to server"` / `"password authentication failed"`
  - Confirms via: `RuntimeError` from DB URL normalization, `sqlalchemy.exc.OperationalError`.
- **JWT/env issues**
  - Query: `"KeyError: JWT"` / `"JWTError"` / `"Invalid token"`
  - Query: `"TypeError"` near `jwt.encode`/`create_access_token`
  - Confirms via: failures in token generation path before response.
- **Password hashing backend issue**
  - Query: `"passlib"` / `"bcrypt"` / `"error reading bcrypt version"`
  - Confirms via: `ValueError`, `AttributeError`, passlib backend exceptions during `verify_password`.
- **Constraint/null mismatch**
  - Query: `"IntegrityError"` / `"NotNullViolation"` / `"DataError"`
  - Confirms via: `sqlalchemy.exc.IntegrityError`, `psycopg.errors.NotNullViolation`.

### Minimal hotfix strategy (incident only)
- **If migration mismatch/cycle**
  1. Freeze deploys.
  2. On prod DB service shell: `alembic current`, `alembic heads`, `alembic history --verbose`.
  3. Resolve revision DAG in `alembic/versions` (single head, no cycles), redeploy, then `alembic upgrade head`.
- **If missing env var**
  1. In Render service env, verify: `DATABASE_URL`, `JWT_SECRET`, `JWT_ALGORITHM` (if set), `ACCESS_TOKEN_EXPIRE_MINUTES`.
  2. Save + restart service, then re-test `/api/v1/auth/login`.
- **If null/constraint mismatch**
  1. Capture exact failing table/column from stack trace.
  2. Apply minimal forward migration (or emergency SQL patch) to align schema with code.
  3. Re-run `alembic upgrade head`; verify login.
- **If DB revision mismatch**
  1. Compare `alembic_version` value in prod DB vs repository head.
  2. If DB is behind, apply forward migrations only.
  3. If DB points to orphan revision, repair to nearest valid ancestor, then migrate forward.

### Exact next debugging steps
1. In Render logs, filter by `path="/api/v1/auth/login"` and collect the first traceback for a failing request.
2. Classify the exception using the queries above (migration, schema drift, env, DB connectivity, JWT, bcrypt).
3. Validate runtime env values in Render (especially `DATABASE_URL` + `JWT_SECRET`) without rotating unrelated settings.
4. Check migration state on prod DB (`alembic current/heads/history`) and verify no cycle/duplicate revision IDs.
5. Execute the corresponding minimal hotfix path, redeploy once, and re-test login with a known valid account.
6. Confirm `200` login + token issuance; then verify `/api/v1/auth/me` for the same token/org context.

**Tasks API (Phase 1)**
Routes are mounted under `/api/v1`:

- `GET /tasks`
- `POST /tasks`
- `GET /tasks/{id}`
- `PATCH /tasks/{id}`
- `POST /tasks/{id}/complete`
- `POST /tasks/{id}/reopen`
- `POST /tasks/bulk`
- `GET /tasks/calendar`
- `GET /tasks/matrix`

**Tasks Verification Checklist**
1. Create a task from `Operations` (`/dashboard`) or `Tasks` (`/tasks`) and confirm it appears in list view.
2. Complete a task from list action and confirm status updates without page errors.
3. Open `/tasks/matrix`, click a non-zero cell, and confirm matching tasks load in detail panel.
4. Confirm role behavior:
   - receptionist gets `403` for `GET /api/v1/tasks?scope=all`
   - admin can load `scope=all`
