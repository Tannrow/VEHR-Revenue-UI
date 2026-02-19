from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status, UploadFile
from openai import AzureOpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models.revenue_era import (
    RevenueEraClaimLine,
    RevenueEraExtractResult,
    RevenueEraFile,
    RevenueEraProcessingLog,
    RevenueEraStructuredResult,
    RevenueEraWorkItem,
)
from app.services.audit import log_event
from app.services.storage import sanitize_filename


STATUS_UPLOADED = "UPLOADED"
STATUS_EXTRACTED = "EXTRACTED"
STATUS_STRUCTURED = "STRUCTURED"
STATUS_NORMALIZED = "NORMALIZED"
STATUS_ERROR = "ERROR"

MATCH_UNMATCHED = "UNMATCHED"
MATCH_MATCHED = "MATCHED"
MATCH_AMBIGUOUS = "AMBIGUOUS"

WORKITEM_OPEN = "OPEN"
WORKITEM_TYPE_UNMATCHED = "UNMATCHED_PAYMENT"
WORKITEM_TYPE_DENIAL = "DENIAL"
WORKITEM_TYPE_UNDERPAYMENT = "UNDERPAYMENT"
WORKITEM_TYPE_RECOUPMENT = "RECOUPMENT"
WORKITEM_TYPE_REVIEW = "REVIEW_REQUIRED"

PROMPT_VERSION = "era_structured_v1"

_ALLOWED_PDF_TYPES = {"application/pdf", "application/octet-stream"}
_FORBIDDEN_PHI_KEYS = {
    "patient",
    "patient_name",
    "patient_id",
    "member",
    "member_name",
    "member_id",
    "subscriber_name",
    "dob",
    "date_of_birth",
    "ssn",
}


def summarize_validation_error(exc: ValidationError) -> str:
    parts: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(segment) for segment in err.get("loc", ()))
        msg = err.get("msg", "")
        if loc and msg:
            parts.append(f"{loc}: {msg}")
        elif msg:
            parts.append(msg)
    return "; ".join(parts) if parts else "validation_failed"


class RevenueEraAdjustment(BaseModel):
    code: str | None = None
    amount_cents: int

    model_config = ConfigDict(extra="forbid")

    @field_validator("amount_cents", mode="before")
    @classmethod
    def _ensure_int(cls, value: Any) -> int:
        if isinstance(value, bool):
            raise ValueError("amount_cents must be integer")
        if isinstance(value, float):
            raise ValueError("floats not allowed")
        try:
            return int(value)
        except Exception as exc:  # noqa: BLE001
            raise ValueError("amount_cents must be integer") from exc


class RevenueEraStructuredLine(BaseModel):
    claim_ref: str
    service_date: date | None = None
    proc_code: str | None = None
    charge_cents: int | None = None
    allowed_cents: int | None = None
    paid_cents: int | None = None
    adjustments: list[RevenueEraAdjustment] = Field(default_factory=list)
    match_status: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("charge_cents", "allowed_cents", "paid_cents", mode="before")
    @classmethod
    def _ensure_optional_int(cls, value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool):
            raise ValueError("cents must be integer")
        if isinstance(value, float):
            raise ValueError("floats not allowed")
        try:
            return int(value)
        except Exception as exc:  # noqa: BLE001
            raise ValueError("cents must be integer") from exc


class RevenueEraStructuredV1(BaseModel):
    payer_name: str
    received_date: date | None = None
    claim_lines: list[RevenueEraStructuredLine]

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _reject_phi_keys(cls, value: Any) -> Any:
        def _check(obj: Any) -> None:
            if isinstance(obj, dict):
                for key, val in obj.items():
                    if key and key.lower() in _FORBIDDEN_PHI_KEYS:
                        raise ValueError(f"forbidden key: {key}")
                    _check(val)
            elif isinstance(obj, list):
                for item in obj:
                    _check(item)

        _check(value)
        return value


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _sanitize_pdf(upload: UploadFile) -> None:
    name_ok = sanitize_filename(upload.filename or "file.pdf").lower().endswith(".pdf")
    ctype = (upload.content_type or "").strip().lower()
    if not name_ok or ctype not in _ALLOWED_PDF_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="pdf_required",
        )


async def write_pdf_with_sha(upload: UploadFile, destination: Path) -> tuple[str, int]:
    _sanitize_pdf(upload)
    sha = hashlib.sha256()
    total_bytes = 0

    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as out:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
            sha.update(chunk)
            total_bytes += len(chunk)

    if total_bytes == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="empty_pdf_not_allowed")
    return sha.hexdigest(), total_bytes


def store_revenue_file(
    db: Session,
    *,
    organization_id: str,
    file_name: str,
    sha256: str,
    storage_ref: str,
    payer_name_raw: str | None,
    received_date: date | None,
) -> RevenueEraFile:
    duplicate = db.execute(
        select(RevenueEraFile).where(
            RevenueEraFile.organization_id == organization_id,
            RevenueEraFile.sha256 == sha256,
        )
    ).scalar_one_or_none()
    if duplicate:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="duplicate_upload")

    row = RevenueEraFile(
        id=str(uuid4()),
        organization_id=organization_id,
        file_name=file_name,
        sha256=sha256,
        payer_name_raw=payer_name_raw,
        received_date=received_date,
        storage_ref=storage_ref,
        status=STATUS_UPLOADED,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _remove_phi(extracted: dict[str, Any]) -> dict[str, Any]:
    """
    Redact patient_name-like keys from extracted payload.
    """

    def _clean(obj: Any) -> Any:
        if isinstance(obj, dict):
            cleaned = {}
            for key, value in obj.items():
                if key.lower() in {
                    "patient_name",
                    "patient",
                    "member_name",
                    "member_id",
                    "patient_id",
                    "subscriber_name",
                }:
                    continue
                cleaned[key] = _clean(value)
            return cleaned
        if isinstance(obj, list):
            return [_clean(item) for item in obj]
        return obj

    return _clean(extracted)


def run_doc_intel(pdf_path: Path) -> dict[str, Any]:
    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.core.credentials import AzureKeyCredential

    endpoint = os.getenv("AZURE_DOCINTEL_ENDPOINT", "").strip()
    key = os.getenv("AZURE_DOCINTEL_KEY", "").strip()
    model_id = os.getenv("AZURE_DOCINTEL_MODEL", "").strip() or "prebuilt-layout"

    if not endpoint or not key:
        raise RuntimeError("Azure Document Intelligence is not configured")

    client = DocumentIntelligenceClient(endpoint=endpoint, credential=AzureKeyCredential(key))
    with pdf_path.open("rb") as data:
        poller = client.begin_analyze_document(model_id=model_id, body=data, content_type="application/pdf")
    result = poller.result()
    payload = result.to_dict() if hasattr(result, "to_dict") else json.loads(json.dumps(result, default=str))
    return {
        "model_id": model_id,
        "extracted": _remove_phi(payload),
    }


def _structured_schema() -> dict[str, Any]:
    schema = RevenueEraStructuredV1.model_json_schema()
    schema["additionalProperties"] = False
    return schema


def run_structuring_llm(extracted_json: dict[str, Any]) -> RevenueEraStructuredV1:
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "").strip()
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "").strip()
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
    api_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
    if not (deployment and api_version and endpoint and api_key):
        raise RuntimeError("Azure OpenAI is not configured")

    client = AzureOpenAI(
        api_key=api_key,
        api_version=api_version,
        azure_endpoint=endpoint,
    )
    schema = _structured_schema()
    response = client.chat.completions.create(
        model=deployment,
        temperature=0,
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "RevenueEraStructuredV1", "schema": schema, "strict": True},
        },
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a deterministic parser that converts ERA extraction JSON into a strict schema. "
                    "Use integer cents only, do not emit floats. Omit any PHI fields."
                ),
            },
            {"role": "user", "content": json.dumps(extracted_json)},
        ],
    )
    try:
        content = response.choices[0].message.content
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("Azure OpenAI response missing content") from exc
    if not content:
        raise RuntimeError("Azure OpenAI returned empty content")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Azure OpenAI returned invalid JSON") from exc
    try:
        return RevenueEraStructuredV1.model_validate(parsed)
    except ValidationError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Structured schema validation failed: {exc}") from exc


def _match_status(raw: str | None) -> str:
    normalized = (raw or "").upper()
    if normalized in {MATCH_MATCHED, MATCH_AMBIGUOUS, MATCH_UNMATCHED}:
        return normalized
    return MATCH_UNMATCHED


def normalize_structured(
    db: Session,
    *,
    era_file: RevenueEraFile,
    structured: RevenueEraStructuredV1,
) -> tuple[int, int, int]:
    db.execute(delete(RevenueEraWorkItem).where(RevenueEraWorkItem.era_file_id == era_file.id))
    db.execute(delete(RevenueEraClaimLine).where(RevenueEraClaimLine.era_file_id == era_file.id))

    payer_name = (structured.payer_name or era_file.payer_name_raw or "").strip() or "Unknown"
    line_records: list[RevenueEraClaimLine] = []
    work_records: list[RevenueEraWorkItem] = []

    for idx, line in enumerate(structured.claim_lines):
        adjustments_payload = [adj.model_dump() for adj in line.adjustments] if line.adjustments else None
        line_record = RevenueEraClaimLine(
            era_file_id=era_file.id,
            line_index=idx,
            claim_ref=line.claim_ref,
            service_date=line.service_date,
            proc_code=line.proc_code,
            charge_cents=line.charge_cents,
            allowed_cents=line.allowed_cents,
            paid_cents=line.paid_cents,
            adjustments_json=adjustments_payload,
            match_status=_match_status(line.match_status),
        )
        line_records.append(line_record)

        paid = line.paid_cents or 0
        charge = line.charge_cents or 0
        allowed = line.allowed_cents
        has_negative_adjustment = any((adj.amount_cents or 0) < 0 for adj in line.adjustments)

        item_type = WORKITEM_TYPE_UNMATCHED
        if paid == 0:
            item_type = WORKITEM_TYPE_DENIAL
        elif allowed is not None and paid < allowed:
            item_type = WORKITEM_TYPE_UNDERPAYMENT
        elif has_negative_adjustment:
            item_type = WORKITEM_TYPE_RECOUPMENT

        dollars_cents = charge - paid
        if dollars_cents < 0:
            dollars_cents = 0

        work_records.append(
            RevenueEraWorkItem(
                id=str(uuid4()),
                organization_id=era_file.organization_id,
                era_file_id=era_file.id,
                era_claim_line_id=None,
                type=item_type,
                dollars_cents=dollars_cents,
                payer_name=payer_name,
                claim_ref=line.claim_ref,
                status=WORKITEM_OPEN,
            )
        )

    db.add_all(line_records)
    db.flush()

    # Wire claim line IDs into work items
    for work, claim in zip(work_records, line_records, strict=False):
        work.era_claim_line_id = claim.id

    db.add_all(work_records)
    db.flush()
    dollars_total = sum(item.dollars_cents for item in work_records)
    return len(line_records), len(work_records), dollars_total


def log_attempt(db: Session, *, organization_id: str, actor: str, era_file_id: str, action: str) -> None:
    try:
        log_event(
            db,
            action=action,
            entity_type="revenue_era_file",
            entity_id=era_file_id,
            organization_id=organization_id,
            actor=actor,
        )
    except Exception:
        # Avoid blocking flow on audit failures; upstream logging already persists attempts.
        pass


def record_processing_log(
    db: Session,
    *,
    era_file_id: str,
    stage: str,
    message: str,
    commit: bool = True,
) -> None:
    try:
        log = RevenueEraProcessingLog(
            id=str(uuid4()),
            era_file_id=era_file_id,
            stage=stage[:50],
            message=(message or "")[:500],
        )
        db.add(log)
        if commit:
            db.commit()
        else:
            db.flush()
    except Exception:
        db.rollback()
