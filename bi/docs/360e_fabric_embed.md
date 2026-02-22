# 360E Fabric / Power BI Embed (App-Owns-Data + RLS)

This guide covers the Phase A setup for multi-tenant Power BI embedding in 360E using:
- App-Owns-Data (service principal)
- RLS Option A: `USERNAME() = organization_id`
- Backend-issued embed tokens with effective identity

## 1) Admin prerequisites (already completed)

Confirm these are done in Fabric/Power BI tenant admin:
- Service principal API access is enabled for Power BI APIs.
- The app registration/service principal is added to the target workspace with access to reports/datasets.
- The service principal has permission to view the report and dataset.

## 2) Publish starter report + semantic model

1. In Power BI Desktop, build a starter report for chart audit.
2. Ensure the semantic model includes a tenant key that matches backend `organization_id` string values.
3. Publish to the target Fabric workspace (example: `360E Analytics`).
4. In Fabric service, verify both report and dataset are visible in that workspace.

## 3) Create RLS role `TenantRLS` (Option A)

In the semantic model:
1. Create role name: `TenantRLS`
2. Apply table filter with DAX using identity:

```DAX
[organization_id] = USERNAME()
```

Notes:
- Backend sets `username` in effective identity to the current org ID.
- Keep `organization_id` type/text formatting aligned with backend org ID values.

## 4) Discover workspace/report/dataset IDs

Run from repo root:

```bash
python bi/scripts/pbi_list_items.py --workspace-name-contains "360E Analytics"
```

Or explicitly:

```bash
python bi/scripts/pbi_list_items.py --workspace-id "<workspace-id>"
```

This prints:
- `workspaceId`
- reports (`name`, `id`, `embedUrl`)
- datasets (`name`, `id`)

Capture the IDs for `chart_audit`.

## 5) Configure backend env vars (Azure Container Apps API service only)

Set these on the backend service (do not expose in frontend env):

- `PBI_TENANT_ID`
- `PBI_CLIENT_ID`
- `PBI_CLIENT_SECRET`
- `PBI_RLS_ROLE=TenantRLS`
- `PBI_DEFAULT_WORKSPACE_ID=<workspace-id>`

The report/dataset/workspace mapping for each key is stored in DB table `bi_reports`.

## 6) Smoke test embed-token generation

Run migration, then seed/upsert the registry row:

```bash
alembic upgrade head
python -m app.scripts.seed_bi_reports
```

Optional discovery helper:

```bash
python bi/scripts/pbi_list_items.py --workspace-name-contains "360E Analytics"
```

Embed-token smoke test:

```bash
python bi/scripts/pbi_smoke_test.py
```

Expected:
- `success=True status=200 ...`

If it fails, output includes HTTP status and error detail from Power BI API.

## 7) Validate tenant isolation

1. Log in as a user in Organization 1 and open `/analytics/chart-audit`.
2. Confirm report only shows Org 1 rows.
3. Log in as a user in Organization 2 and open the same page.
4. Confirm report only shows Org 2 rows.
5. Ensure no cross-org records are visible in visuals, detail rows, or exports.

Implementation detail:
- Backend endpoint `/api/v1/bi/embed-config?report_key=chart_audit` always derives org from authenticated membership, never from request input.
