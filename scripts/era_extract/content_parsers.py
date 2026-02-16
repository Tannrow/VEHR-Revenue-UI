from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any


_DATE_RX = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{2,4})\b")
_DATE_RANGE_RX = re.compile(
    r"\b(\d{1,2}/\d{1,2}/\d{2,4})\s*[-–]\s*(\d{1,2}/\d{1,2}/\d{2,4})\b",
    re.IGNORECASE,
)
_MONEY_RX = re.compile(r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})|[0-9]+\.[0-9]{2})")
_ACCOUNT_RX = re.compile(r"\bAE-\d{3,}-\d+\b", re.IGNORECASE)
_ADJ_CODE_RX = re.compile(r"^(?:CO|PR|OA|PI)-[A-Z0-9]+$", re.IGNORECASE)


def _clean_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line and line.strip()]


def _to_decimal(raw: str | None) -> Decimal | None:
    if not raw:
        return None
    cleaned = raw.replace(",", "").replace("$", "").strip()
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _extract_money_values(text: str) -> list[Decimal]:
    values: list[Decimal] = []
    for raw in _MONEY_RX.findall(text or ""):
        dec = _to_decimal(raw)
        if dec is not None:
            values.append(dec)
    return values


def _extract_date(raw: str | None) -> date | None:
    if not raw:
        return None
    token = raw.strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(token, fmt).date()
        except ValueError:
            continue
    return None


def _extract_date_range(text: str) -> tuple[date | None, date | None]:
    if not text:
        return None, None
    match = _DATE_RANGE_RX.search(text)
    if match:
        return _extract_date(match.group(1)), _extract_date(match.group(2))
    single = _DATE_RX.search(text)
    if single:
        d = _extract_date(single.group(1))
        return d, d
    return None, None


def _extract_account_id(block: str) -> str | None:
    explicit = re.search(
        r"(?im)(?:Patient\s*Ctrl\s*Nmbr|ACNT|Account(?:\s*(?:ID|Number))?)\s*:\s*([A-Za-z0-9\-]+)",
        block,
    )
    if explicit:
        return explicit.group(1).strip()
    general = _ACCOUNT_RX.search(block or "")
    if general:
        return general.group(0).strip()
    return None


def _extract_claim_number(block: str) -> str | None:
    for rx in (
        r"(?im)Claim\s*Number\s*:\s*([A-Za-z0-9\-]+)",
        r"(?im)Payer\s*Claim\s*Number\s*:\s*([A-Za-z0-9\-]+)",
    ):
        m = re.search(rx, block)
        if m:
            return m.group(1).strip()
    return None


def _extract_icn(block: str) -> str | None:
    m = re.search(r"(?im)\bICN\b\s*:\s*([A-Za-z0-9\-]+)", block or "")
    if m:
        return m.group(1).strip()
    return None


def _extract_proc_code(text: str) -> str | None:
    if not text:
        return None
    hc = re.search(r"(?i)\b(?:HC|CPT|PROC)\s*:\s*([A-Z0-9]+)\b", text)
    if hc:
        return hc.group(1).upper()
    cpt = re.search(r"\b([A-Z]?\d{4,5}[A-Z]?)\b", text)
    if cpt:
        return cpt.group(1).upper()
    return None


def _extract_units(text: str) -> Decimal | None:
    if not text:
        return None
    for rx in (
        r"(?i)\bunits?\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)\b",
        r"/\s*([0-9]+(?:\.[0-9]+)?)\s*$",
        r"(?i)\bqty\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)\b",
    ):
        m = re.search(rx, text.strip())
        if m:
            return _to_decimal(m.group(1))
    return None


def _split_claim_blocks(content: str) -> list[str]:
    if not content or not content.strip():
        return []
    blocks = re.split(r"(?im)(?=^\s*(?:Patient\s*Name:|NAME:))", content)
    cleaned = [blk.strip() for blk in blocks if blk and blk.strip()]
    if cleaned:
        return cleaned
    return [content.strip()]


def _line_id_like(token: str) -> bool:
    if not token:
        return False
    return bool(re.match(r"^[A-Z0-9]{8,}(?:Z\d+)?$", token.strip(), flags=re.IGNORECASE))


def _parse_era_table_layout(
    block: str,
    *,
    account_id: str | None,
    claim_number: str | None,
    icn: str | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    lines = _clean_lines(block)
    if not lines:
        return rows

    header_idx = -1
    for i, line in enumerate(lines):
        if "Line Ctrl Nmbr".lower() in line.lower():
            header_idx = i
            break
    if header_idx < 0:
        return rows

    region: list[str] = []
    for line in lines[header_idx + 1 :]:
        lowered = line.lower()
        if lowered.startswith("supplemental information") or lowered.startswith("patient name"):
            break
        region.append(line)
    if not region:
        return rows

    idxs = [i for i, line in enumerate(region) if _line_id_like(line)]
    if not idxs:
        return rows

    for j, start in enumerate(idxs):
        end = idxs[j + 1] if j + 1 < len(idxs) else len(region)
        segment = region[start:end]
        if not segment:
            continue

        line_id = segment[0].strip()
        segment_text = "\n".join(segment)
        dos_from, dos_to = _extract_date_range(segment_text)

        proc_line = ""
        for line in segment[1:]:
            if ":" in line and ("HC:" in line.upper() or "PROC" in line.upper() or "CPT" in line.upper()):
                proc_line = line
                break
        if not proc_line:
            for line in segment[1:]:
                if re.search(r"\b[A-Z]?\d{4,5}[A-Z]?\b", line):
                    proc_line = line
                    break

        proc_code = _extract_proc_code(proc_line or segment_text)
        units = _extract_units(proc_line or segment_text)

        money = _extract_money_values(segment_text)
        allowed_amount = money[0] if len(money) >= 1 else None
        billed_amount = money[1] if len(money) >= 2 else (money[0] if len(money) == 1 else None)
        paid_amount = money[-1] if money else None

        adj_code = None
        adj_amount = None
        for idx, line in enumerate(segment):
            if _ADJ_CODE_RX.match(line.strip()):
                adj_code = line.strip().upper()
                if idx + 1 < len(segment):
                    next_money = _extract_money_values(segment[idx + 1])
                    if next_money:
                        adj_amount = next_money[0]
                break
        if adj_amount is None and len(money) >= 4:
            adj_amount = money[-2]

        rows.append(
            {
                "account_id": account_id,
                "payer_claim_number": claim_number,
                "icn": icn,
                "line_ctrl_number": line_id,
                "dos_from": dos_from,
                "dos_to": dos_to,
                "proc_code": proc_code,
                "units": units,
                "billed_amount": billed_amount,
                "allowed_amount": allowed_amount,
                "paid_amount": paid_amount,
                "adj_code": adj_code,
                "adj_amount": adj_amount,
                "source_layout": "table",
            }
        )
    return rows


def _parse_era_monospace_layout(
    block: str,
    *,
    account_id: str | None,
    claim_number: str | None,
    icn: str | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    lines = _clean_lines(block)
    if not lines:
        return rows

    header_idx = -1
    for i, line in enumerate(lines):
        lowered = " ".join(line.lower().split())
        if "serv date" in lowered and "proc" in lowered and "billed" in lowered and (
            "prov pd" in lowered or "paid" in lowered
        ):
            header_idx = i
            break
    if header_idx < 0:
        return rows

    for line in lines[header_idx + 1 :]:
        lowered = line.lower()
        if lowered.startswith("supplemental information") or lowered.startswith("patient name"):
            break
        if len(line.split()) < 4:
            continue

        dos_from, dos_to = _extract_date_range(line)
        proc_code = _extract_proc_code(line)
        money = _extract_money_values(line)
        if dos_from is None and dos_to is None:
            continue
        if proc_code is None and not money:
            continue

        units = _extract_units(line)
        billed_amount = money[0] if len(money) >= 1 else None
        allowed_amount = money[1] if len(money) >= 2 else None
        paid_amount = money[-1] if money else None

        adj_code = None
        adj_match = re.search(r"\b(?:CO|PR|OA|PI)-[A-Z0-9]+\b", line, flags=re.IGNORECASE)
        if adj_match:
            adj_code = adj_match.group(0).upper()

        rows.append(
            {
                "account_id": account_id,
                "payer_claim_number": claim_number,
                "icn": icn,
                "line_ctrl_number": None,
                "dos_from": dos_from,
                "dos_to": dos_to,
                "proc_code": proc_code,
                "units": units,
                "billed_amount": billed_amount,
                "allowed_amount": allowed_amount,
                "paid_amount": paid_amount,
                "adj_code": adj_code,
                "adj_amount": None,
                "source_layout": "monospace",
            }
        )
    return rows


def parse_era_content(content: str) -> tuple[list[dict[str, Any]], dict[str, int]]:
    counters = {
        "claim_blocks_found": 0,
        "line_rows_extracted": 0,
        "blocks_with_no_lines": 0,
        "skipped_missing_account_id": 0,
    }
    rows: list[dict[str, Any]] = []

    for block in _split_claim_blocks(content):
        counters["claim_blocks_found"] += 1
        account_id = _extract_account_id(block)
        if not account_id:
            counters["skipped_missing_account_id"] += 1

        claim_number = _extract_claim_number(block)
        icn = _extract_icn(block)
        parsed_rows = _parse_era_table_layout(
            block,
            account_id=account_id,
            claim_number=claim_number,
            icn=icn,
        )
        if not parsed_rows:
            parsed_rows = _parse_era_monospace_layout(
                block,
                account_id=account_id,
                claim_number=claim_number,
                icn=icn,
            )

        if not parsed_rows:
            counters["blocks_with_no_lines"] += 1
            continue

        rows.extend(parsed_rows)
        counters["line_rows_extracted"] += len(parsed_rows)

    return rows, counters


def _split_billed_blocks(content: str) -> list[str]:
    if not content or not content.strip():
        return []
    blocks = re.split(
        r"(?im)(?=^\s*(?:ACNT|Account(?:\s*(?:ID|Number))?|Patient\s*Ctrl\s*Nmbr|Patient\s*Name:|NAME:))",
        content,
    )
    cleaned = [blk.strip() for blk in blocks if blk and blk.strip()]
    return cleaned if cleaned else [content.strip()]


def _parse_billed_window(window_text: str, *, fallback_dates: tuple[date | None, date | None]) -> dict[str, Any] | None:
    dos_from, dos_to = _extract_date_range(window_text)
    if dos_from is None and fallback_dates[0] is not None:
        dos_from, dos_to = fallback_dates

    proc_code = _extract_proc_code(window_text)
    units = _extract_units(window_text)
    money = _extract_money_values(window_text)
    billed_amount = money[-1] if money else None

    if dos_from is None and proc_code is None and billed_amount is None:
        return None

    return {
        "dos_from": dos_from,
        "dos_to": dos_to,
        "proc_code": proc_code,
        "units": units,
        "billed_amount": billed_amount,
    }


def parse_billed_content(content: str) -> tuple[list[dict[str, Any]], dict[str, int]]:
    counters = {
        "blocks_found": 0,
        "line_rows_extracted": 0,
        "blocks_with_no_lines": 0,
        "missing_key_count": 0,
    }
    rows: list[dict[str, Any]] = []

    for block in _split_billed_blocks(content):
        counters["blocks_found"] += 1
        account_id = _extract_account_id(block)
        if not account_id:
            counters["missing_key_count"] += 1

        lines = _clean_lines(block)
        block_rows: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()

        active_dates: tuple[date | None, date | None] = (None, None)
        for i, line in enumerate(lines):
            if _DATE_RX.search(line) or _DATE_RANGE_RX.search(line):
                active_dates = _extract_date_range(line)

            if not (_DATE_RX.search(line) or "HC:" in line.upper() or "$" in line):
                continue

            window = "\n".join(lines[i : min(len(lines), i + 4)])
            parsed = _parse_billed_window(window, fallback_dates=active_dates)
            if not parsed:
                continue

            row_key = (
                parsed.get("dos_from"),
                parsed.get("dos_to"),
                parsed.get("proc_code"),
                parsed.get("units"),
                parsed.get("billed_amount"),
            )
            if row_key in seen:
                continue
            seen.add(row_key)

            block_rows.append(
                {
                    "account_id": account_id,
                    "dos_from": parsed.get("dos_from"),
                    "dos_to": parsed.get("dos_to"),
                    "proc_code": parsed.get("proc_code"),
                    "units": parsed.get("units"),
                    "billed_amount": parsed.get("billed_amount"),
                }
            )

        if not block_rows:
            counters["blocks_with_no_lines"] += 1
            continue

        rows.extend(block_rows)
        counters["line_rows_extracted"] += len(block_rows)

    return rows, counters
