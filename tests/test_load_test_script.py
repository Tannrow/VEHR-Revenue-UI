from __future__ import annotations

from pathlib import Path

from scripts import load_test


def test_parser_defaults_to_process_mode() -> None:
    parser = load_test._build_parser()
    args = parser.parse_args(["--dir", "/tmp"])
    assert args.mode == "processes"


def test_percentile_handles_empty_and_interpolated_values() -> None:
    assert load_test._percentile([], 95) == 0
    assert load_test._percentile([10], 95) == 10
    assert load_test._percentile([10, 20, 30, 40], 50) == 25


def test_extract_stage_durations_reads_duration_only() -> None:
    rows = [
        {"stage": "EXTRACTED", "message": "model_id=di; duration_ms=101"},
        {"stage": "STRUCTURED", "message": "claim_count=1; duration_ms=202"},
        {"stage": "NORMALIZED", "message": "claim_count=1"},
        {"stage": "FAILED", "message": "duration_ms=abc"},
    ]
    parsed = load_test._extract_stage_durations(rows)
    assert parsed == {"extracted": 101, "structured": 202}
    assert "failed" not in parsed


def test_required_stress_fixtures_exist() -> None:
    fixture_dir = Path(__file__).resolve().parent / "fixtures" / "era"
    required = {
        "large_20p.pdf",
        "large_50p.pdf",
        "large_100p.pdf",
        "malformed_truncated.pdf",
        "malformed_not_pdf.pdf",
        "encrypted.pdf",
    }
    assert required.issubset({path.name for path in fixture_dir.iterdir() if path.is_file()})


def test_main_rejects_invalid_base_url(tmp_path) -> None:
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    assert load_test.main(["--dir", str(tmp_path), "--base-url", "ftp://invalid"]) == 1


def test_main_supports_concurrency_matrix(tmp_path, monkeypatch, capsys) -> None:
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(load_test, "_login", lambda *args, **kwargs: ("tok", "org-1"))
    monkeypatch.setattr(
        load_test,
        "_run_one",
        lambda *args, **kwargs: {
            "ok": True,
            "error_code": "",
            "request_id": "req-1",
            "duration_ms": 10,
            "stage_durations": {"extracted": 5, "structured": 4, "normalized": 1},
            "rss_mb": 32.0,
            "source_file": "sample.pdf",
            "deterministic_hash": "abc123",
        },
    )
    monkeypatch.setattr(load_test, "_run_invariants", lambda *args, **kwargs: {"pass": True, "failures": []})
    monkeypatch.setattr(load_test, "_rss_mb", lambda: 64.0)

    for workers in (5, 20, 50):
        rc = load_test.main(
            [
                "--dir",
                str(tmp_path),
                "--base-url",
                "http://127.0.0.1:8000",
                "--workers",
                str(workers),
                "--iterations",
                "1",
                "--mode",
                "threads",
                "--memory-ceiling-mb",
                "128",
            ]
        )
        assert rc == 0
    assert '"db_invariants": {"failures": [], "pass": true}' in capsys.readouterr().out
