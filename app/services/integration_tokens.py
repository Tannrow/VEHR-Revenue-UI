import base64
import hashlib
import os

from cryptography.fernet import Fernet


class TokenEncryptionError(RuntimeError):
    pass


def _fernet_key_from_env() -> bytes:
    raw_key = os.getenv("INTEGRATION_TOKEN_KEY", "").strip()
    if not raw_key:
        raise TokenEncryptionError("INTEGRATION_TOKEN_KEY is missing")

    try:
        decoded = base64.urlsafe_b64decode(raw_key.encode("utf-8"))
        if len(decoded) == 32:
            return raw_key.encode("utf-8")
    except Exception:
        pass

    # Backward-compatible fallback: derive a stable 32-byte key from any secret string.
    derived = hashlib.sha256(raw_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(derived)


def encrypt_token(token: str) -> str:
    if not token:
        raise TokenEncryptionError("Token value is required")

    try:
        fernet = Fernet(_fernet_key_from_env())
        return fernet.encrypt(token.encode("utf-8")).decode("utf-8")
    except TokenEncryptionError:
        raise
    except Exception as exc:
        raise TokenEncryptionError(f"Unable to encrypt token: {exc}") from exc


def decrypt_token(token_encrypted: str) -> str:
    if not token_encrypted:
        raise TokenEncryptionError("Encrypted token value is required")

    try:
        fernet = Fernet(_fernet_key_from_env())
        return fernet.decrypt(token_encrypted.encode("utf-8")).decode("utf-8")
    except TokenEncryptionError:
        raise
    except Exception as exc:
        raise TokenEncryptionError(f"Unable to decrypt token: {exc}") from exc
