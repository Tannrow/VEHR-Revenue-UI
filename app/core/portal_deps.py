from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.portal_security import PortalSessionTokenData, decode_portal_session_token
from app.db.models.organization import Organization
from app.db.models.patient import Patient
from app.db.session import get_db


portal_auth_scheme = HTTPBearer(auto_error=False)


def get_portal_session(
    credentials: HTTPAuthorizationCredentials = Depends(portal_auth_scheme),
    db: Session = Depends(get_db),
) -> tuple[PortalSessionTokenData, Patient, Organization]:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing portal credentials",
        )

    try:
        token_data = decode_portal_session_token(credentials.credentials)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid portal token",
        )

    patient = db.get(Patient, token_data.patient_id)
    if not patient or patient.organization_id != token_data.organization_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid portal session",
        )
    organization = db.get(Organization, token_data.organization_id)
    if not organization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Organization not found",
        )
    return token_data, patient, organization
