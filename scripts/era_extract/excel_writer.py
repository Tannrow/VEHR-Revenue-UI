from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

import pandas as pd
from openpyxl.utils import get_column_letter


@dataclass(frozen=True)
class TableFrame:
    name: str
    df: pd.DataFrame


def write_lines_xlsx(out_path: Path, rows: Sequence[dict[str, Any]]) -> None:
    """Write a single-sheet workbook named 'Lines' with the expected columns."""
    cols = [
        "Patient Name",
        "Patient ID",
        "Claim ID",
        "Date of Service",
        "Modifier Units",
        "Charge",
        "Payment",
    ]
    df = pd.DataFrame(list(rows))
    # Enforce column order and ensure columns exist even if empty.
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    df = df[cols]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Lines")
        ws = writer.book["Lines"]
        ws.freeze_panes = "A2"
        for col_idx, col in enumerate(cols, start=1):
            series = df[col].astype(str)
            max_len = max([len(col)] + [len(v) for v in series.head(500).tolist()])
            ws.column_dimensions[get_column_letter(col_idx)].width = min(max(12, max_len + 2), 60)


def _safe_sheet_name(name: str) -> str:
    # Excel: max 31 chars, cannot contain: : \ / ? * [ ]
    bad = [":", "\\", "/", "?", "*", "[", "]"]
    for ch in bad:
        name = name.replace(ch, " ")
    name = " ".join(name.split()).strip()
    return (name or "Table")[:31]


def write_tables_to_xlsx(out_path: Path, tables: list[TableFrame]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        if not tables:
            pd.DataFrame([{"message": "No tables detected in this document."}]).to_excel(
                writer, index=False, sheet_name="NoTables"
            )
            return

        used_names: set[str] = set()
        for i, t in enumerate(tables, start=1):
            base = _safe_sheet_name(t.name or f"Table {i}")
            sheet = base
            n = 2
            while sheet in used_names:
                suffix = f" {n}"
                sheet = _safe_sheet_name(base[: max(0, 31 - len(suffix))] + suffix)
                n += 1
            used_names.add(sheet)

            t.df.to_excel(writer, index=False, sheet_name=sheet)

            ws = writer.book[sheet]
            ws.freeze_panes = "A2"

            # Auto-size columns (approx) with a cap to keep it readable.
            for col_idx, col in enumerate(t.df.columns, start=1):
                series = t.df[col].astype(str) if col in t.df.columns else pd.Series([""])
                max_len = max([len(str(col))] + [len(v) for v in series.head(200).tolist()])
                width = min(max(10, max_len + 2), 60)
                ws.column_dimensions[get_column_letter(col_idx)].width = width
