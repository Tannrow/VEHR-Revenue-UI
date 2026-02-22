# 360E Phase 3: Enterprise Semantic Model + Analytics UX

## 1) Star Schema Design

### Core principles
- Grain-first fact modeling.
- Single-direction filtering from dimensions to facts.
- Tenant isolation enforced in every fact and dimension with `tenant_id`.
- Monday-based week intelligence through `dim_date[WeekStartDate]`.
- Hide technical keys in the Power BI model and expose business-friendly fields.

### Dimensions

#### `dim_date`
- `Date` (PK, date)
- `Year` (int)
- `Quarter` (text/int)
- `MonthNumber` (int)
- `MonthName` (text)
- `WeekStartDate` (date, Monday)
- `DayOfWeek` (int/text, Monday=1)
- `IsWeekend` (bool)

#### `dim_patient`
- `patient_id` (UUID PK)
- `tenant_id` (text/UUID)
- `mrn` (text)
- `first_name` (text)
- `last_name` (text)
- `dob` (date)
- `sex` (text)
- `status` (text)
- `age` (calculated column)
- `age_group` (calculated column)

#### `dim_staff`
- `staff_id` (UUID PK)
- `tenant_id` (text/UUID)
- `display_name` (text)
- `role` (text)
- `status` (text)

#### `dim_program`
- `program_key` (text PK)
- `tenant_id` (text/UUID)
- `program_name` (text)
- `program_type` (text)
- `status` (text)

#### `dim_facility`
- `facility_id` (UUID/text PK)
- `tenant_id` (text/UUID)
- `facility_name` (text)
- `city` (text)
- `state` (text)
- `status` (text)

### Facts

#### `fact_encounters` (grain: one encounter)
- `encounter_id`
- `tenant_id`
- `patient_id`
- `staff_id`
- `program_key`
- `facility_id`
- `occurred_date`
- `encounter_type`
- `status`
- `encounter_count` (fixed `1`)

#### `fact_claims` (grain: one claim)
- `claim_id`
- `tenant_id`
- `patient_id`
- `program_key`
- `facility_id`
- `payer_name`
- `claim_status`
- `service_date`
- `total_charge`
- `total_paid`

#### `fact_payments` (grain: one payment transaction)
- `payment_id`
- `tenant_id`
- `claim_id`
- `patient_id`
- `paid_date`
- `amount`

#### `fact_compliance` (grain: one finding)
- `finding_id`
- `tenant_id`
- `patient_id`
- `staff_id`
- `program_key`
- `facility_id`
- `finding_date`
- `finding_type`
- `severity`
- `unsigned_flag`

#### `fact_productivity` (grain: one staff/day/program/facility work entry)
- `time_entry_id`
- `tenant_id`
- `staff_id`
- `facility_id`
- `program_key`
- `work_date`
- `minutes_logged`
- `encounters_count`

### Relationships (single direction)
- `dim_date[Date] -> fact_encounters[occurred_date]`
- `dim_date[Date] -> fact_claims[service_date]`
- `dim_date[Date] -> fact_payments[paid_date]`
- `dim_date[Date] -> fact_compliance[finding_date]`
- `dim_date[Date] -> fact_productivity[work_date]`
- `dim_patient[patient_id] -> fact_*[patient_id]`
- `dim_staff[staff_id] -> fact_encounters[staff_id]`, `fact_compliance[staff_id]`, `fact_productivity[staff_id]`
- `dim_program[program_key] -> fact_*[program_key]`
- `dim_facility[facility_id] -> fact_*[facility_id]`

## 2) Standardized DAX Measure Pack (30)

Use measure folders:
- `[Clinical]`
- `[Revenue]`
- `[Operations]`
- `[Compliance]`
- `[Executive]`

### Reusable time helper pattern (Monday-start week)
```DAX
VAR AnchorDate = MAX(dim_date[Date])
VAR WeekStart = AnchorDate - WEEKDAY(AnchorDate, 2) + 1
VAR WeekEnd = WeekStart + 6
```

### [Clinical]
```DAX
KPI - Encounters (Daily) =
COALESCE(SUM(fact_encounters[encounter_count]), 0)

KPI - Encounters (Week) =
VAR AnchorDate = MAX(dim_date[Date])
VAR WeekStart = AnchorDate - WEEKDAY(AnchorDate, 2) + 1
RETURN
COALESCE(
    CALCULATE([KPI - Encounters (Daily)], DATESBETWEEN(dim_date[Date], WeekStart, WeekStart + 6)),
    0
)

KPI - Unique Clients Seen (Week) =
VAR AnchorDate = MAX(dim_date[Date])
VAR WeekStart = AnchorDate - WEEKDAY(AnchorDate, 2) + 1
RETURN
COALESCE(
    CALCULATE(DISTINCTCOUNT(fact_encounters[patient_id]), DATESBETWEEN(dim_date[Date], WeekStart, WeekStart + 6)),
    0
)

KPI - Active Census =
COALESCE(
    CALCULATE(DISTINCTCOUNT(dim_patient[patient_id]), dim_patient[status] = "active"),
    0
)

KPI - New Admissions (Week) =
VAR AnchorDate = MAX(dim_date[Date])
VAR WeekStart = AnchorDate - WEEKDAY(AnchorDate, 2) + 1
RETURN
COALESCE(
    CALCULATE(
        COUNTROWS(fact_encounters),
        fact_encounters[encounter_type] = "admission",
        DATESBETWEEN(dim_date[Date], WeekStart, WeekStart + 6)
    ),
    0
)

KPI - Discharges (Week) =
VAR AnchorDate = MAX(dim_date[Date])
VAR WeekStart = AnchorDate - WEEKDAY(AnchorDate, 2) + 1
RETURN
COALESCE(
    CALCULATE(
        COUNTROWS(fact_encounters),
        fact_encounters[encounter_type] = "discharge",
        DATESBETWEEN(dim_date[Date], WeekStart, WeekStart + 6)
    ),
    0
)

KPI - Completed Encounters (Week) =
VAR AnchorDate = MAX(dim_date[Date])
VAR WeekStart = AnchorDate - WEEKDAY(AnchorDate, 2) + 1
RETURN
COALESCE(
    CALCULATE(
        COUNTROWS(fact_encounters),
        fact_encounters[status] = "completed",
        DATESBETWEEN(dim_date[Date], WeekStart, WeekStart + 6)
    ),
    0
)

KPI - No Shows (Week) =
VAR AnchorDate = MAX(dim_date[Date])
VAR WeekStart = AnchorDate - WEEKDAY(AnchorDate, 2) + 1
RETURN
COALESCE(
    CALCULATE(
        COUNTROWS(fact_encounters),
        fact_encounters[status] = "no_show",
        DATESBETWEEN(dim_date[Date], WeekStart, WeekStart + 6)
    ),
    0
)

KPI - Attendance Rate (Week) =
DIVIDE([KPI - Completed Encounters (Week)], [KPI - Encounters (Week)], 0)

KPI - No Show Rate (Week) =
DIVIDE([KPI - No Shows (Week)], [KPI - Encounters (Week)], 0)
```

### [Revenue]
```DAX
KPI - Charges =
COALESCE(SUM(fact_claims[total_charge]), 0)

KPI - Paid =
COALESCE(SUM(fact_claims[total_paid]), 0)

KPI - Charges (Week) =
VAR AnchorDate = MAX(dim_date[Date])
VAR WeekStart = AnchorDate - WEEKDAY(AnchorDate, 2) + 1
RETURN
COALESCE(CALCULATE([KPI - Charges], DATESBETWEEN(dim_date[Date], WeekStart, WeekStart + 6)), 0)

KPI - Paid (Week) =
VAR AnchorDate = MAX(dim_date[Date])
VAR WeekStart = AnchorDate - WEEKDAY(AnchorDate, 2) + 1
RETURN
COALESCE(CALCULATE([KPI - Paid], DATESBETWEEN(dim_date[Date], WeekStart, WeekStart + 6)), 0)

KPI - Claims Submitted (Week) =
VAR AnchorDate = MAX(dim_date[Date])
VAR WeekStart = AnchorDate - WEEKDAY(AnchorDate, 2) + 1
RETURN
COALESCE(
    CALCULATE(
        COUNTROWS(fact_claims),
        fact_claims[claim_status] IN {"submitted", "paid", "denied"},
        DATESBETWEEN(dim_date[Date], WeekStart, WeekStart + 6)
    ),
    0
)

KPI - Claims Paid (Week) =
VAR AnchorDate = MAX(dim_date[Date])
VAR WeekStart = AnchorDate - WEEKDAY(AnchorDate, 2) + 1
RETURN
COALESCE(
    CALCULATE(
        COUNTROWS(fact_claims),
        fact_claims[claim_status] = "paid",
        DATESBETWEEN(dim_date[Date], WeekStart, WeekStart + 6)
    ),
    0
)

KPI - Denials (Week) =
VAR AnchorDate = MAX(dim_date[Date])
VAR WeekStart = AnchorDate - WEEKDAY(AnchorDate, 2) + 1
RETURN
COALESCE(
    CALCULATE(
        COUNTROWS(fact_claims),
        fact_claims[claim_status] = "denied",
        DATESBETWEEN(dim_date[Date], WeekStart, WeekStart + 6)
    ),
    0
)

KPI - Denial Rate (Week) =
DIVIDE([KPI - Denials (Week)], [KPI - Claims Submitted (Week)], 0)

KPI - Collections Rate (Week) =
DIVIDE([KPI - Paid (Week)], [KPI - Charges (Week)], 0)

KPI - AR Balance Total =
COALESCE(SUMX(fact_claims, fact_claims[total_charge] - fact_claims[total_paid]), 0)

KPI - AR Over 30 =
COALESCE(CALCULATE([KPI - AR Balance Total], FILTER(ALL(dim_date[Date]), dim_date[Date] <= TODAY() - 30)), 0)

KPI - AR Over 60 =
COALESCE(CALCULATE([KPI - AR Balance Total], FILTER(ALL(dim_date[Date]), dim_date[Date] <= TODAY() - 60)), 0)

KPI - AR Over 90 =
COALESCE(CALCULATE([KPI - AR Balance Total], FILTER(ALL(dim_date[Date]), dim_date[Date] <= TODAY() - 90)), 0)
```

### [Operations]
```DAX
KPI - Minutes Logged (Week) =
VAR AnchorDate = MAX(dim_date[Date])
VAR WeekStart = AnchorDate - WEEKDAY(AnchorDate, 2) + 1
RETURN
COALESCE(
    CALCULATE(SUM(fact_productivity[minutes_logged]), DATESBETWEEN(dim_date[Date], WeekStart, WeekStart + 6)),
    0
)

KPI - Productivity Encounters (Week) =
VAR AnchorDate = MAX(dim_date[Date])
VAR WeekStart = AnchorDate - WEEKDAY(AnchorDate, 2) + 1
RETURN
COALESCE(
    CALCULATE(SUM(fact_productivity[encounters_count]), DATESBETWEEN(dim_date[Date], WeekStart, WeekStart + 6)),
    0
)

KPI - Encounters per 60 Minutes (Week) =
DIVIDE([KPI - Productivity Encounters (Week)], DIVIDE([KPI - Minutes Logged (Week)], 60, 0), 0)

KPI - Avg Encounters per Staff (Week) =
DIVIDE([KPI - Productivity Encounters (Week)], DISTINCTCOUNT(dim_staff[staff_id]), 0)
```

### [Compliance]
```DAX
KPI - Unsigned Notes Over 24h =
COALESCE(
    CALCULATE(COUNTROWS(fact_compliance), fact_compliance[finding_type] = "unsigned_note_24h"),
    0
)

KPI - Unsigned Notes Over 72h =
COALESCE(
    CALCULATE(COUNTROWS(fact_compliance), fact_compliance[finding_type] = "unsigned_note_72h"),
    0
)

KPI - Audit Findings (Week) =
VAR AnchorDate = MAX(dim_date[Date])
VAR WeekStart = AnchorDate - WEEKDAY(AnchorDate, 2) + 1
RETURN
COALESCE(CALCULATE(COUNTROWS(fact_compliance), DATESBETWEEN(dim_date[Date], WeekStart, WeekStart + 6)), 0)

KPI - High Severity Findings (Week) =
VAR AnchorDate = MAX(dim_date[Date])
VAR WeekStart = AnchorDate - WEEKDAY(AnchorDate, 2) + 1
RETURN
COALESCE(
    CALCULATE(
        COUNTROWS(fact_compliance),
        fact_compliance[severity] IN {"high", "critical"},
        DATESBETWEEN(dim_date[Date], WeekStart, WeekStart + 6)
    ),
    0
)

KPI - Staff Compliance Score =
VAR Findings = [KPI - Audit Findings (Week)]
VAR HighFindings = [KPI - High Severity Findings (Week)]
RETURN
MAX(0, 100 - (Findings * 2) - (HighFindings * 5))
```

### [Executive]
```DAX
KPI - Net Revenue (Week) =
[KPI - Paid (Week)] - ([KPI - Charges (Week)] - [KPI - Paid (Week)])

KPI - Compliance Risk Index =
DIVIDE([KPI - High Severity Findings (Week)] * 2 + [KPI - Unsigned Notes Over 72h], [KPI - Active Census], 0)
```

### Metric key mapping
- `active_clients` -> `KPI - Active Census`
- `new_admissions_week` -> `KPI - New Admissions (Week)`
- `discharges_week` -> `KPI - Discharges (Week)`
- `attendance_rate_week` -> `KPI - Attendance Rate (Week)`
- `no_show_rate_week` -> `KPI - No Show Rate (Week)`
- `encounters_week` -> `KPI - Encounters (Week)`
- `charges_week` -> `KPI - Charges (Week)`
- `claims_submitted_week` -> `KPI - Claims Submitted (Week)`
- `claims_paid_week` -> `KPI - Claims Paid (Week)`
- `denial_rate_week` -> `KPI - Denial Rate (Week)`
- `ar_balance_total` -> `KPI - AR Balance Total`
- `ar_over_30` -> `KPI - AR Over 30`
- `ar_over_60` -> `KPI - AR Over 60`
- `ar_over_90` -> `KPI - AR Over 90`
- `unsigned_notes_over_24h` -> `KPI - Unsigned Notes Over 24h`
- `unsigned_notes_over_72h` -> `KPI - Unsigned Notes Over 72h`

## 3) RLS Role: `TenantRLS`

### Identity contract
- `USERNAME()` / `USERPRINCIPALNAME()` carries `tenant_id` (existing app-owns-data behavior).
- `CUSTOMDATA()` carries optional scope in fixed format:
  - `role|staff_id|facility_id|program_key`
  - Use `*` for unrestricted values.
  - Example admin: `admin|*|*|*`
  - Example clinician: `clinician|a3...staff-uuid|facility-uuid|program_key`

### RLS filters (DAX)

#### `dim_patient`
```DAX
[tenant_id] = USERPRINCIPALNAME()
```

#### `dim_staff`
```DAX
VAR TenantOk = [tenant_id] = USERPRINCIPALNAME()
VAR ScopeRole = LOWER(PATHITEM(CUSTOMDATA(), 1, TEXT))
VAR ScopeStaff = PATHITEM(CUSTOMDATA(), 2, TEXT)
RETURN
TenantOk &&
(
    ScopeRole <> "clinician" ||
    ScopeStaff = "*" ||
    FORMAT([staff_id], "") = ScopeStaff
)
```

#### `fact_encounters`
```DAX
VAR TenantOk = [tenant_id] = USERPRINCIPALNAME()
VAR ScopeRole = LOWER(PATHITEM(CUSTOMDATA(), 1, TEXT))
VAR ScopeStaff = PATHITEM(CUSTOMDATA(), 2, TEXT)
VAR ScopeFacility = PATHITEM(CUSTOMDATA(), 3, TEXT)
VAR ScopeProgram = PATHITEM(CUSTOMDATA(), 4, TEXT)
RETURN
TenantOk &&
(ScopeRole <> "clinician" || ScopeStaff = "*" || FORMAT([staff_id], "") = ScopeStaff) &&
(ScopeFacility = "*" || FORMAT([facility_id], "") = ScopeFacility) &&
(ScopeProgram = "*" || [program_key] = ScopeProgram)
```

#### `fact_claims`
```DAX
VAR TenantOk = [tenant_id] = USERPRINCIPALNAME()
VAR ScopeFacility = PATHITEM(CUSTOMDATA(), 3, TEXT)
VAR ScopeProgram = PATHITEM(CUSTOMDATA(), 4, TEXT)
RETURN
TenantOk &&
(ScopeFacility = "*" || FORMAT([facility_id], "") = ScopeFacility) &&
(ScopeProgram = "*" || [program_key] = ScopeProgram)
```

#### `fact_payments`
```DAX
[tenant_id] = USERPRINCIPALNAME()
```

#### `fact_compliance`
```DAX
VAR TenantOk = [tenant_id] = USERPRINCIPALNAME()
VAR ScopeRole = LOWER(PATHITEM(CUSTOMDATA(), 1, TEXT))
VAR ScopeStaff = PATHITEM(CUSTOMDATA(), 2, TEXT)
VAR ScopeFacility = PATHITEM(CUSTOMDATA(), 3, TEXT)
VAR ScopeProgram = PATHITEM(CUSTOMDATA(), 4, TEXT)
RETURN
TenantOk &&
(ScopeRole <> "clinician" || ScopeStaff = "*" || FORMAT([staff_id], "") = ScopeStaff) &&
(ScopeFacility = "*" || FORMAT([facility_id], "") = ScopeFacility) &&
(ScopeProgram = "*" || [program_key] = ScopeProgram)
```

#### `fact_productivity`
```DAX
VAR TenantOk = [tenant_id] = USERPRINCIPALNAME()
VAR ScopeRole = LOWER(PATHITEM(CUSTOMDATA(), 1, TEXT))
VAR ScopeStaff = PATHITEM(CUSTOMDATA(), 2, TEXT)
VAR ScopeFacility = PATHITEM(CUSTOMDATA(), 3, TEXT)
VAR ScopeProgram = PATHITEM(CUSTOMDATA(), 4, TEXT)
RETURN
TenantOk &&
(ScopeRole <> "clinician" || ScopeStaff = "*" || FORMAT([staff_id], "") = ScopeStaff) &&
(ScopeFacility = "*" || FORMAT([facility_id], "") = ScopeFacility) &&
(ScopeProgram = "*" || [program_key] = ScopeProgram)
```

### RLS validation checklist
1. Power BI Desktop:
   - Model view -> Manage roles -> `TenantRLS`.
   - `View as` tenant-only admin context.
   - `View as` clinician with staff scope.
2. Fabric workspace:
   - Confirm dataset publishes with role intact.
   - Confirm service principal retains workspace Member/Admin access.
3. Embedded token test:
   - Validate token identity username equals tenant UUID.
   - Validate `customData` format for scoped users.
   - Compare Org 1 vs Org 2 visible totals and row counts.

## 4) Flagship Dashboard Blueprint

### 1) Executive Overview (`exec_overview`)
- KPI strip: active census, encounters week, charges week, compliance risk index.
- 30-day trend: encounters, paid, findings on dual-axis.
- Revenue by payer: stacked bar.
- Compliance risk summary: high/critical findings and unsigned notes.
- Drill-through target: Program detail page.

### 2) Revenue Cycle (`revenue_cycle`)
- Charges vs paid trend (daily line).
- Denial rate (week + trend).
- AR aging buckets (`0-30`, `31-60`, `61-90`, `90+`).
- Top denial reasons (when reason field available).
- Payer performance matrix.

### 3) Clinical Delivery (`clinical_delivery`)
- Encounters by level of care/program.
- Unique clients seen.
- Productivity by provider (`encounters per 60 minutes`).
- Attendance/no-show panel (placeholder-safe).

### 4) Compliance & Risk (`compliance_risk`)
- Unsigned notes over 24h/72h.
- Missing documentation queue counts.
- Findings by severity trend.
- Staff compliance scorecard.

### Standard slicers (all reports)
- Date
- Facility
- Program
- Provider
- Payer

## 5) Analytics UI refinement (Next.js)

- Applied to `frontend/app/(app)/analytics/[reportKey]/page.tsx`.
- Friendly report title mapping implemented.
- Removed raw `report_key` display.
- Added premium header:
  - white surface
  - bottom border
  - centered `max-w-7xl`
  - title + "Analytics Suite" subtitle
  - right-side actions: `Refresh`, `Ask EI`
- Content wrapper:
  - `mx-auto max-w-7xl px-6 py-8`
- Page shell:
  - `min-h-screen bg-slate-50`
- Embed logic untouched.

## 6) BI report registration

Registration keys defined in `app/services/bi_registry.py`:
- `exec_overview`
- `revenue_cycle`
- `clinical_delivery`
- `compliance_risk`

Expected env variables:
- `PBI_WORKSPACE_ID_EXEC_OVERVIEW`
- `PBI_REPORT_ID_EXEC_OVERVIEW`
- `PBI_DATASET_ID_EXEC_OVERVIEW`
- `PBI_WORKSPACE_ID_REVENUE_CYCLE`
- `PBI_REPORT_ID_REVENUE_CYCLE`
- `PBI_DATASET_ID_REVENUE_CYCLE`
- `PBI_WORKSPACE_ID_CLINICAL_DELIVERY`
- `PBI_REPORT_ID_CLINICAL_DELIVERY`
- `PBI_DATASET_ID_CLINICAL_DELIVERY`
- `PBI_WORKSPACE_ID_COMPLIANCE_RISK`
- `PBI_REPORT_ID_COMPLIANCE_RISK`
- `PBI_DATASET_ID_COMPLIANCE_RISK`

Notes:
- `rls_role` uses `PBI_RLS_ROLE` and defaults to `TenantRLS`.
- Missing report/dataset IDs are skipped safely during seeding.
- Seed command:
  - `python -m app.scripts.seed_bi_reports`

## 7) Implementation checklist

1. Build semantic model tables/views and backfill from operational sources.
2. Publish dataset + create measure folders and standardized measures.
3. Configure `TenantRLS` role in Desktop and publish.
4. Set new report/dataset/workspace env vars in Azure Container Apps.
5. Run BI report seeding:
   - `python -m app.scripts.seed_bi_reports`
6. Validate `/api/v1/bi/reports` returns all enabled keys.
7. Validate `/analytics/<reportKey>` rendering and token refresh behavior.
8. Verify Org 1 vs Org 2 isolation in embedded reports.
9. Add visual regression snapshots for each flagship report route.
