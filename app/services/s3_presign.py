from dataclasses import dataclass

from app.services.storage import (
    generate_presigned_get_url as _generate_presigned_get_url,
    generate_presigned_put_url as _generate_presigned_put_url,
    get_s3_settings,
)


@dataclass(frozen=True)
class PresignS3Settings:
    region: str
    bucket: str
    access_key_id: str
    secret_access_key: str
    expires_in_seconds: int


def load_presign_s3_settings() -> PresignS3Settings:
    settings = get_s3_settings()
    return PresignS3Settings(
        region=settings.region,
        bucket=settings.bucket,
        access_key_id=settings.access_key_id,
        secret_access_key=settings.secret_access_key,
        expires_in_seconds=settings.presign_expires_seconds,
    )


def get_presign_s3_client(_settings: PresignS3Settings):
    # Compatibility shim for older call sites.
    return None


def generate_presigned_put_url(
    client,
    bucket: str,
    key: str,
    content_type: str,
    expires_in: int,
) -> str:
    del client, bucket
    return _generate_presigned_put_url(key=key, content_type=content_type, expires=expires_in)


def generate_presigned_get_url(
    client,
    bucket: str,
    key: str,
    expires_in: int,
) -> str:
    del client, bucket
    return _generate_presigned_get_url(key=key, expires=expires_in)
