# VEHR Dev Notes

## Local run
- Backend:
  - `.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000`
- Frontend:
  - `cd frontend`
  - `npm ci`
  - `npm run dev`

## Local smoke checks
- Backend tests:
  - `.\.venv\Scripts\python.exe -m pytest -q`
- Seed demo data:
  - `.\.venv\Scripts\python.exe -m app.scripts.seed_demo`
- Nightly-style recheck job:
  - `.\.venv\Scripts\python.exe -m app.jobs.run_clinical_audit_rechecks`

## Env flags
- `NEXT_PUBLIC_API_BASE_URL`:
  - Frontend API base URL (`https://api.the-trapp-house.com` in Azure Container Apps).
- `NEXT_PUBLIC_API_TOKEN`:
  - Optional static token fallback for frontend API calls.
  - Temporary option until full interactive login/session UX is added.
- `CORS_ALLOWED_ORIGINS`:
  - Comma-separated allowed origins for backend CORS.
- `CLINICAL_AUDIT_AUTO_RUN_ON_SUBMISSION`:
  - `true`/`false` toggle for auto audit on assessment submission.
- `CLINICAL_AUDIT_PLAN_WINDOW_DAYS`:
  - Window used by deterministic rules and recheck job.
- `CLINICAL_AUDIT_AUTO_QUEUE_MIN_SEVERITY`:
  - Threshold (`info`, `warning`, `high`) for auto queue creation.

## Where audit triggers live
- Submission-triggered audit:
  - `app/api/v1/endpoints/forms.py` in `submit_form()`.
  - Runs deterministic clinical audit when template name contains `assessment` (and auto-run flag is enabled).
- Scheduled recheck audit:
  - `app/jobs/run_clinical_audit_rechecks.py`.
  - Scans older assessment submissions and runs deterministic audits (skips items audited in last 24h).

## How prompt-to-form generation works
- Endpoint:
  - `POST /api/v1/forms/templates/{template_id}/generate`
- Permission:
  - Requires `forms:manage`.
- Behavior:
  - Draft template: generated schema updates draft in place.
  - Published template: template is cloned to new draft version, then generated schema is applied.
- Core implementation:
  - Endpoint: `app/api/v1/endpoints/forms.py`
  - Generator + validator: `app/services/form_generation.py`
- Validation rules:
  - Allowed field types: `text`, `textarea`, `number`, `select`, `checkbox`, `date`
  - Each field must include `id`, `label`, and valid `type`
  - `select` fields require non-empty string `options`

## Temporary auth note for frontend
- The API client reads bearer token in this order:
  - `localStorage.vehr_access_token`
  - `localStorage.access_token`
  - `sessionStorage.vehr_access_token`
  - `sessionStorage.access_token`
  - `vehr_access_token` or `access_token` cookie
  - `NEXT_PUBLIC_API_TOKEN` env fallback
