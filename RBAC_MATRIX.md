# RBAC Matrix (Current)

## High Privilege
- `Administrator`
  - full patient/encounter/forms/document/service/org/user/webhook management

## Low-Risk Invite Roles
- `Counselor`
  - patient/encounter/forms/documents/service read-write (no org/user admin)
- `Case Manager`
  - patient/encounter/forms/documents/service read-write (no org/user admin)

## Existing Roles
- `Clinician`
- `Therapist`
- `Medical Provider`
- `Medical Assistant`
- `Staff`
- `Billing`
- `Compliance Manager`
- `Consultant`

## Role Assignment Rules
- Invite acceptance is restricted to low-risk invite roles only.
- Admin-assigned role updates go through:
  - `PATCH /api/v1/admin/users/{user_id}/role`
- Role updates are audited (`user.role_updated`).

