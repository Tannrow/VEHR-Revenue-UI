from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Optional

from scripts.era_extract.docintel_client import create_document_intelligence_client
from scripts.era_extract.excel_writer import write_lines_xlsx


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _config_path() -> Path:
    return Path(__file__).resolve().with_name("config.json")


def _default_out_for(pdf_path: Path) -> Path:
    return _repo_root() / "outputs" / "eras" / f"{pdf_path.stem}__extracted.xlsx"


def _norm(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def _load_config() -> dict[str, Any]:
    return json.loads(_config_path().read_text(encoding="utf-8"))


def _iter_kvpairs(result: Any):
    for kv in getattr(result, "key_value_pairs", []) or []:
        key = getattr(kv, "key", None)
        val = getattr(kv, "value", None)
        ktxt = (getattr(key, "content", "") or "").strip()
        vtxt = (getattr(val, "content", "") or "").strip()
        if ktxt or vtxt:
            yield ktxt, vtxt


def _extract_patient_fields(result: Any, cfg: dict[str, Any]) -> tuple[str, str]:
    name_hints = [h.lower() for h in (cfg.get("patient_name_key_hints") or [])]
    id_hints = [h.lower() for h in (cfg.get("patient_id_key_hints") or [])]

    patient_name = ""
    patient_id = ""

    for k, v in _iter_kvpairs(result):
        nk = _norm(k)
        if not patient_name and any(h in nk for h in name_hints):
            patient_name = v.strip()
        if not patient_id and any(h in nk for h in id_hints):
            patient_id = v.strip()
        if patient_name and patient_id:
            return patient_name, patient_id

    # Fallback: regex over full OCR content. This is intentionally conservative.
    content = (getattr(result, "content", "") or "").strip()
    if content:
        m = re.search(r"(?im)^\s*patient\s+name\s*[:\-]?\s*(.+?)\s*$", content)
        if m:
            patient_name = patient_name or m.group(1).strip()
        m = re.search(r"(?im)^\s*patient\s+id\s*[:\-]?\s*([A-Za-z0-9\-]+)\s*$", content)
        if m:
            patient_id = patient_id or m.group(1).strip()

    return patient_name, patient_id


def _table_header_text_by_col(table: Any) -> dict[int, str]:
    # Build header (row 0) text per column; handles multi-cell headers by joining.
    col_text: dict[int, list[str]] = {}
    for cell in getattr(table, "cells", []) or []:
        r = int(getattr(cell, "row_index", 0))
        c = int(getattr(cell, "column_index", 0))
        if r != 0:
            continue
        txt = (getattr(cell, "content", "") or "").strip()
        if not txt:
            continue
        col_text.setdefault(c, []).append(txt)
    return {c: " ".join(v).strip() for c, v in col_text.items()}


def _find_detail_table(tables: list[Any], required_headers: list[str]) -> tuple[Optional[Any], Optional[dict[str, int]]]:
    req = [_norm(x) for x in required_headers]

    best = None
    best_match = -1
    best_cols: Optional[dict[str, int]] = None

    for t in tables:
        headers = _table_header_text_by_col(t)
        # For matching, treat each column header as a normalized blob.
        norm_headers = {c: _norm(txt) for c, txt in headers.items()}

        cols: dict[str, int] = {}
        match_count = 0
        for want in req:
            found_col = None
            for c, htxt in norm_headers.items():
                if want and want in htxt:
                    found_col = c
                    break
            if found_col is not None:
                match_count += 1
                cols[want] = found_col

        if match_count > best_match:
            best_match = match_count
            best = t
            best_cols = cols

    if best is None or best_match < len(req):
        return None, None
    return best, best_cols


def _cell_text_grid(table: Any) -> list[list[str]]:
    row_count = int(getattr(table, "row_count", 0) or 0)
    col_count = int(getattr(table, "column_count", 0) or 0)
    grid = [["" for _ in range(col_count)] for _ in range(row_count)]
    for cell in getattr(table, "cells", []) or []:
        r = int(getattr(cell, "row_index", 0))
        c = int(getattr(cell, "column_index", 0))
        txt = (getattr(cell, "content", "") or "").strip()
        if 0 <= r < row_count and 0 <= c < col_count and txt:
            if not grid[r][c]:
                grid[r][c] = txt
    return grid


def _pick_modifier_units_col(table: Any, required_cols: set[int], hints: list[str], header_by_col: dict[int, str]) -> Optional[int]:
    norm_hints = [_norm(h) for h in hints]
    for c, hdr in header_by_col.items():
        if c in required_cols:
            continue
        nh = _norm(hdr)
        if any(h in nh for h in norm_hints):
            return c
    return None


def extract_era_lines(pdf_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cfg = _load_config()
    required_headers = cfg.get("detail_table_required_headers") or []
    if not required_headers:
        raise RuntimeError("config.json missing detail_table_required_headers")

    client, doc_cfg = create_document_intelligence_client()
    with pdf_path.open("rb") as f:
        poller = client.begin_analyze_document(model_id="prebuilt-layout", body=f)
    result = poller.result()

    patient_name, patient_id = _extract_patient_fields(result, cfg)
    tables = list(getattr(result, "tables", []) or [])

    detail_table, cols = _find_detail_table(tables, list(required_headers))
    if not detail_table or not cols:
        return (
            [],
            {
                "patient_name": patient_name,
                "patient_id": patient_id,
                "table_count": len(tables),
                "error": "No ERA detail table found",
            },
        )

    # Map required header normalized strings to actual columns.
    req_norm = [_norm(x) for x in required_headers]
    line_ctrl_col = cols[_norm(required_headers[0])] if _norm(required_headers[0]) in cols else cols[req_norm[0]]
    dos_col = cols[_norm(required_headers[1])] if _norm(required_headers[1]) in cols else cols[req_norm[1]]
    charge_col = cols[_norm(required_headers[2])] if _norm(required_headers[2]) in cols else cols[req_norm[2]]
    payment_col = cols[_norm(required_headers[3])] if _norm(required_headers[3]) in cols else cols[req_norm[3]]

    header_by_col = _table_header_text_by_col(detail_table)
    modifier_col = _pick_modifier_units_col(
        detail_table,
        required_cols={line_ctrl_col, dos_col, charge_col, payment_col},
        hints=list(cfg.get("modifier_units_header_hints") or []),
        header_by_col=header_by_col,
    )
    if modifier_col is None:
        # Fallback: choose the first non-required column (stable ordering).
        for c in sorted(header_by_col.keys()):
            if c not in {line_ctrl_col, dos_col, charge_col, payment_col}:
                modifier_col = c
                break

    grid = _cell_text_grid(detail_table)
    rows_out: list[dict[str, Any]] = []

    for r in range(1, len(grid)):
        row = grid[r]
        if not any(x.strip() for x in row):
            continue
        claim_id = row[line_ctrl_col].strip() if line_ctrl_col < len(row) else ""
        dos = row[dos_col].strip() if dos_col < len(row) else ""
        modifier_units = row[modifier_col].strip() if (modifier_col is not None and modifier_col < len(row)) else ""
        charge = row[charge_col].strip() if charge_col < len(row) else ""
        payment = row[payment_col].strip() if payment_col < len(row) else ""

        # Skip rows that don't look like actual lines.
        if not claim_id and not (dos or charge or payment):
            continue

        rows_out.append(
            {
                "Patient Name": patient_name,
                "Patient ID": patient_id,
                "Claim ID": claim_id,
                "Date of Service": dos,
                "Modifier Units": modifier_units,
                "Charge": charge,
                "Payment": payment,
            }
        )

    meta = {
        "model_id": "prebuilt-layout",
        "patient_name": patient_name,
        "patient_id": patient_id,
        "table_count": len(tables),
        "extracted_lines": len(rows_out),
    }
    return rows_out, meta


def run(pdf_path: Path, out_path: Optional[Path] = None) -> Path:
    pdf_path = pdf_path.resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(str(pdf_path))
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a .pdf file, got: {pdf_path.name}")

    out_path = (out_path or _default_out_for(pdf_path)).resolve()

    print(f"[era_extract] analyzing: {pdf_path.name} (model=prebuilt-layout)")
    lines, meta = extract_era_lines(pdf_path)

    if not lines:
        print(
            "[era_extract] No ERA detail table found — check scripts/era_extract/config.json keywords. "
            f"(tables_detected={meta.get('table_count')})"
        )
    else:
        print(f"[era_extract] extracted_lines={meta.get('extracted_lines')}")

    write_lines_xlsx(out_path, lines)
    print(f"[era_extract] wrote: {out_path}")
    return out_path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Extract ERA patient + claim lines to Excel (sheet: Lines).")
    p.add_argument("--pdf", required=True, help="Path to an ERA PDF")
    p.add_argument("--out", required=False, help="Output .xlsx path (default: outputs/eras/<pdf>__extracted.xlsx)")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    run(Path(args.pdf), Path(args.out) if args.out else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

