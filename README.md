VEHR (Veteran / Virtual Electronic Health Record)

VEHR is a modular FastAPI-based backend for an integrated EHR platform supporting Mental Health, Substance Use Disorder (SUD), Case Management, Medical, and Psychiatric services, with future support for auditing, billing, eligibility, forms, AI assistance, labs, fax, and CRM workflows.

This repository is the source of truth for architecture and run instructions.

🚀 Quick Start
1. Activate virtual environment
cd C:\VEHR
.\.venv\Scripts\Activate.ps1


You should see:

(.venv) PS C:\VEHR>

2. Run the server
python -m uvicorn app.main:app --reload

3. Open API docs

App: http://127.0.0.1:8000

Swagger docs: http://127.0.0.1:8000/docs

🧠 Core Architecture Rules (READ THIS FIRST)

These rules exist to prevent circular imports and startup failures.

SQLAlchemy base + models pattern (CRITICAL)
DO NOT VIOLATE THIS PATTERN

app/db/base.py

Defines Base only

Must NOT import any models

from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass


app/db/models/*.py

Each model imports Base

Models NEVER import each other directly unless necessary

app/db/models/__init__.py

Imports all models so SQLAlchemy registers tables

from app.db.models.patient import Patient  # noqa


app/main.py

On startup, explicitly imports app.db.models

THEN (optionally) runs Base.metadata.create_all(...) when AUTO_CREATE_TABLES=true

@app.on_event("startup")
def on_startup():
    import app.db.models  # register models
    if os.getenv("AUTO_CREATE_TABLES", "").strip().lower() in {"1", "true", "yes"}:
        Base.metadata.create_all(bind=engine)


👉 If you see errors like “partially initialized module”, this rule was broken.

📁 Project Structure
C:\VEHR
├── app
│   ├── __init__.py
│   ├── main.py
│   ├── api
│   │   └── v1
│   │       ├── router.py
│   │       └── endpoints
│   │           └── patients.py
│   ├── db
│   │   ├── base.py
│   │   ├── session.py
│   │   └── models
│   │       ├── __init__.py
│   │       └── patient.py
│   └── services
├── .venv
├── vehr.db
├── requirements.txt
└── README.md

🧪 Development Notes
Database

SQLite is used for local development (vehr.db)

Designed to be swappable to PostgreSQL later

Migrations (Alembic)

Local DB URL (default): sqlite:///./vehr.db
Actual path when running from repo root: C:\VEHR\vehr.db

Create the initial migration (first-time only):

alembic revision --autogenerate -m "init"

Apply migrations:

alembic upgrade head

Local DB workflow

1. Fresh start: delete or rename C:\VEHR\vehr.db, then run alembic upgrade head.
2. Existing DB already has tables: run alembic stamp head.

Optional dev-only fallback (not recommended for normal use):
set AUTO_CREATE_TABLES=true to allow Base.metadata.create_all() on startup.

Auth bootstrap (first-time only)

POST /api/v1/auth/bootstrap with:
{
  "organization_name": "The Daily Dose",
  "admin_email": "admin@example.com",
  "admin_password": "ChangeMeNow!",
  "admin_name": "Admin User"
}

Use the returned token as:
Authorization: Bearer <token>

Auto-reload

--reload is enabled for development

Server will restart on file changes

🤖 Codex / Copilot Usage Rules

To maintain accuracy and avoid regressions:

Allowed for Codex

New DB models

CRUD endpoints

Pydantic schemas

Refactors inside a single module

NOT allowed for Codex (without human review)

Architecture redesign

Compliance logic

Billing rules

Auth/permission models

Prompt discipline

One vertical slice at a time (Patients → Encounters → Audits → Forms)

Save prompts in codex_prompts/

🛠 Troubleshooting
Server won’t start

Confirm main.py is saved

Confirm .venv is activated

Run from C:\VEHR, not a subfolder

“Attribute app not found”

Ensure app = FastAPI(...) exists in main.py

Ensure app/__init__.py exists

Circular import error

Check base.py does NOT import models

Check models are only imported in models/__init__.py

Check main.py imports app.db.models on startup

📌 Roadmap (High Level)

✅ Patients (v1)

⏭ Encounters / Visits

⏭ Audit Events (compliance backbone)

⏭ Forms Engine (versioned, auditable, PDF)

⏭ Billing + Eligibility

⏭ AI-assisted documentation

⏭ Labs / Fax / CRM integrations

🧭 Runbook (When Coming Back Tomorrow)

Open VS Code

Open folder: C:\VEHR

Activate venv

Run uvicorn

Open /docs

Continue one module at a time

S3 presigned upload/download endpoints

Required env vars:

- AWS_REGION
- S3_BUCKET_NAME
- AWS_ACCESS_KEY_ID
- AWS_SECRET_ACCESS_KEY

Create presigned upload URL:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/uploads/presign" ^
  -H "Authorization: Bearer <token>" ^
  -H "Content-Type: application/json" ^
  -d "{\"filename\":\"intake-form.pdf\",\"content_type\":\"application/pdf\"}"
```

Upload using returned URL:

```bash
curl -X PUT "<url-from-presign-response>" ^
  -H "Content-Type: application/pdf" ^
  --data-binary "@intake-form.pdf"
```

Create presigned download URL:

```bash
curl "http://127.0.0.1:8000/api/v1/uploads/<key-from-presign-response>/download" ^
  -H "Authorization: Bearer <token>"
```

RingCentral integration (OAuth + realtime)

Required API env vars (startup fails fast if missing):

- INTEGRATION_TOKEN_KEY
- RINGCENTRAL_CLIENT_ID
- RINGCENTRAL_CLIENT_SECRET
- RINGCENTRAL_SERVER_URL (default: https://platform.ringcentral.com)
- RINGCENTRAL_REDIRECT_URI (must exactly match the RingCentral app callback URL, example: https://api.360-encompass.com/api/v1/integrations/ringcentral/callback)

Optional (required only for webhook subscription flow):

- RINGCENTRAL_WEBHOOK_SHARED_SECRET
- PUBLIC_WEBHOOK_BASE_URL (example: https://api.360-encompass.com)
- CALL_CENTER_TIMEZONE (optional, default: America/New_York; used for `call_date` partitioning)

Connect flow:

1. Sign in as an admin user with `admin:integrations`.
2. Open Admin Center and click `Connect RingCentral`.
3. Complete OAuth consent in RingCentral.
4. Confirm redirect back to frontend includes `?connected=1` (or `?connected=0&err=<code>` on failure).
5. Verify `ringcentral_credentials` has one row for `(organization_id, user_id)`.
6. Click `Ensure subscription` in Admin Center and confirm subscription shows `ACTIVE`.

Webhook configuration:

- Endpoint:
  `https://api.360-encompass.com/api/v1/webhooks/ringcentral?secret=<RINGCENTRAL_WEBHOOK_SHARED_SECRET>`
- Optional compatibility endpoint:
  `https://api.360-encompass.com/api/v1/integrations/ringcentral/webhook?organization_id=<ORG_ID>&secret=<RINGCENTRAL_WEBHOOK_SHARED_SECRET>`
- Point RingCentral event subscriptions to this URL.
- After a test call event, verify rows are created in `live_calls` (upsert by `session_id`) and `call_events` (raw event log).
- Open `Calls & Reception` and confirm events appear without manual refresh (SSE stream).

Real-time infrastructure API checks (backend only):

1. Ensure subscription:

```bash
curl -X POST "https://api.360-encompass.com/api/v1/integrations/ringcentral/ensure-subscription" \
  -H "Authorization: Bearer <token>"
```

2. RingCentral webhook test (shared secret in query):

```bash
curl -X POST "https://api.360-encompass.com/api/v1/webhooks/ringcentral?secret=<RINGCENTRAL_WEBHOOK_SHARED_SECRET>" \
  -H "Content-Type: application/json" \
  -d '{"event":"/restapi/v1.0/account/~/extension/~/telephony/sessions","eventId":"evt-test-1","body":{"id":"call-test-1","telephonySessionId":"session-test-1"}}'
```

3. Dev-only test-event publisher (pushes one fake call + one fake presence event into org queue):

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/webhooks/ringcentral/test-event" \
  -H "Authorization: Bearer <token>"
```

4. Snapshot + stream (no polling):

```bash
curl "http://127.0.0.1:8000/api/v1/call-center/snapshot" \
  -H "Authorization: Bearer <token>"
```

Historical snapshot by day:

```bash
curl "http://127.0.0.1:8000/api/v1/call-center/snapshot?date=2026-02-12" \
  -H "Authorization: Bearer <token>"
```

Daily CSV export (Power BI / Excel):

```bash
curl "http://127.0.0.1:8000/api/v1/call-center/export?date=2026-02-12" \
  -H "Authorization: Bearer <token>" \
  -o call-center-2026-02-12.csv
```

```text
GET /api/v1/call-center/stream?access_token=<token>
Accept: text/event-stream
```

Call Center visual snapshot test (frontend):

```bash
npm --prefix frontend run test:visual
```

Update the baseline screenshot:

```bash
npm --prefix frontend run test:visual:update
```

AI Copilot + AI Scribe

Required env vars:

- INTEGRATION_TOKEN_KEY (used for at-rest encryption of ai_messages, transcripts, drafts, and capture keys)
- OPENAI_API_KEY

Optional env vars:

- OPENAI_CHAT_MODEL (default: gpt-4o-mini)
- OPENAI_TRANSCRIBE_MODEL (default: whisper-1)
- OPENAI_TIMEOUT_SECONDS (default: 90)
- ScribeAudioRetentionDays (default: 14)

API routes:

- `GET /api/v1/ai/threads`
- `POST /api/v1/ai/threads`
- `GET /api/v1/ai/threads/{thread_id}/messages`
- `POST /api/v1/ai/chat`
- `POST /api/v1/scribe/captures`
- `POST /api/v1/scribe/captures/{id}/complete`
- `POST /api/v1/scribe/captures/{id}/transcribe`
- `POST /api/v1/scribe/captures/{id}/draft-note`
- `PUT /api/v1/scribe/drafts/{id}`
- `POST /api/v1/scribe/drafts/{id}/insert-into-chart`

Quick API check:

1. Send a Copilot message:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/ai/chat" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"Draft SOAP note for intake follow-up\",\"context\":{\"path\":\"/encounters\",\"module\":\"encounters\"}}"
```

2. Create a scribe capture upload URL:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/scribe/captures" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d "{\"encounter_id\":\"<encounter-id>\",\"filename\":\"visit.webm\",\"content_type\":\"audio/webm\"}"
```

3. Upload audio to `upload_url` from step 2, then complete:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/scribe/captures/<capture-id>/complete" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d "{}"
```

4. Transcribe and generate draft:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/scribe/captures/<capture-id>/transcribe" \
  -H "Authorization: Bearer <token>"
```

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/scribe/captures/<capture-id>/draft-note" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d "{\"note_type\":\"SOAP\"}"
```

Navigation + user preferences API

`user_preferences` stores UI preferences per `(organization_id, user_id)`:

- `last_active_module`
- `sidebar_collapsed`
- `copilot_enabled`

Module IDs:

- `care_delivery`
- `call_center`
- `workforce`
- `revenue_cycle`
- `governance`
- `administration`

Endpoints:

- `GET /api/v1/me/preferences`
- `PATCH /api/v1/me/preferences`

Example:

```bash
curl "http://127.0.0.1:8000/api/v1/me/preferences" \
  -H "Authorization: Bearer <token>"
```

```bash
curl -X PATCH "http://127.0.0.1:8000/api/v1/me/preferences" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d "{\"last_active_module\":\"care_delivery\",\"sidebar_collapsed\":false,\"copilot_enabled\":true}"
```

Tanner AI (OpenAI Integration)

Required env vars:

- OPENAI_API_KEY

Endpoints:

- `GET /api/v1/tanner-ai/health`
- `POST /api/v1/tanner-ai/transcribe`
- `POST /api/v1/tanner-ai/generate`
- `POST /api/v1/tanner-ai/note`
- `POST /api/v1/tanner-ai/assistant`

Test transcription:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/tanner-ai/transcribe" \
  -H "Authorization: Bearer <token>" \
  -F "file=@visit.webm"
```

Test note generation:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/tanner-ai/note" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d "{\"transcript\":\"Client reports improved mood and sleep over the last week.\",\"note_type\":\"SOAP\"}"
```

Example usage snippet:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/tanner-ai/assistant" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"Summarize the team huddle notes into action items.\",\"context\":\"Morning operations meeting\"}"
```
