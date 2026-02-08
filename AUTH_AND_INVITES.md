# Auth And Invites

## Invite Flow
Endpoints:
- `GET /api/v1/admin/invites`
- `POST /api/v1/admin/invites`
- `POST /api/v1/admin/invites/{id}/resend`
- `POST /api/v1/admin/invites/{id}/revoke`
- `POST /api/v1/auth/accept-invite`

Behavior:
- Admin creates invite by email.
- Invite stores hashed token and expiration.
- Invite email is sent via messaging abstraction.
- Invite acceptance allows only low-risk roles:
  - `Counselor`
  - `Case Manager`
- Higher privilege roles are admin-assigned via:
  - `PATCH /api/v1/admin/users/{user_id}/role`

## Password Management
Endpoints:
- `POST /api/v1/auth/change-password`
- `POST /api/v1/auth/request-password-reset`
- `POST /api/v1/auth/reset-password`

Behavior:
- Change password requires valid current password and active membership session.
- Password reset uses hashed one-time token with expiry.
- Reset request response is generic to avoid account enumeration.

## Audit Coverage
- `invite.created`
- `invite.resent`
- `invite.revoked`
- `invite.accepted`
- `user.role_updated`
- `password.changed`
- `password.reset`

