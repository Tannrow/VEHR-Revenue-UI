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

    exit_code = era_ops.main(["upload", "--file", str(pdf), "--token", "tok"])

    assert exit_code == 1
    assert "stage=upload status=400" in capsys.readouterr().err
