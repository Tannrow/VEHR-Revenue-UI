from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from datetime import date, datetime
from decimal import Decimal
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
from app.core.env import env_default_bool
from app.services.audit import log_event
from app.services.storage import sanitize_filename
from infrastructure.azure_client import AzureClientError, AzureReliabilityClient


STATUS_UPLOADED = "UPLOADED"
STATUS_PROCESSING_EXTRACT = "PROCESSING_EXTRACT"
STATUS_PROCESSING_STRUCTURING = "PROCESSING_STRUCTURING"
STATUS_COMPLETE = "COMPLETE"
STATUS_ERROR = "ERROR"

# Backward-compatible aliases for existing call sites/tests.
STATUS_EXTRACTED = STATUS_PROCESSING_EXTRACT
STATUS_STRUCTURED = STATUS_PROCESSING_STRUCTURING
STATUS_NORMALIZED = STATUS_COMPLETE

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

_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE_RE = re.compile(r"(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}\b")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_DOB_RE = re.compile(r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\b")

ERROR_CODE_DUPLICATE = "ERA_DUPLICATE"
ERROR_CODE_SCHEMA_INVALID = "ERA_SCHEMA_INVALID"
ERROR_CODE_PHI_DETECTED = "ERA_PHI_DETECTED"
ERROR_CODE_RECONCILIATION_FAILED = "ERA_RECONCILIATION_FAILED"
ERROR_CODE_PROCESSING_FAILED = "ERA_PROCESSING_FAILED"

_FAILURE_INJECTION_LOCK = threading.Lock()
_FAILURE_INJECTION_USED: set[str] = set()
_FAILURE_STAGE_MAP = {
    "EXTRACTING": "document_intelligence_extract",
    "STRUCTURING": "openai_structuring",
    "PERSISTING": "persisting",
}


class EraSchemaInvalidError(RuntimeError):
    pass


class EraPhiDetectedError(RuntimeError):
    pass


class EraReconciliationError(RuntimeError):
    pass


def failure_injection_enabled() -> bool:
    if env_default_bool("ENABLE_FAILURE_INJECTION", False):
        return True
    env_name = (os.getenv("ENV", "") or os.getenv("APP_ENV", "")).strip().lower()
    return env_name in {"test", "dev", "development"}


def maybe_raise_fail_once(*, stage: str, request_id: str) -> None:
    configured = (os.getenv("AZURE_FAIL_ONCE_STAGE", "") or "").strip().upper()
    if not configured or configured not in _FAILURE_STAGE_MAP:
        return
    if _FAILURE_STAGE_MAP[configured] != stage:
        return
    if not failure_injection_enabled():
        return
    error_code = (os.getenv("AZURE_FAIL_ONCE_ERROR", "") or "").strip().lower() or "azure_unavailable"
    # Intentionally global fail-once behavior per configured stage+error_code for deterministic retry tests.
    key = f"{configured}:{error_code}"
    with _FAILURE_INJECTION_LOCK:
        if key in _FAILURE_INJECTION_USED:
            return
        _FAILURE_INJECTION_USED.add(key)
    raise AzureClientError(stage=stage, error_code=error_code, request_id=request_id)


def phase2_validation_enabled() -> bool:
    return env_default_bool("PHASE2_VALIDATION", False)


def fail_closed_enabled() -> bool:
    default = phase2_validation_enabled()
    return env_default_bool("FAIL_CLOSED", default)


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
        if isinstance(value, (float, Decimal)):
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
    patient_responsibility_cents: int | None = None
    adjustments: list[RevenueEraAdjustment] = Field(default_factory=list)
    match_status: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("charge_cents", "allowed_cents", "paid_cents", "patient_responsibility_cents", mode="before")
    @classmethod
    def _ensure_optional_int(cls, value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool):
            raise ValueError("cents must be integer")
        if isinstance(value, (float, Decimal)):
            raise ValueError("floats not allowed")
        try:
            return int(value)
        except Exception as exc:  # noqa: BLE001
            raise ValueError("cents must be integer") from exc


class RevenueEraStructuredV1(BaseModel):
    payer_name: str
    received_date: date | None = None
    declared_total_paid_cents: int | None = None
    declared_total_adjustment_cents: int | None = None
    declared_total_patient_resp_cents: int | None = None
    declared_net_cents: int | None = None
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

    @field_validator(
        "declared_total_paid_cents",
        "declared_total_adjustment_cents",
        "declared_total_patient_resp_cents",
        "declared_net_cents",
        mode="before",
    )
    @classmethod
    def _ensure_declared_int(cls, value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool):
            raise ValueError("declared totals must be integer")
        if isinstance(value, (float, Decimal)):
            raise ValueError("floats not allowed")
        try:
            return int(value)
        except Exception as exc:  # noqa: BLE001
            raise ValueError("declared totals must be integer") from exc


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


def _to_layout_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    pages = payload.get("pages") if isinstance(payload, dict) else []
    tables = payload.get("tables") if isinstance(payload, dict) else []
    tables_by_page: dict[int, list[dict[str, Any]]] = {}

    for table in tables if isinstance(tables, list) else []:
        if not isinstance(table, dict):
            continue
        table_pages: set[int] = set()
        cells: list[dict[str, Any]] = []
        for cell in table.get("cells") or []:
            if not isinstance(cell, dict):
                continue
            text = str(cell.get("content") or cell.get("text") or "").strip()
            cells.append(
                {
                    "row_index": cell.get("row_index"),
                    "column_index": cell.get("column_index"),
                    "text": text,
                }
            )
            for region in cell.get("bounding_regions") or []:
                if isinstance(region, dict):
                    page_number = region.get("page_number")
                    if isinstance(page_number, int):
                        table_pages.add(page_number)
        for region in table.get("bounding_regions") or []:
            if isinstance(region, dict):
                page_number = region.get("page_number")
                if isinstance(page_number, int):
                    table_pages.add(page_number)
        table_entry = {"cells": cells}
        for page_number in table_pages:
            tables_by_page.setdefault(page_number, []).append(table_entry)

    normalized_pages: list[dict[str, Any]] = []
    for page in pages if isinstance(pages, list) else []:
        if not isinstance(page, dict):
            continue
        page_number = page.get("page_number")
        if not isinstance(page_number, int):
            continue
        lines: list[dict[str, str]] = []
        for line in page.get("lines") or []:
            if not isinstance(line, dict):
                continue
            text = str(line.get("content") or line.get("text") or "").strip()
            if text:
                lines.append({"text": text})
        normalized_pages.append(
            {
                "page_number": page_number,
                "lines": lines,
                "tables": tables_by_page.get(page_number, []),
            }
        )

    return {"pages": normalized_pages}


def _validate_layout_envelope(envelope: dict[str, Any]) -> bool:
    pages = envelope.get("pages")
    if not isinstance(pages, list):
        return False
    for page in pages:
        if not isinstance(page, dict):
            return False
        if not isinstance(page.get("page_number"), int):
            return False
        if not isinstance(page.get("lines"), list):
            return False
        if not isinstance(page.get("tables"), list):
            return False
    return True


def run_doc_intel(pdf_path: Path, *, request_id: str | None = None) -> dict[str, Any]:
    request_id = request_id or str(uuid4())
    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.core.credentials import AzureKeyCredential
    from azure.core.pipeline.policies import RetryPolicy
    from azure.core.pipeline.transport import RequestsTransport

    endpoint = os.getenv("AZURE_DOCINTEL_ENDPOINT", "").strip()
    key = os.getenv("AZURE_DOCINTEL_KEY", "").strip()
    custom_model_id = os.getenv("AZURE_DOCINTEL_MODEL", "").strip()
    model_id = custom_model_id or "prebuilt-layout"
    connect_timeout_seconds = float(os.getenv("AZURE_DOCINTEL_CONNECT_TIMEOUT_SECONDS", "5"))
    read_timeout_seconds = float(os.getenv("AZURE_DOCINTEL_READ_TIMEOUT_SECONDS", "20"))
    # Phase 2 reliability requirement: Document Intelligence timeout must not exceed 30s.
    total_timeout_seconds = min(float(os.getenv("AZURE_DOCINTEL_TOTAL_TIMEOUT_SECONDS", "30")), 30.0)

    if not endpoint or not key:
        raise RuntimeError("Azure Document Intelligence is not configured")

    client = DocumentIntelligenceClient(
        endpoint=endpoint,
        credential=AzureKeyCredential(key),
        transport=RequestsTransport(
            connection_timeout=connect_timeout_seconds,
            read_timeout=read_timeout_seconds,
        ),
        retry_policy=RetryPolicy(
            retry_total=0,
            retry_connect=0,
            retry_read=0,
            retry_status=0,
            retry_backoff_factor=0.8,
            retry_backoff_max=4,
        ),
    )
    azure_client = AzureReliabilityClient()

    def _operation():
        with pdf_path.open("rb") as data:
            poller = client.begin_analyze_document(model_id=model_id, body=data, content_type="application/pdf")
        return poller.result(timeout=total_timeout_seconds)

    call = azure_client.call(
        stage="document_intelligence_extract",
        request_id=request_id,
        timeout_seconds=total_timeout_seconds,
        operation=_operation,
    )
    if not call.ok or call.value is None:
        raise AzureClientError(
            stage="document_intelligence_extract",
            error_code=call.error_code or "azure_unavailable",
            request_id=request_id,
        )
    result = call.value
    upstream_request_id = None
    response = getattr(result, "_response", None)
    headers = getattr(response, "headers", None)
    if headers:
        upstream_request_id = headers.get("x-ms-request-id") or headers.get("x-request-id")
    payload = result.to_dict() if hasattr(result, "to_dict") else json.loads(json.dumps(result, default=str))
    envelope = _remove_phi(_to_layout_envelope(payload))
    if not _validate_layout_envelope(envelope):
        raise AzureClientError(
            stage="document_intelligence_extract",
            error_code="azure_invalid_response",
            request_id=request_id,
        )
    return {"model_id": model_id, "request_id": upstream_request_id or request_id, "extracted": envelope}


def _structured_schema() -> dict[str, Any]:
    schema = RevenueEraStructuredV1.model_json_schema()
    schema["additionalProperties"] = False
    return schema


def run_structuring_llm(extracted_json: dict[str, Any], *, request_id: str | None = None) -> RevenueEraStructuredV1:
    request_id = request_id or str(uuid4())
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "").strip()
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "").strip()
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
    api_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
    if not (deployment and api_version and endpoint and api_key):
        raise RuntimeError("Azure OpenAI is not configured")

    # Phase 2 reliability requirement: Azure OpenAI timeout must not exceed 20s.
    timeout_seconds = min(float(os.getenv("AZURE_OPENAI_TIMEOUT_SECONDS", "20")), 20.0)
    client = AzureOpenAI(
        api_key=api_key,
        api_version=api_version,
        azure_endpoint=endpoint,
        timeout=timeout_seconds,
        max_retries=0,
    )
    schema = _structured_schema()
    azure_client = AzureReliabilityClient()

    def _operation():
        return client.chat.completions.create(
            model=deployment,
            temperature=0,
            timeout=timeout_seconds,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "RevenueEraStructuredV1", "schema": schema, "strict": True},
            },
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a deterministic parser that converts ERA layout extraction JSON into a strict schema. "
                        "Input contains pages[].lines[].text and pages[].tables[].cells[]. "
                        "Use integer cents only, do not emit floats. Omit any PHI fields."
                    ),
                },
                {"role": "user", "content": json.dumps(extracted_json)},
            ],
        )

    call = azure_client.call(
        stage="openai_structuring",
        request_id=request_id,
        timeout_seconds=timeout_seconds,
        operation=_operation,
    )
    if not call.ok or call.value is None:
        raise AzureClientError(
            stage="openai_structuring",
            error_code=call.error_code or "azure_unavailable",
            request_id=request_id,
        )
    response = call.value
    try:
        content = response.choices[0].message.content
    except Exception as exc:  # noqa: BLE001
        raise AzureClientError(
            stage="openai_structuring",
            error_code="azure_invalid_response",
            request_id=request_id,
        ) from exc
    if not content:
        raise AzureClientError(
            stage="openai_structuring",
            error_code="azure_invalid_response",
            request_id=request_id,
        )
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise AzureClientError(
            stage="openai_structuring",
            error_code="azure_invalid_response",
            request_id=request_id,
        ) from exc
    try:
        return RevenueEraStructuredV1.model_validate(parsed)
    except ValidationError as exc:
        raise AzureClientError(
            stage="openai_structuring",
            error_code="azure_invalid_response",
            request_id=request_id,
        ) from exc


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


def phi_scan(structured_payload: dict[str, Any]) -> tuple[bool, list[str]]:
    hits: set[str] = set()

    def _walk(value: Any, path: str = "") -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                key_lower = str(key).lower()
                if any(token in key_lower for token in {"patient_name", "member_name", "dob", "address"}):
                    hits.add(path + key_lower)
                _walk(nested, f"{path}{key}.")
            return
        if isinstance(value, list):
            for idx, nested in enumerate(value):
                _walk(nested, f"{path}{idx}.")
            return
        if isinstance(value, str):
            if _EMAIL_RE.search(value):
                hits.add("email")
            if _PHONE_RE.search(value):
                hits.add("phone")
            if _SSN_RE.search(value):
                hits.add("ssn")
            if _DOB_RE.search(value):
                hits.add("dob")

    _walk(structured_payload)
    hit_list = sorted(hits)
    return len(hit_list) == 0, hit_list


def reconcile_era(structured: RevenueEraStructuredV1) -> dict[str, Any]:
    total_paid = 0
    total_adjustment = 0
    total_patient_resp = 0
    line_count = 0
    for line in structured.claim_lines:
        line_count += 1
        for value in (line.paid_cents, line.patient_responsibility_cents):
            if value is not None and not isinstance(value, int):
                raise EraReconciliationError("non_integer_cents")
        paid = line.paid_cents or 0
        patient_resp = line.patient_responsibility_cents or 0
        adjustment = 0
        for adj in line.adjustments:
            if not isinstance(adj.amount_cents, int):
                raise EraReconciliationError("non_integer_adjustment")
            adjustment += adj.amount_cents
        total_paid += paid
        total_adjustment += adjustment
        total_patient_resp += patient_resp

    net_cents = total_paid - total_adjustment - total_patient_resp
    declared = {
        "paid": structured.declared_total_paid_cents,
        "adjustment": structured.declared_total_adjustment_cents,
        "patient_responsibility": structured.declared_total_patient_resp_cents,
        "net": structured.declared_net_cents,
    }
    declared_total_missing = all(value is None for value in declared.values())
    reconciled = True
    if not declared_total_missing:
        reconciled = (
            declared["paid"] == total_paid
            and declared["adjustment"] == total_adjustment
            and declared["patient_responsibility"] == total_patient_resp
            and declared["net"] == net_cents
        )
        if not reconciled:
            raise EraReconciliationError("declared_totals_mismatch")
    return {
        "line_count": line_count,
        "total_paid_cents": total_paid,
        "total_adjustment_cents": total_adjustment,
        "total_patient_resp_cents": total_patient_resp,
        "net_cents": net_cents,
        "declared_total_missing": declared_total_missing,
        "reconciled": reconciled,
    }


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
