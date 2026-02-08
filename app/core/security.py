import os
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel


JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# bcrypt only uses the first 72 bytes of a password.
# Validate length up front so we do not silently truncate credentials.
BCRYPT_MAX_PASSWORD_BYTES = 72


class TokenData(BaseModel):
    user_id: str
    organization_id: str


def _validate_bcrypt_password_length(password: str) -> None:
    if len(password.encode("utf-8")) > BCRYPT_MAX_PASSWORD_BYTES:
        raise ValueError(
            f"Password exceeds bcrypt limit of {BCRYPT_MAX_PASSWORD_BYTES} UTF-8 bytes",
        )


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        _validate_bcrypt_password_length(plain_password)
    except ValueError:
        return False
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    _validate_bcrypt_password_length(password)
    return pwd_context.hash(password)


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> TokenData:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        raise ValueError("Invalid token") from exc

    user_id = payload.get("sub")
    organization_id = payload.get("org_id")
    if not user_id or not organization_id:
        raise ValueError("Invalid token payload")
    return TokenData(user_id=user_id, organization_id=organization_id)
