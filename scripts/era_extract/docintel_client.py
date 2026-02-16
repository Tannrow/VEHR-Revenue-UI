from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable, Optional

from dotenv import load_dotenv


@dataclass(frozen=True)
class DocIntelConfig:
    endpoint: str
    key: str
    model_id: str = "prebuilt-layout"


def _first_env(var_names: Iterable[str]) -> Optional[str]:
    for name in var_names:
        val = os.getenv(name)
        if val and val.strip():
            return val.strip()
    return None


def _discover_endpoint_and_key() -> tuple[Optional[str], Optional[str]]:
    # Spec-required env vars (load via python-dotenv from .env).
    endpoint = _first_env(["AZURE_DOCINTEL_ENDPOINT"])
    key = _first_env(["AZURE_DOCINTEL_KEY"])
    if endpoint and key:
        return endpoint, key

    # Back-compat aliases (do not invent; support common variants).
    endpoint = _first_env(
        [
            "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT",
            "DOCUMENT_INTELLIGENCE_ENDPOINT",
            "DOCINTEL_ENDPOINT",
            "FORM_RECOGNIZER_ENDPOINT",
            "AZURE_FORM_RECOGNIZER_ENDPOINT",
        ]
    )
    key = _first_env(
        [
            "AZURE_DOCUMENT_INTELLIGENCE_KEY",
            "DOCUMENT_INTELLIGENCE_KEY",
            "DOCINTEL_KEY",
            "FORM_RECOGNIZER_KEY",
            "AZURE_FORM_RECOGNIZER_KEY",
        ]
    )
    return endpoint, key


def load_docintel_config() -> DocIntelConfig:
    # Load .env if present; never print values.
    load_dotenv(override=False)

    endpoint, key = _discover_endpoint_and_key()
    model_id = _first_env(
        [
            "AZURE_DOCUMENT_INTELLIGENCE_MODEL_ID",
            "DOCUMENT_INTELLIGENCE_MODEL_ID",
            "DOCINTEL_MODEL_ID",
        ]
    ) or "prebuilt-layout"

    if not endpoint or not key:
        raise RuntimeError(
            "Azure Document Intelligence is not configured. "
            "Set endpoint/key env vars (preferred: "
            "AZURE_DOCINTEL_ENDPOINT + AZURE_DOCINTEL_KEY)."
        )

    return DocIntelConfig(endpoint=endpoint, key=key, model_id=model_id)


def create_document_intelligence_client():
    # Imported lazily to keep import-time errors local to this feature.
    from azure.core.credentials import AzureKeyCredential
    from azure.ai.documentintelligence import DocumentIntelligenceClient

    cfg = load_docintel_config()
    return DocumentIntelligenceClient(endpoint=cfg.endpoint, credential=AzureKeyCredential(cfg.key)), cfg
