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

Notes:
`AUTO_CREATE_TABLES` stays off so Alembic is the schema source of truth.  
Render supplies `PORT` automatically for the Docker container.

**Vercel Frontend**
1. Deploy the `frontend` directory as the project root.
2. Set the environment variable:

`NEXT_PUBLIC_API_BASE_URL` = `https://<your-render-service-domain>`
`NEXT_PUBLIC_API_TOKEN` = `Bearer token` (optional for dev; use a token from `/api/v1/auth/login`)

3. Build with the default Next.js build command. The API base URL is used for all frontend requests.

**Operational Checklist**
1. Confirm `DATABASE_URL` is set for Alembic, Render, and any local scripts.
2. Confirm `AUTO_CREATE_TABLES` is not set or is `false`.
3. Confirm `CORS_ALLOWED_ORIGINS` includes the Vercel domain.
4. Confirm `/health` returns `{"status":"ok"}` on the deployed API.
5. Bootstrap the first organization/admin via `POST /api/v1/auth/bootstrap`.
6. Microsoft delegated OAuth checklist:
   - Confirm all Microsoft env vars above are set in API service config.
   - Sign in as an org admin and open `/admin/integrations/microsoft` in the frontend.
   - Click **Connect Microsoft** and complete Microsoft consent.
   - Confirm redirect returns to `/admin/integrations/microsoft?status=connected`.
   - Confirm a row exists in `integration_accounts` for `provider='microsoft'` with `revoked_at` null.

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
