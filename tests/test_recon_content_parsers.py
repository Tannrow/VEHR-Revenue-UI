from __future__ import annotations

from datetime import date
from decimal import Decimal

from scripts.era_extract.content_parsers import parse_billed_content, parse_era_content


def test_parse_era_content_table_layout_extracts_rows_and_counters() -> None:
    content = """
Patient Name: TEST, ALPHA
Patient Ctrl Nmbr: AE-10001-1
Claim Number: CLM001
Line Details
Line Ctrl Nmbr
Dates of Service
Charge
Payment
11300000001Z1
01/01/2026 - 01/01/2026
HC:96164 / HF / 1
$23.44 (B6)
$30.00
CO-45
$6.56
$23.44
11300000001Z2
01/02/2026 - 01/02/2026
HC:96165 / HF / 2
$46.88 (B6)
$60.00
CO-45
$13.12
$46.88
Supplemental Information
Patient Name: TEST, BETA
Patient Ctrl Nmbr: AE-10002-2
Claim Number: CLM002
Line Details
Line Ctrl Nmbr
Dates of Service
Charge
Payment
11300000002Z1
01/03/2026 - 01/03/2026
HC:T1017 / HF / 4
$56.80 (B6)
$60.00
CO-45
$3.20
$56.80
"""

    rows, counters = parse_era_content(content)

    assert counters["claim_blocks_found"] == 2
    assert counters["line_rows_extracted"] == 3
    assert counters["blocks_with_no_lines"] == 0
    assert counters["skipped_missing_account_id"] == 0

    assert len(rows) == 3
    assert rows[0]["account_id"] == "AE-10001-1"
    assert rows[0]["payer_claim_number"] == "CLM001"
    assert rows[0]["dos_from"] == date(2026, 1, 1)
    assert rows[0]["proc_code"] == "96164"
    assert rows[0]["units"] == Decimal("1")
    assert rows[0]["billed_amount"] == Decimal("30.00")
    assert rows[0]["paid_amount"] == Decimal("23.44")
    assert rows[0]["source_layout"] == "table"


def test_parse_era_content_monospace_layout_extracts_rows() -> None:
    content = """
NAME: DEMO PATIENT
ACNT: AE-20001-1
PROV  SERV DATE  POS  NOS  PROC  BILLED  ALLOWED  PROV PD
01/10/2026 - 01/10/2026  11  1  HC:96164 / HF / 1  $30.00  $23.44  $23.44
01/11/2026 - 01/11/2026  11  1  HC:96165 / HF / 2  $60.00  $46.88  $46.88
"""

    rows, counters = parse_era_content(content)

    assert counters["claim_blocks_found"] == 1
    assert counters["line_rows_extracted"] == 2
    assert rows[0]["account_id"] == "AE-20001-1"
    assert rows[0]["source_layout"] == "monospace"
    assert rows[0]["proc_code"] == "96164"
    assert rows[0]["billed_amount"] == Decimal("30.00")


def test_parse_billed_content_extracts_rows_and_missing_key_counts() -> None:
    content = """
Account Number: AE-30001-1
01/15/2026 - 01/15/2026 HC:96164 / HF / 1 $30.00
01/16/2026 - 01/16/2026 HC:96165 / HF / 2 $60.00

Patient Name: DEMO WITHOUT ACCOUNT
01/17/2026 - 01/17/2026 HC:T1017 / HF / 4 $56.80
"""

    rows, counters = parse_billed_content(content)

    assert counters["blocks_found"] >= 2
    assert counters["line_rows_extracted"] == 3
    assert counters["missing_key_count"] >= 1
    assert any(row["account_id"] == "AE-30001-1" for row in rows)
    assert any(row["account_id"] is None for row in rows)
