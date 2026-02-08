import os
import re
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError


@dataclass(frozen=True)
class S3Settings:
    region: str
    bucket: str
    access_key_id: str
    secret_access_key: str
    endpoint_url: str | None
    use_path_style: bool
    presign_expires_seconds: int


_SETTINGS: S3Settings | None = None
_S3_CLIENT = None
_INIT_LOCK = Lock()


def _parse_bool(raw: str, *, default: bool = False) -> bool:
    value = raw.strip().lower()
    if value == "":
        return default
    return value in {"1", "true", "yes", "on"}


def _load_settings_from_env() -> S3Settings:
    region = os.getenv("AWS_REGION", "").strip()
    bucket = os.getenv("S3_BUCKET", "").strip()
    access_key_id = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
    secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()

    missing = [
        name
        for name, value in (
            ("AWS_REGION", region),
            ("S3_BUCKET", bucket),
            ("AWS_ACCESS_KEY_ID", access_key_id),
            ("AWS_SECRET_ACCESS_KEY", secret_access_key),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing required S3 environment variables: {', '.join(missing)}")

    endpoint_url = os.getenv("S3_ENDPOINT_URL", "").strip() or None
    use_path_style = _parse_bool(os.getenv("S3_USE_PATH_STYLE", ""), default=False)
    expires_raw = os.getenv("S3_PRESIGN_EXPIRES_SECONDS", "900").strip()
    try:
        presign_expires_seconds = int(expires_raw)
    except ValueError as exc:
        raise RuntimeError("S3_PRESIGN_EXPIRES_SECONDS must be an integer") from exc
    if presign_expires_seconds <= 0:
        raise RuntimeError("S3_PRESIGN_EXPIRES_SECONDS must be greater than 0")

    return S3Settings(
        region=region,
        bucket=bucket,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        endpoint_url=endpoint_url,
        use_path_style=use_path_style,
        presign_expires_seconds=presign_expires_seconds,
    )


def init_s3() -> None:
    global _SETTINGS, _S3_CLIENT
    if _SETTINGS is not None and _S3_CLIENT is not None:
        return
    with _INIT_LOCK:
        if _SETTINGS is not None and _S3_CLIENT is not None:
            return
        settings = _load_settings_from_env()
        config = Config(s3={"addressing_style": "path"}) if settings.use_path_style else None
        client = boto3.client(
            "s3",
            region_name=settings.region,
            endpoint_url=settings.endpoint_url,
            aws_access_key_id=settings.access_key_id,
            aws_secret_access_key=settings.secret_access_key,
            config=config,
        )
        _SETTINGS = settings
        _S3_CLIENT = client


def get_s3_settings() -> S3Settings:
    init_s3()
    assert _SETTINGS is not None
    return _SETTINGS


def _get_s3_client():
    init_s3()
    assert _S3_CLIENT is not None
    return _S3_CLIENT


def should_validate_s3_on_startup() -> bool:
    return _parse_bool(os.getenv("S3_VALIDATE_ON_STARTUP", ""), default=False)


def validate_s3_connection() -> None:
    settings = get_s3_settings()
    client = _get_s3_client()
    try:
        client.head_bucket(Bucket=settings.bucket)
    except (ClientError, BotoCoreError) as exc:
        raise RuntimeError(
            f"S3 startup validation failed for bucket '{settings.bucket}' in region '{settings.region}': {exc}"
        ) from exc


def sanitize_filename(filename: str) -> str:
    safe_name = Path(filename).name
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", safe_name)
    if not safe_name:
        return "file"
    return safe_name[:180]


def _sanitize_resource(resource: str) -> str:
    cleaned = resource.strip().strip("/")
    if not cleaned:
        raise ValueError("resource must not be empty")
    if "/" in cleaned:
        raise ValueError("resource must be a single segment")
    normalized = re.sub(r"[^A-Za-z0-9._-]", "_", cleaned)
    if not normalized:
        raise ValueError("resource contains no valid characters")
    return normalized


def build_object_key(
    *,
    organization_id: str,
    resource: str,
    filename: str,
    object_id: str | None = None,
) -> str:
    # Enforce tenant-scoped keys: organization_id/resource/uuid/filename
    org = organization_id.strip()
    if not org:
        raise ValueError("organization_id must not be empty")
    key_resource = _sanitize_resource(resource)
    key_object_id = object_id.strip() if object_id else str(uuid4())
    if not key_object_id:
        raise ValueError("object_id must not be empty")
    safe_name = sanitize_filename(filename)
    return f"{org}/{key_resource}/{key_object_id}/{safe_name}"


def upload_fileobj(
    file_obj=None,
    *,
    key: str,
    content_type: str | None = None,
    fileobj=None,
) -> None:
    # Backward-compatible alias: older call sites may still pass fileobj=...
    if file_obj is None:
        file_obj = fileobj
    if file_obj is None:
        raise ValueError("file_obj is required")

    settings = get_s3_settings()
    client = _get_s3_client()
    extra_args: dict[str, str] = {}
    if content_type:
        extra_args["ContentType"] = content_type
    # Never set ACLs here; object access is controlled by IAM/bucket policy.
    if extra_args:
        client.upload_fileobj(file_obj, settings.bucket, key, ExtraArgs=extra_args)
    else:
        client.upload_fileobj(file_obj, settings.bucket, key)


def delete_object(key: str) -> None:
    settings = get_s3_settings()
    client = _get_s3_client()
    client.delete_object(Bucket=settings.bucket, Key=key)


def generate_presigned_put_url(key: str, content_type: str, expires: int = 900) -> str:
    settings = get_s3_settings()
    client = _get_s3_client()
    return client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.bucket,
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=expires,
        HttpMethod="PUT",
    )


def generate_presigned_get_url(key: str, expires: int = 900) -> str:
    settings = get_s3_settings()
    client = _get_s3_client()
    return client.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": settings.bucket,
            "Key": key,
        },
        ExpiresIn=expires,
        HttpMethod="GET",
    )
