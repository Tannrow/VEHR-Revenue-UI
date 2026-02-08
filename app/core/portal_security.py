import os
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from secrets import randbelow

from jose import JWTError, jwt
from pydantic import BaseModel

from app.core.security import JWT_ALGORITHM, JWT_SECRET


PORTAL_MAGIC_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("PORTAL_MAGIC_TOKEN_EXPIRE_MINUTES", "60"),
)
PORTAL_SESSION_EXPIRE_MINUTES = int(
    os.getenv("PORTAL_SESSION_EXPIRE_MINUTES", "720"),
)


class PortalMagicTokenData(BaseModel):
    patient_id: str
    organization_id: str
    access_code_id: str


class PortalSessionTokenData(BaseModel):
    patient_id: str
    organization_id: str


def generate_portal_code() -> str:
    # 6-digit numeric code is easy to relay via SMS or call center.
    return f"{randbelow(1_000_000):06d}"


def hash_portal_code(code: str) -> str:
    return sha256(code.strip().encode("utf-8")).hexdigest()


def create_portal_magic_token(
    *,
    patient_id: str,
    organization_id: str,
    access_code_id: str,
    expires_delta: timedelta | None = None,
) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=PORTAL_MAGIC_TOKEN_EXPIRE_MINUTES)
    )
    payload = {
        "sub": patient_id,
        "org_id": organization_id,
        "access_code_id": access_code_id,
        "token_type": "portal_magic",
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_portal_magic_token(token: str) -> PortalMagicTokenData:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        raise ValueError("Invalid magic token") from exc

    if payload.get("token_type") != "portal_magic":
        raise ValueError("Invalid magic token type")

    patient_id = payload.get("sub")
    organization_id = payload.get("org_id")
    access_code_id = payload.get("access_code_id")
    if not patient_id or not organization_id or not access_code_id:
        raise ValueError("Invalid magic token payload")

    return PortalMagicTokenData(
        patient_id=patient_id,
        organization_id=organization_id,
        access_code_id=access_code_id,
    )


def create_portal_session_token(
    *,
    patient_id: str,
    organization_id: str,
    expires_delta: timedelta | None = None,
) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=PORTAL_SESSION_EXPIRE_MINUTES)
    )
    payload = {
        "sub": patient_id,
        "org_id": organization_id,
        "token_type": "portal_session",
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_portal_session_token(token: str) -> PortalSessionTokenData:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        raise ValueError("Invalid portal session token") from exc

    if payload.get("token_type") != "portal_session":
        raise ValueError("Invalid portal session token type")

    patient_id = payload.get("sub")
    organization_id = payload.get("org_id")
    if not patient_id or not organization_id:
        raise ValueError("Invalid portal session token payload")

    return PortalSessionTokenData(
        patient_id=patient_id,
        organization_id=organization_id,
    )
