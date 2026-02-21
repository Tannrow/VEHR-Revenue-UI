from __future__ import annotations

import io
import json
from pathlib import Path
from urllib import error

from scripts import era_ops


def test_multipart_body_uses_files_field(tmp_path: Path) -> None:
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    body, boundary = era_ops._multipart_body(pdf)

    assert boundary
    text = body.decode("latin-1")
    assert 'name="files"' in text
    assert f'filename="{pdf.name}"' in text


def test_main_upload_success(tmp_path: Path, monkeypatch, capsys) -> None:
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    class _Response:
        status = 200

        @staticmethod
        def read() -> bytes:
            return json.dumps([{"id": "era-1", "status": "uploaded"}]).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    monkeypatch.setattr(era_ops.request, "urlopen", lambda req: _Response())

    exit_code = era_ops.main(["upload", "--file", str(pdf), "--base-url", "http://localhost:8000", "--token", "tok"])

    assert exit_code == 0
    assert "upload era_file_id=era-1 status=uploaded" in capsys.readouterr().out


def test_main_upload_http_error(tmp_path: Path, monkeypatch, capsys) -> None:
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    class _ErrorResponse:
        @staticmethod
        def read() -> bytes:
            return json.dumps({"detail": "bad_request"}).encode("utf-8")

    def _raise_http_error(req):
        raise error.HTTPError(req.full_url, 400, "bad request", hdrs=None, fp=io.BytesIO(_ErrorResponse.read()))

    monkeypatch.setattr(era_ops.request, "urlopen", _raise_http_error)

    exit_code = era_ops.main(["upload", "--file", str(pdf), "--base-url", "http://localhost:8000", "--token", "tok"])

    assert exit_code == 1
    assert "stage=upload status=400" in capsys.readouterr().err


def test_main_login_success(monkeypatch, capsys) -> None:
    class _Response:
        status = 200

        @staticmethod
        def read() -> bytes:
            return json.dumps(
                {"access_token": "secret-token", "organization_id": "org-1", "user_id": "user-1"}
            ).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    monkeypatch.setattr(era_ops.request, "urlopen", lambda req, data=None: _Response())

    exit_code = era_ops.main(
        ["login", "--base-url", "http://localhost:8000", "--email", "admin@example.com", "--password", "pw"]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "login status=200 organization_id=org-1 user_id=user-1" in captured.out
    assert "secret-token" not in captured.out


def test_main_ingest_reports_process_error(tmp_path: Path, monkeypatch, capsys) -> None:
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    class _Response:
        def __init__(self, status: int, payload: object) -> None:
            self.status = status
            self._payload = payload

        def read(self) -> bytes:
            return json.dumps(self._payload).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    def _urlopen(req, data=None):
        if req.full_url.endswith("/api/v1/auth/login"):
            return _Response(200, {"access_token": "secret-token"})
        if req.full_url.endswith("/api/v1/revenue/era-pdfs/upload"):
            return _Response(200, [{"id": "era-1", "status": "uploaded"}])
        if req.full_url.endswith("/api/v1/revenue/era-pdfs/era-1/process"):
            return _Response(
                502,
                {"error": "external_service_failure", "stage": "extract", "error_code": "DI_TIMEOUT", "request_id": "req-1"},
            )
        raise AssertionError(f"unexpected url {req.full_url}")

    monkeypatch.setattr(era_ops.request, "urlopen", _urlopen)

    exit_code = era_ops.main(
        ["ingest", "--dir", str(tmp_path), "--base-url", "http://localhost:8000", "--email", "admin@example.com", "--password", "pw"]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "summary success=0 failure=1" in captured.out
    assert "stage=extract status=502 error_code=DI_TIMEOUT request_id=req-1" in captured.err
