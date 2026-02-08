# Patient Chart Spec (Phase Implementation)

## Scope
- Single patient chart per organization-scoped patient.
- Structured chart tabs:
  - Overview
  - Demographics
  - Insurance
  - Intake & Paperwork
  - Encounters
  - Notes
  - Assessments
  - Documents
  - Treatment Progress
  - History

## Core Principles
- Tenant isolation by `organization_id` from authenticated membership.
- RBAC checks on all chart APIs.
- Append-only audit events for critical state changes.
- No chart duplication across services; service context is attached via enrollments/notes.

## Data Ownership
- Episodes of Care: admit/discharge and active lifecycle.
- Encounters: service events and session containers.
- Notes: service-scoped clinical documentation with `draft -> signed` lifecycle.
- Documents/Paperwork: service-linked patient requirements and packet status.
- Treatment Progress: stage state + event history.
- Requirements: readiness/alerts engine.

## Encounter-Note Linkage
- Signed notes must be linked to an encounter.
- `POST /api/v1/notes/{note_id}/sign` auto-creates a `note_signoff` encounter when none is provided.
- Unsigned (`draft`) notes drive the `unsigned_note` patient requirement in refresh flow.

## UI Notes
- Sticky patient header shows identity, active episode, care team, and quick actions.
- Overview includes readiness checklist and alerts.
- Treatment progress uses stage chips and event timeline.
