# Episode Of Care

## Table
`episodes_of_care`

## Fields
- `id`
- `organization_id`
- `patient_id`
- `admit_date`
- `discharge_date` (nullable)
- `referral_source`
- `reason_for_admission`
- `primary_service_category` (`intake | sud | mh | psych | cm`)
- `court_involved` (bool)
- `discharge_disposition` (nullable)
- `status` (`active | discharged`)
- `created_at`
- `updated_at`

## Rules
- Patient can have many episodes over time.
- Only one active episode per patient (enforced by API rule).
- Active episode cannot have `discharge_date`.
- Discharged episode requires `discharge_date`.
- `discharge_date >= admit_date`.

## Related Objects
- `patient_care_team`
- `patient_requirements`
- `patient_treatment_stage`
- `patient_treatment_stage_events`

