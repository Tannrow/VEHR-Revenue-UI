from __future__ import annotations

import json
import sys
import types

from app.services import revenue_era


def test_doc_intel_falls_back_to_prebuilt_layout_and_structuring_receives_layout_envelope(
    tmp_path, monkeypatch
) -> None:
    pdf_path = tmp_path / "era.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    captured: dict[str, object] = {}

    class FakeCredential:
        def __init__(self, key: str) -> None:
            self.key = key

    class FakeResult:
        def to_dict(self) -> dict[str, object]:
            return {
                "pages": [
                    {"page_number": 1, "lines": [{"content": "PAYER A"}, {"content": "CLAIM C1"}]},
                ],
                "tables": [
                    {
                        "cells": [
                            {
                                "row_index": 0,
                                "column_index": 0,
                                "content": "Claim",
                                "bounding_regions": [{"page_number": 1}],
                            }
                        ]
                    }
                ],
            }

    class FakePoller:
        def result(self, timeout: float | None = None) -> FakeResult:
            captured["poller_timeout"] = timeout
            return FakeResult()

    class FakeDocIntelClient:
        def __init__(self, endpoint: str, credential: FakeCredential, **kwargs) -> None:
            captured["endpoint"] = endpoint
            captured["key"] = credential.key
            captured["kwargs"] = kwargs

        def begin_analyze_document(self, *, model_id: str, body, content_type: str) -> FakePoller:
            captured["model_id"] = model_id
            captured["content_type"] = content_type
            body.read(1)
            return FakePoller()

    azure_module = types.ModuleType("azure")
    azure_module.__path__ = []  # type: ignore[attr-defined]
    azure_ai_module = types.ModuleType("azure.ai")
    azure_ai_module.__path__ = []  # type: ignore[attr-defined]
    azure_docintel_module = types.ModuleType("azure.ai.documentintelligence")
    azure_docintel_module.DocumentIntelligenceClient = FakeDocIntelClient
    azure_core_module = types.ModuleType("azure.core")
    azure_core_module.__path__ = []  # type: ignore[attr-defined]
    azure_core_credentials_module = types.ModuleType("azure.core.credentials")
    azure_core_credentials_module.AzureKeyCredential = FakeCredential
    azure_module.ai = azure_ai_module  # type: ignore[attr-defined]
    azure_ai_module.documentintelligence = azure_docintel_module  # type: ignore[attr-defined]
    azure_module.core = azure_core_module  # type: ignore[attr-defined]
    azure_core_module.credentials = azure_core_credentials_module  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "azure", azure_module)
    monkeypatch.setitem(sys.modules, "azure.ai", azure_ai_module)
    monkeypatch.setitem(sys.modules, "azure.ai.documentintelligence", azure_docintel_module)
    monkeypatch.setitem(sys.modules, "azure.core", azure_core_module)
    monkeypatch.setitem(sys.modules, "azure.core.credentials", azure_core_credentials_module)

    monkeypatch.setenv("AZURE_DOCINTEL_ENDPOINT", "https://example.cognitiveservices.azure.com")
    monkeypatch.setenv("AZURE_DOCINTEL_KEY", "secret")
    monkeypatch.delenv("AZURE_DOCINTEL_MODEL", raising=False)

    extracted = revenue_era.run_doc_intel(pdf_path)

    assert captured["model_id"] == "prebuilt-layout"
    assert extracted["model_id"] == "prebuilt-layout"
    assert extracted["extracted"]["pages"][0]["page_number"] == 1
    assert extracted["extracted"]["pages"][0]["lines"][0]["text"] == "PAYER A"
    assert "cells" in extracted["extracted"]["pages"][0]["tables"][0]

    class FakeCompletions:
        @staticmethod
        def create(**kwargs):
            user_payload = json.loads(kwargs["messages"][1]["content"])
            assert "pages" in user_payload
            assert {"page_number", "lines", "tables"} <= user_payload["pages"][0].keys()
            return types.SimpleNamespace(
                choices=[
                    types.SimpleNamespace(
                        message=types.SimpleNamespace(
                            content=json.dumps(
                                {
                                    "payer_name": "PAYER A",
                                    "received_date": "2026-01-01",
                                    "declared_total_paid_cents": 100,
                                    "claim_lines": [
                                        {
                                            "claim_ref": "C1",
                                            "paid_cents": 100,
                                            "adjustments": [],
                                        }
                                    ],
                                }
                            )
                        )
                    )
                ]
            )

    class FakeAzureOpenAI:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.chat = types.SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(revenue_era, "AzureOpenAI", FakeAzureOpenAI)
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "dep")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "secret")

    structured = revenue_era.run_structuring_llm(extracted["extracted"])
    assert structured.payer_name == "PAYER A"
    assert structured.claim_lines[0].claim_ref == "C1"
