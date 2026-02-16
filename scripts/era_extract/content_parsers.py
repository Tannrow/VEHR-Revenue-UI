from __future__ import annotations

import logging
import re
import hashlib
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any


_DATE_RX = re.compile(r"\b(\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{2,4})\b")
_DATE_RANGE_RX = re.compile(
    r"\b(\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{2,4})\s*[-–]\s*(\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{2,4})\b",
    re.IGNORECASE,
)
_MONEY_RX = re.compile(
    r"\(?\$?\s*(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]{1,2})?\)?"
)
_ADJ_CODE_RX = re.compile(r"^(?:CO|PR|OA|PI)-[A-Z0-9]+$", re.IGNORECASE)
_CLAIM_BLOCK_ANCHOR_RX = re.compile(r"(?i)\b(Patient\s+Name|NAME)\s*:\s*")

logger = logging.getLogger(__name__)


def _clean_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line and line.strip()]


def _to_decimal(raw: str | None) -> Decimal | None:
    if not raw:
        return None
    cleaned = raw.strip()
    is_paren = cleaned.startswith("(") and cleaned.endswith(")")
    cleaned = cleaned.replace("(", "").replace(")", "")
    cleaned = cleaned.replace(",", "").replace("$", "").strip()
    if not cleaned:
        return None
    try:
        value = Decimal(cleaned)
        return -value if is_paren else value
    except InvalidOperation:
        return None


def _extract_money_values(text: str) -> list[Decimal]:
    values: list[Decimal] = []
    for match in _MONEY_RX.finditer(text or ""):
        raw = match.group(0)
        dec = _to_decimal(raw)
        if dec is not None:
            values.append(dec)
    return values


def _extract_date(raw: str | None) -> date | None:
    if not raw:
        return None
    token = raw.strip().replace(" ", "")
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
        r"(?im)(?:Patient\s*Ctrl\s*Nmbr|ACNT|ACCT)\s*:\s*([^\n]+)",
        block or "",
    )
    if not explicit:
        return None
    raw = explicit.group(1).strip()
    if not raw:
        return None
    normalized = re.sub(r"\s+", "", raw)
    return normalized or None


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


def _extract_patient_name(block: str) -> str | None:
    if not block:
        return None
    header_region = _claim_header_region(block)
    m = re.search(r"(?im)^\s*Patient\s+Name\s*:\s*(.+?)\s*$", header_region)
    if not m:
        # Fallback only if "NAME" line includes "Patient" in the same line.
        m = re.search(r"(?im)^\s*NAME\s*:\s*(.+?)\s*$", header_region)
    if not m:
        return None
    name = m.group(1).strip()
    return name or None


def _extract_member_id(block: str) -> str | None:
    if not block:
        return None
    header_region = _claim_header_region(block)
    patterns = [
        r"(?im)^\s*Patient\s*ID\s*[:#]?\s*([^\n]+)\s*$",
        r"(?im)^\s*Member\s*ID\s*[:#]?\s*([^\n]+)\s*$",
        r"(?im)^\s*Subscriber\s*ID\s*[:#]?\s*([^\n]+)\s*$",
        r"(?im)^\s*ID\s*#\s*[:#]?\s*([^\n]+)\s*$",
        r"(?im)^\s*Medicaid\s*ID\s*[:#]?\s*([^\n]+)\s*$",
    ]
    for rx in patterns:
        m = re.search(rx, header_region)
        if m:
            raw = m.group(1).strip()
            if raw:
                normalized = re.sub(r"\s+", "", raw)
                return normalized or None
    return None


def _claim_header_region(block: str) -> str:
    if not block:
        return ""
    lines = block.splitlines()
    header_lines: list[str] = []
    for line in lines:
        lowered = line.lower()
        if "line details" in lowered or "line ctrl nmbr" in lowered:
            break
        header_lines.append(line)
    return "\n".join(header_lines)


def _block_has_member_id_label(block: str) -> bool:
    if not block:
        return False
    header_region = _claim_header_region(block)
    return bool(
        re.search(
            r"(?im)^\s*(Patient\s*ID|Member\s*ID|Subscriber\s*ID|ID\s*#|Medicaid\s*ID)\b",
            header_region,
        )
    )


def _normalize_name(name: str | None) -> str | None:
    if not name:
        return None
    cleaned = " ".join(name.strip().lower().split())
    return cleaned or None


def _extract_proc_code(text: str) -> str | None:
    if not text:
        return None
    hc = re.search(r"(?i)\bHC\s*:\s*(\d{5})\b", text)
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
    anchors = list(_CLAIM_BLOCK_ANCHOR_RX.finditer(content))
    if not anchors:
        return []
    blocks: list[str] = []
    for idx, match in enumerate(anchors):
        start = match.start()
        end = anchors[idx + 1].start() if idx + 1 < len(anchors) else len(content)
        block = content[start:end].strip()
        if block:
            blocks.append(block)
    return blocks


def _line_id_like(token: str) -> bool:
    if not token:
        return False
    return bool(re.match(r"^[A-Z0-9]{8,}(?:Z\d+)?$", token.strip(), flags=re.IGNORECASE))


def _line_id_start(line: str) -> str | None:
    if not line:
        return None
    m = re.match(r"^\s*([A-Z0-9]{6,}(?:Z\d+)?)\b", line.strip(), flags=re.IGNORECASE)
    if not m:
        return None
    return m.group(1).strip()


def _line_id_near_start(line: str) -> str | None:
    if not line:
        return None
    m = re.match(r"^\s*.{0,6}([A-Z0-9]{6,}(?:Z\d+)?)\b", line.strip(), flags=re.IGNORECASE)
    if not m:
        return None
    return m.group(1).strip()


def _looks_like_line_ctrl(token: str) -> bool:
    if not token:
        return False
    cleaned = re.sub(r"[^\w]", "", token)
    if len(cleaned) < 8:
        return False
    if not re.match(r"^[A-Za-z0-9]+$", cleaned):
        return False
    digit_count = sum(1 for ch in cleaned if ch.isdigit())
    return digit_count >= 5


def _find_line_ctrl_token(text: str) -> str | None:
    tokens = re.split(r"\s+", text.strip())
    for token in tokens[:3]:
        if _looks_like_line_ctrl(token):
            return re.sub(r"[^\w]", "", token)
    return None


def _is_junk_line(line: str) -> bool:
    if not line or not line.strip():
        return True
    stripped = line.strip()
    if re.fullmatch(r"[\W_]+", stripped):
        return True
    lowered = stripped.lower()
    if lowered in {"results:", "result:", "page", "page:"}:
        return True
    if "line ctrl nmbr" in lowered or "dates of service" in lowered:
        return True
    if "adj amount" in lowered or "adj code" in lowered:
        return True
    return False


def _has_any_alnum_token(text: str) -> bool:
    return bool(re.search(r"[A-Za-z0-9]{3,}", text or ""))

def _row_signals(text: str) -> dict[str, bool]:
    contains_digits = bool(re.search(r"\d{6,}", text))
    contains_adj = bool(re.search(r"\b(?:CO|PR|OA)-\d+\b", text, flags=re.IGNORECASE))
    contains_hc_marker = bool(re.search(r"(?i)\bHC\s*:\b", text))
    return {
        "has_date": bool(_DATE_RX.search(text)),
        "has_proc": _extract_proc_code(text) is not None,
        "has_amount": bool(_MONEY_RX.search(text)),
        "has_line_ctrl": _find_line_ctrl_token(text) is not None,
        "has_long_digits": contains_digits,
        "has_adj_code": contains_adj,
        "has_hc_marker": contains_hc_marker,
    }


def _is_header_like(lines: list[str]) -> bool:
    if not lines:
        return False
    joined = " ".join(lines).lower()
    if "line ctrl nmbr" in joined:
        return True
    if "line details" in joined:
        return True
    if "serv date" in joined and "proc" in joined:
        return True
    if "dates of service" in joined and "charge" in joined:
        return True
    if "charge" in joined and "payment" in joined and "results" in joined:
        return True
    return False


def _find_adj_code(text: str) -> tuple[str | None, int | None]:
    m = re.search(r"\b(?:CO|PR|OA)-\d+\b", text, flags=re.IGNORECASE)
    if not m:
        return None, None
    return m.group(0).upper(), m.start()


def _extract_amount_tokens_with_positions(text: str) -> list[tuple[int, Decimal]]:
    tokens: list[tuple[int, Decimal]] = []
    for m in _MONEY_RX.finditer(text or ""):
        dec = _to_decimal(m.group(0))
        if dec is not None:
            tokens.append((m.start(), dec))
    return tokens


def _pick_amount_near_keyword(tokens: list[tuple[int, Decimal]], text: str, keyword: str) -> Decimal | None:
    if not tokens:
        return None
    idx = text.lower().find(keyword.lower())
    if idx < 0:
        return None
    best = None
    best_dist = None
    for pos, val in tokens:
        if val <= 0:
            continue
        dist = abs(pos - idx)
        if best is None or dist < best_dist:
            best = val
            best_dist = dist
    return best


def _derive_confidence(row: dict[str, Any]) -> str:
    score = 0
    if row.get("line_ctrl_number"):
        score += 2
    if row.get("dos_from"):
        score += 2
    if row.get("proc_code"):
        score += 2
    if row.get("units"):
        score += 1
    if row.get("billed_amount") is not None:
        score += 2
    if row.get("paid_amount") is not None:
        score += 2
    if row.get("adj_code"):
        score += 1
    if row.get("allowed_amount") is not None:
        score += 1
    if score >= 8:
        return "high"
    if score >= 5:
        return "medium"
    return "low"


def _is_probably_junk_row(row: dict[str, Any], *, signals: dict[str, bool]) -> bool:
    # Keep all rows, but flag low-signal rows as probably junk.
    if row.get("era_row_confidence") not in {"low"}:
        return False
    has_strong = bool(row.get("dos_from")) or bool(row.get("proc_code")) or bool(row.get("billed_amount")) or bool(
        row.get("paid_amount")
    )
    if has_strong:
        return False
    # If we only had weak signals like alnum tokens, mark as probably junk.
    return not (signals.get("has_line_ctrl") or signals.get("has_long_digits") or signals.get("has_adj_code") or signals.get("has_hc_marker"))


def _parse_era_table_layout(
    block: str,
    *,
    account_id: str | None,
    claim_number: str | None,
    icn: str | None,
    patient_name: str | None,
    member_id: str | None,
    claim_id: str | None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows: list[dict[str, Any]] = []
    stats = {
        "lines_in_region": 0,
        "logical_rows_built": 0,
        "logical_rows_emitted": 0,
        "skipped_header_lines": 0,
        "skipped_empty_buffer": 0,
        "skipped_no_signals": 0,
        "skipped_junk_lines": 0,
        "built_rows_total": 0,
        "emitted_rows_total": 0,
        "dropped_rows_total": 0,
        "dropped_reason_no_signals": 0,
        "dropped_reason_header_like": 0,
        "dropped_reason_other": 0,
        "dropped_contains_digits_only": 0,
        "dropped_contains_adj_code": 0,
        "dropped_contains_hc_marker": 0,
    }
    lines = _clean_lines(block)
    if not lines:
        return rows, stats

    header_idx = -1
    for i, line in enumerate(lines):
        if "Line Ctrl Nmbr".lower() in line.lower():
            header_idx = i
            break
    if header_idx < 0:
        return rows, stats

    region: list[str] = []
    for line in lines[header_idx + 1 :]:
        lowered = line.lower()
        if lowered.startswith("supplemental information") or lowered.startswith("patient name"):
            break
        region.append(line)
    if not region:
        return rows, stats

    stats["lines_in_region"] = len(region)

    buffer: list[str] = []
    buffer_signals = {"has_date": False, "has_proc": False, "has_amount": False, "has_line_ctrl": False}

    def finalize_buffer(lines_buf: list[str]) -> None:
        if not lines_buf:
            stats["skipped_empty_buffer"] += 1
            return
        stats["logical_rows_built"] += 1
        stats["built_rows_total"] += 1
        if _is_header_like(lines_buf):
            stats["skipped_header_lines"] += 1
            stats["dropped_rows_total"] += 1
            stats["dropped_reason_header_like"] += 1
            return
        joined = "\n".join(lines_buf).strip()
        signals = _row_signals(joined)
        if not any(signals.values()):
            if not _has_any_alnum_token(joined):
                stats["skipped_no_signals"] += 1
                stats["dropped_rows_total"] += 1
                stats["dropped_reason_no_signals"] += 1
                if signals.get("has_long_digits"):
                    stats["dropped_contains_digits_only"] += 1
                if signals.get("has_adj_code"):
                    stats["dropped_contains_adj_code"] += 1
                if signals.get("has_hc_marker"):
                    stats["dropped_contains_hc_marker"] += 1
                return

        line_id = _find_line_ctrl_token(joined) or (_line_id_start(lines_buf[0]) if lines_buf else None)
        dos_from, dos_to = _extract_date_range(joined)

        proc_code = _extract_proc_code(joined)
        units = _extract_units(joined)

        amounts_with_pos = _extract_amount_tokens_with_positions(joined)
        amounts = [val for _, val in amounts_with_pos]
        positive = [val for val in amounts if val > 0]
        billed_amount = max(positive) if positive else None
        paid_amount = _pick_amount_near_keyword(amounts_with_pos, joined, "payment")
        if paid_amount is None and positive:
            paid_amount = positive[-1]
        allowed_amount = None
        if positive and billed_amount is not None:
            mids = [v for v in positive if v != billed_amount and v != paid_amount]
            if mids:
                allowed_amount = mids[0]

        adj_code, adj_pos = _find_adj_code(joined)
        adj_amount = None
        if adj_code and adj_pos is not None and amounts_with_pos:
            best = None
            best_dist = None
            for pos, val in amounts_with_pos:
                dist = abs(pos - adj_pos)
                if best is None or dist < best_dist:
                    best = val
                    best_dist = dist
            adj_amount = best

        if not (
            line_id
            or dos_from
            or proc_code
            or amounts_with_pos
            or signals.get("has_long_digits")
            or signals.get("has_adj_code")
            or signals.get("has_hc_marker")
        ):
            if not _has_any_alnum_token(joined):
                stats["skipped_no_signals"] += 1
                stats["dropped_rows_total"] += 1
                stats["dropped_reason_no_signals"] += 1
                if signals.get("has_long_digits"):
                    stats["dropped_contains_digits_only"] += 1
                if signals.get("has_adj_code"):
                    stats["dropped_contains_adj_code"] += 1
                if signals.get("has_hc_marker"):
                    stats["dropped_contains_hc_marker"] += 1
                return

        row = {
            "account_id": account_id,
            "payer_claim_number": claim_number,
            "icn": icn,
            "patient_name": patient_name,
            "member_id": member_id,
            "claim_id": claim_id,
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
        row["era_row_confidence"] = _derive_confidence(row)
        row["row_is_probably_junk"] = _is_probably_junk_row(row, signals=signals)

        rows.append(row)
        stats["logical_rows_emitted"] += 1
        stats["emitted_rows_total"] += 1

    for line in region:
        if _is_junk_line(line):
            stats["skipped_junk_lines"] += 1
            continue
        line_start_id = _line_id_near_start(line)
        line_signals = _row_signals(line)
        has_hc = bool(re.search(r"(?i)\bHC\s*:\s*\d{5}\b", line))
        line_proc = _extract_proc_code(line)
        new_row = False
        if line_start_id:
            new_row = True
        elif line_signals["has_date"] and any(buffer_signals.values()):
            new_row = True
        elif has_hc and (buffer_signals["has_date"] or buffer_signals["has_amount"] or buffer_signals["has_proc"]):
            new_row = True
        elif line_proc and buffer_signals["has_proc"]:
            new_row = True

        if new_row and buffer:
            finalize_buffer(buffer)
            buffer = []
            buffer_signals = {"has_date": False, "has_proc": False, "has_amount": False, "has_line_ctrl": False}

        buffer.append(line)
        buffer_signals["has_date"] = buffer_signals["has_date"] or line_signals["has_date"]
        buffer_signals["has_proc"] = buffer_signals["has_proc"] or line_signals["has_proc"]
        buffer_signals["has_amount"] = buffer_signals["has_amount"] or line_signals["has_amount"]
        buffer_signals["has_line_ctrl"] = buffer_signals["has_line_ctrl"] or line_signals["has_line_ctrl"]

    if buffer:
        finalize_buffer(buffer)

    return rows, stats


def _parse_era_monospace_layout(
    block: str,
    *,
    account_id: str | None,
    claim_number: str | None,
    icn: str | None,
    patient_name: str | None,
    member_id: str | None,
    claim_id: str | None,
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

        row = {
            "account_id": account_id,
            "payer_claim_number": claim_number,
            "icn": icn,
            "patient_name": patient_name,
            "member_id": member_id,
            "claim_id": claim_id,
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
        row["era_row_confidence"] = _derive_confidence(row)
        row["row_is_probably_junk"] = _is_probably_junk_row(row, signals=_row_signals(line))
        rows.append(row)
    return rows


def parse_era_content(
    content: str,
    *,
    job_id: str | None = None,
    debug: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    counters = {
        "claim_blocks_found": 0,
        "line_rows_extracted": 0,
        "blocks_with_no_lines": 0,
        "skipped_missing_account_id": 0,
        "patient_name_anchors": 0,
        "name_anchors": 0,
        "line_details_anchors": 0,
        "acnt_anchors": 0,
        "patient_ctrl_anchors": 0,
        "blocks_after_split": 0,
        "blocks_with_account_id": 0,
        "blocks_skipped_missing_account_id": 0,
        "blocks_with_lines": 0,
        "total_line_rows": 0,
        "rows_emitted_table": 0,
        "rows_emitted_monospace": 0,
        "skipped_header_lines": 0,
        "skipped_empty_buffer": 0,
        "skipped_no_signals": 0,
        "skipped_junk_lines": 0,
        "built_rows_total": 0,
        "emitted_rows_total": 0,
        "dropped_rows_total": 0,
        "dropped_reason_no_signals": 0,
        "dropped_reason_header_like": 0,
        "dropped_reason_other": 0,
        "dropped_contains_digits_only": 0,
        "dropped_contains_adj_code": 0,
        "dropped_contains_hc_marker": 0,
        "blocks_with_patient_name": 0,
        "blocks_missing_patient_name": 0,
        "distinct_patient_name_hashes_count": 0,
        "rows_returned_by_parser": 0,
        "blocks_with_member_id": 0,
        "blocks_missing_member_id": 0,
        "distinct_member_id_count_before": 0,
        "distinct_member_id_count_after": 0,
        "header_member_id_present": 0,
        "member_id_global_suppressed": 0,
        "distinct_claim_id_count": 0,
        "distinct_patient_name_count_before": 0,
        "distinct_patient_name_count_after": 0,
        "patient_name_global_suppressed": 0,
    }
    rows: list[dict[str, Any]] = []
    patient_name_hashes: set[str] = set()
    patient_name_values: set[str] = set()
    member_id_values: set[str] = set()
    claim_id_values: set[str] = set()
    header_member_id = _extract_member_id((content or "")[:2000])
    if header_member_id:
        counters["header_member_id_present"] = 1

    if content:
        counters["patient_name_anchors"] = len(re.findall(r"(?i)Patient\s+Name\s*:", content))
        counters["name_anchors"] = len(re.findall(r"(?i)\bNAME\s*:", content))
        counters["line_details_anchors"] = len(re.findall(r"(?i)Line\s+Details", content))
        counters["acnt_anchors"] = len(re.findall(r"(?i)\bACNT\s*:", content))
        counters["patient_ctrl_anchors"] = len(re.findall(r"(?i)Patient\s*Ctrl\s*Nmbr", content))

    blocks = _split_claim_blocks(content)
    counters["blocks_after_split"] = len(blocks)

    for block_idx, block in enumerate(blocks, start=1):
        counters["claim_blocks_found"] += 1
        account_id = _extract_account_id(block)
        if not account_id:
            counters["skipped_missing_account_id"] += 1
            counters["blocks_skipped_missing_account_id"] += 1
            continue
        counters["blocks_with_account_id"] += 1

        claim_number = _extract_claim_number(block)
        icn = _extract_icn(block)
        patient_name = _extract_patient_name(block)
        member_id = _extract_member_id(block)
        if member_id and header_member_id and member_id == header_member_id and not _block_has_member_id_label(block):
            member_id = None
        if patient_name:
            counters["blocks_with_patient_name"] += 1
            normalized = _normalize_name(patient_name)
            if normalized:
                digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
                patient_name_hashes.add(digest)
                patient_name_values.add(normalized)
        else:
            counters["blocks_missing_patient_name"] += 1
        if member_id:
            counters["blocks_with_member_id"] += 1
            member_id_values.add(member_id)
        else:
            counters["blocks_missing_member_id"] += 1

        claim_id = account_id or None
        if claim_id:
            claim_id_values.add(claim_id)
        parsed_rows: list[dict[str, Any]] = []
        table_rows, table_stats = _parse_era_table_layout(
            block,
            account_id=account_id,
            claim_number=claim_number,
            icn=icn,
            patient_name=patient_name,
            member_id=member_id,
            claim_id=claim_id,
        )
        monospace_rows = _parse_era_monospace_layout(
            block,
            account_id=account_id,
            claim_number=claim_number,
            icn=icn,
            patient_name=patient_name,
            member_id=member_id,
            claim_id=claim_id,
        )
        parsed_rows.extend(table_rows)
        parsed_rows.extend(monospace_rows)

        counters["rows_emitted_table"] += table_stats.get("logical_rows_emitted", 0)
        counters["rows_emitted_monospace"] += len(monospace_rows)
        counters["skipped_header_lines"] += table_stats.get("skipped_header_lines", 0)
        counters["skipped_empty_buffer"] += table_stats.get("skipped_empty_buffer", 0)
        counters["skipped_no_signals"] += table_stats.get("skipped_no_signals", 0)
        counters["skipped_junk_lines"] += table_stats.get("skipped_junk_lines", 0)
        counters["built_rows_total"] += table_stats.get("built_rows_total", 0)
        counters["emitted_rows_total"] += table_stats.get("emitted_rows_total", 0)
        counters["dropped_rows_total"] += table_stats.get("dropped_rows_total", 0)
        counters["dropped_reason_no_signals"] += table_stats.get("dropped_reason_no_signals", 0)
        counters["dropped_reason_header_like"] += table_stats.get("dropped_reason_header_like", 0)
        counters["dropped_reason_other"] += table_stats.get("dropped_reason_other", 0)
        counters["dropped_contains_digits_only"] += table_stats.get("dropped_contains_digits_only", 0)
        counters["dropped_contains_adj_code"] += table_stats.get("dropped_contains_adj_code", 0)
        counters["dropped_contains_hc_marker"] += table_stats.get("dropped_contains_hc_marker", 0)

        if debug:
            print(
                "[era_extract] block_diag "
                f"block={block_idx} physical_lines_in_region={table_stats.get('lines_in_region', 0)} "
                f"logical_rows_built={table_stats.get('logical_rows_built', 0)} "
                f"logical_rows_emitted={table_stats.get('logical_rows_emitted', 0)}"
            )

        # Keep all parsed rows; no dedupe here to preserve row yield.

        if not parsed_rows:
            counters["blocks_with_no_lines"] += 1
            continue

        counters["blocks_with_lines"] += 1
        counters["line_rows_extracted"] += len(parsed_rows)
        counters["total_line_rows"] += len(parsed_rows)
        rows.extend(parsed_rows)

    counters["distinct_patient_name_hashes_count"] = len(patient_name_hashes)
    counters["distinct_member_id_count_before"] = len(member_id_values)
    counters["distinct_claim_id_count"] = len(claim_id_values)
    counters["distinct_patient_name_count_before"] = len(patient_name_values)

    if counters["distinct_claim_id_count"] > 1 and counters["distinct_patient_name_count_before"] == 1:
        for row in rows:
            row["patient_name"] = None
        counters["patient_name_global_suppressed"] = 1
        counters["distinct_patient_name_count_after"] = 0
    else:
        counters["patient_name_global_suppressed"] = 0
        counters["distinct_patient_name_count_after"] = len(
            {row.get("patient_name") for row in rows if row.get("patient_name")}
        )

    if counters["distinct_claim_id_count"] > 1 and counters["distinct_member_id_count_before"] == 1:
        for row in rows:
            row["member_id"] = None
        counters["member_id_global_suppressed"] = 1
        counters["distinct_member_id_count_after"] = 0
    else:
        counters["distinct_member_id_count_after"] = len({row.get("member_id") for row in rows if row.get("member_id")})

    if debug:
        print(
            "[era_extract] table_totals "
            f"rows_emitted_table={counters['rows_emitted_table']} "
            f"rows_emitted_monospace={counters['rows_emitted_monospace']} "
            f"skipped_header_lines={counters['skipped_header_lines']} "
            f"skipped_empty_buffer={counters['skipped_empty_buffer']} "
            f"skipped_no_signals={counters['skipped_no_signals']} "
            f"skipped_junk_lines={counters['skipped_junk_lines']} "
            f"built_rows_total={counters['built_rows_total']} "
            f"emitted_rows_total={counters['emitted_rows_total']} "
            f"dropped_rows_total={counters['dropped_rows_total']} "
            f"dropped_reason_no_signals={counters['dropped_reason_no_signals']} "
            f"dropped_reason_header_like={counters['dropped_reason_header_like']} "
            f"dropped_reason_other={counters['dropped_reason_other']} "
            f"dropped_contains_digits_only={counters['dropped_contains_digits_only']} "
            f"dropped_contains_adj_code={counters['dropped_contains_adj_code']} "
            f"dropped_contains_hc_marker={counters['dropped_contains_hc_marker']}"
        )
        print(
            "[era_extract] patient_name_totals "
            f"blocks_with_patient_name={counters['blocks_with_patient_name']} "
            f"blocks_missing_patient_name={counters['blocks_missing_patient_name']} "
            f"distinct_patient_name_hashes_count={counters['distinct_patient_name_hashes_count']}"
        )

    counters["rows_returned_by_parser"] = len(rows)
    if job_id:
        logger.info(
            "era_parse_diagnostics job_id=%s patient_name_anchors=%s name_anchors=%s line_details_anchors=%s acnt_anchors=%s "
            "patient_ctrl_anchors=%s blocks_after_split=%s blocks_with_account_id=%s blocks_skipped_missing_account_id=%s "
            "blocks_with_lines=%s blocks_with_no_lines=%s total_line_rows=%s",
            job_id,
            counters["patient_name_anchors"],
            counters["name_anchors"],
            counters["line_details_anchors"],
            counters["acnt_anchors"],
            counters["patient_ctrl_anchors"],
            counters["blocks_after_split"],
            counters["blocks_with_account_id"],
            counters["blocks_skipped_missing_account_id"],
            counters["blocks_with_lines"],
            counters["blocks_with_no_lines"],
            counters["total_line_rows"],
        )

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


def collect_content_diagnostics(content: str, *, mode: str) -> dict[str, int]:
    counters = {
        "patient_name_anchors": 0,
        "name_anchors": 0,
        "line_details_anchors": 0,
        "acnt_anchors": 0,
        "patient_ctrl_anchors": 0,
        "blocks_after_split": 0,
        "blocks_with_account_id": 0,
        "skipped_missing_account_id": 0,
        "blocks_with_lines": 0,
        "total_line_rows": 0,
    }

    if content:
        counters["patient_name_anchors"] = len(re.findall(r"(?i)Patient\s+Name\s*:", content))
        counters["name_anchors"] = len(re.findall(r"(?i)\bNAME\s*:", content))
        counters["line_details_anchors"] = len(re.findall(r"(?i)Line\s+Details", content))
        counters["acnt_anchors"] = len(re.findall(r"(?i)\bACNT\s*:", content))
        counters["patient_ctrl_anchors"] = len(re.findall(r"(?i)Patient\s*Ctrl\s*Nmbr", content))

    if mode == "billed":
        blocks = _split_billed_blocks(content)
        counters["blocks_after_split"] = len(blocks)
        for block in blocks:
            account_id = _extract_account_id(block)
            if not account_id:
                counters["skipped_missing_account_id"] += 1
            else:
                counters["blocks_with_account_id"] += 1
    else:
        blocks = _split_claim_blocks(content)
        counters["blocks_after_split"] = len(blocks)
        for block in blocks:
            account_id = _extract_account_id(block)
            if not account_id:
                counters["skipped_missing_account_id"] += 1
            else:
                counters["blocks_with_account_id"] += 1

    return counters


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


def parse_billed_content(content: str, billed_track: str) -> tuple[list[dict[str, Any]], dict[str, int]]:
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
        claim_id = None
        m = re.search(r"(?im)^\s*Claim\s*ID\s*:\s*([A-Za-z0-9\-]+)\s*$", block)
        if m:
            claim_id = m.group(1).strip()
        member_id = _extract_member_id(block)

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
                    "claim_id": claim_id or account_id,
                    "member_id": member_id,
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
