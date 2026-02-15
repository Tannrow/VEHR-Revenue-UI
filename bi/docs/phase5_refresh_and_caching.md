# Phase 5: Analytics Refresh + Performance

This phase improves analytics reliability/performance by:

- Precomputing select KPIs via Postgres materialized views.
- Adding a refresh + sync job to populate the governed KPI tables (`rpt_kpi_daily`).
- Adding short-TTL, tenant-safe caching for:
  - `GET /api/v1/bi/embed-config`
  - `GET /api/v1/analytics/query`

## 1) Materialized Views (Postgres)

Migration: `alembic/versions/605c0b84d71e_add_reporting_materialized_views.py`

Objects created (Postgres only):

- Schema: `reporting`
- Materialized view: `reporting.mv_kpi_daily_core`
  - Emits rows shaped like `rpt_kpi_daily` for a small set of “core” metrics:
    - `encounters_week` (daily encounter counts from `encounters`)
    - `new_admissions_week` (daily admits from `episodes_of_care`)
    - `discharges_week` (daily discharges from `episodes_of_care`)
  - Created with `WITH NO DATA` (first refresh must be non-concurrent).
- Indexes:
  - `ux_reporting_mv_kpi_daily_core` (required to support `REFRESH ... CONCURRENTLY`)
  - Supporting table indexes to speed refresh:
    - `ix_encounters_org_start_time`
    - `ix_episodes_of_care_org_admit_date`
    - `ix_episodes_of_care_org_discharge_date`

Notes:

- SQLite dev environments do not get materialized views; analytics continues to rely on the KPI tables.

## 2) Refresh + Sync Job (Nightly + On-Demand)

Entrypoint:

- `python -m app.scripts.refresh_analytics_materializations`

What it does:

1. Refreshes `reporting.mv_kpi_daily_core`.
   - If the MV is not populated yet, it runs an initial (non-concurrent) refresh.
   - Otherwise uses `REFRESH MATERIALIZED VIEW CONCURRENTLY ...`.
   - Uses a Postgres advisory lock to prevent overlapping runs.
2. Syncs MV output into `rpt_kpi_daily` by:
   - Deleting only the “total” rows (all dimension IDs null) for the materialized metric keys.
   - Bulk inserting the refreshed totals back into `rpt_kpi_daily`.

Flags:

- `--no-refresh` to skip refreshing the materialized view (sync only).
- `--no-sync` to skip syncing into KPI tables (refresh only).
- `--batch-size 1000` controls insert batching.

### Scheduling on Render

Use Render’s “Cron Job” feature (recommended):

1. Create a new Cron Job in Render.
2. Point it at the same repo/Dockerfile as the API service.
3. Command:
   - `python -m app.scripts.refresh_analytics_materializations`
4. Schedule:
   - Nightly (example): `0 3 * * *` (3:00 AM UTC)
5. Ensure env vars match the API service (at minimum `DATABASE_URL`).

### Observability

The job logs:

- per-view refresh duration
- KPI sync delete/insert counts + duration
- failures (stack traces)

## 3) Tenant-Safe Short-TTL Caching

### A) `GET /api/v1/bi/embed-config`

Location: `app/api/v1/endpoints/bi.py`

- Cache: in-memory TTL+LRU (`app/services/ttl_cache.py`)
- TTL:
  - up to 10 minutes
  - additionally capped to `expiresOn - 2 minutes` to avoid serving near-expiry tokens
- Cache key includes:
  - `organization_id`
  - `report_key`
  - `workspace_id`, `report_id`, `dataset_id`, `rls_role`
- Failures are not cached.

### B) `GET /api/v1/analytics/query`

Location: `app/api/v1/endpoints/analytics.py`

- Cache: in-memory TTL+LRU
- TTL: 60 seconds
- Cache key includes:
  - `organization_id`
  - normalized role key
  - `metric_key`, grain, backing_table
  - all filters: `start`, `end`, `facility_id`, `program_id`, `provider_id`, `payer_id`
- Failures are not cached.

### Cache bypass (debug)

Header:

- `x-cache-bypass: 1`

Guard:

- Only privileged roles (`admin`, `office_manager`, `sud_supervisor`) are allowed to bypass.

### Important limitation

This cache is **per-instance**. If the API runs multiple instances, hit rates may be lower, but correctness and tenant isolation remain intact.

## 4) Power BI Incremental Refresh (Authoring Checklist)

Manual authoring checklist (no code changes required):

1. In Power BI Desktop, create parameters:
   - `RangeStart` (DateTime)
   - `RangeEnd` (DateTime)
2. For import-mode fact tables, filter a DateTime column:
   - `fact[DateTime] >= RangeStart && fact[DateTime] < RangeEnd`
3. In the model, configure incremental refresh:
   - Store: X months/years
   - Refresh: last Y days
4. Publish to the workspace and validate in Power BI Service:
   - Confirm partitions are created
   - Trigger a refresh and verify only recent partitions refresh
5. RLS validation still applies:
   - Use “View as” in Desktop and embedded token tests in app.

