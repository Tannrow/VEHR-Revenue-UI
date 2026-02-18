from __future__ import annotations

import json
import os
from typing import Any

import httpx


class ClaimNormalizationError(RuntimeError):
    pass


def _load_azure_openai_config() -> dict[str, str]:
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
    key = os.getenv("AZURE_OPENAI_KEY", "").strip()
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "").strip()
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "").strip() or "2024-08-01-preview"

    missing = [name for name, value in [("AZURE_OPENAI_ENDPOINT", endpoint), ("AZURE_OPENAI_KEY", key), ("AZURE_OPENAI_DEPLOYMENT", deployment)] if not value]
    if missing:
        raise ClaimNormalizationError(f"Azure OpenAI config missing: {', '.join(missing)}")

    return {
        "endpoint": endpoint.rstrip("/"),
        "key": key,
        "deployment": deployment,
        "api_version": api_version,
    }


def normalize_claims_from_azure(azure_json: dict[str, Any], document_type: str) -> list[dict[str, Any]]:
    if not isinstance(azure_json, dict):
        raise ClaimNormalizationError("azure_json must be a dict")
    cfg = _load_azure_openai_config()

    url = f"{cfg['endpoint']}/openai/deployments/{cfg['deployment']}/chat/completions"
    params = {"api-version": cfg["api_version"]}

    system_prompt = (
        "You normalize healthcare claims extracted from Azure Document Intelligence. "
        "Return strict JSON matching the schema. "
        "Never include PHI beyond what is provided. "
        "Schema: list of claims with external_claim_id, patient_name, member_id, payer_name, dos_from, dos_to, "
        "and lines[{cpt_code, units, billed_amount, allowed_amount, paid_amount, adjustments[{code, amount}]}]. "
        "Dates must be YYYY-MM-DD or null. Numeric fields may be null."
    )

    user_payload = {
        "document_type": document_type,
        "azure_document_intelligence": azure_json,
    }

    body = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload)},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "api-key": cfg["key"],
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=60) as client:
            resp = client.post(url, params=params, headers=headers, json=body)
    except Exception as exc:
        raise ClaimNormalizationError(f"Azure OpenAI request failed: {exc}")

    if resp.status_code >= 400:
        raise ClaimNormalizationError(f"Azure OpenAI HTTP {resp.status_code}")

    try:
        payload = resp.json()
        content = (
            payload.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
    except Exception as exc:
        raise ClaimNormalizationError(f"Invalid Azure OpenAI response: {exc}")

    if not content:
        raise ClaimNormalizationError("Azure OpenAI returned empty content")

    try:
        parsed = json.loads(content)
    except Exception as exc:
        raise ClaimNormalizationError(f"Failed to parse normalized claims JSON: {exc}")

    claims = parsed
    if isinstance(parsed, dict) and "claims" in parsed:
        claims = parsed.get("claims")
    if not isinstance(claims, list):
        raise ClaimNormalizationError("Normalized claims must be a list")
    sanitized: list[dict[str, Any]] = []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        safe_claim = dict(claim)
        for key in ("billed_amount", "allowed_amount", "paid_amount"):
            if key in safe_claim:
                safe_claim[key] = None
        lines = safe_claim.get("lines")
        if isinstance(lines, list):
            new_lines: list[dict[str, Any]] = []
            for line in lines:
                if not isinstance(line, dict):
                    continue
                safe_line = dict(line)
                for key in ("billed_amount", "allowed_amount", "paid_amount"):
                    if key in safe_line:
                        safe_line[key] = None
                adjustments = safe_line.get("adjustments")
                if isinstance(adjustments, list):
                    safe_line["adjustments"] = [
                        {**adj, "amount": None} for adj in adjustments if isinstance(adj, dict)
                    ]
                new_lines.append(safe_line)
            safe_claim["lines"] = new_lines
        sanitized.append(safe_claim)
    return sanitized
