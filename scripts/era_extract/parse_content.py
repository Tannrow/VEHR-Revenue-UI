from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Optional, Sequence, Tuple

from scripts.era_extract.content_parsers import collect_content_diagnostics
from scripts.era_extract.content_parsers import parse_billed_content, parse_era_content
from scripts.era_extract.excel_writer import write_recon_lines_xlsx


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_out_for(label: str) -> Path:
    safe = "_".join(label.strip().split()) or "era"
    return _repo_root() / "outputs" / "eras" / f"{safe}__content.xlsx"


def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_content_from_analyze_json(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    content: Optional[str] = None

    if isinstance(data, dict):
        analyze = data.get("analyzeResult")
        if isinstance(analyze, dict):
            content = analyze.get("content")
        if content is None:
            raw = data.get("content")
            if isinstance(raw, str):
                content = raw

    if not content or not isinstance(content, str):
        raise ValueError("analyzeResult.content missing or empty in JSON")
    return content


def _print_diag(rows: list[dict[str, Any]], counters: dict[str, int], *, label: str) -> None:
    print(f"[era_extract] {label} parse diagnostics (PHI-safe counts)")
    print(f"[era_extract] lines_extracted={len(rows)}")
    for key in sorted(counters.keys()):
        print(f"[era_extract] {key}={counters[key]}")


def _parse_content(
    *,
    content: str,
    doc_type: str,
    billed_track: Optional[str],
    debug: bool,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    if doc_type == "billed":
        if not billed_track:
            raise ValueError("--billed-track is required when --doc-type billed")
        return parse_billed_content(content, billed_track=billed_track)
    return parse_era_content(content, debug=debug)


def _candidate_name(path: Path) -> bool:
    name = path.name.lower()
    return any(token in name for token in ("era", "docintel", "analyze"))


def _candidate_by_content(path: Path) -> bool:
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception:
        return False
    try:
        data = json.loads(raw)
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    analyze = data.get("analyzeResult")
    if isinstance(analyze, dict) and "content" in analyze:
        return True
    if "content" in data:
        return True
    return False


def _find_analyze_json(search_root: Path) -> list[Path]:
    candidates: list[Path] = []
    for root, _, files in os.walk(search_root):
        for fn in files:
            if not fn.lower().endswith(".json"):
                continue
            path = Path(root) / fn
            if _candidate_name(path) or _candidate_by_content(path):
                candidates.append(path)
    return candidates


def _format_candidates(paths: Sequence[Path], *, root: Path) -> list[str]:
    rows: list[str] = []
    for p in paths:
        try:
            rel = p.relative_to(root)
            rel_txt = str(rel)
        except Exception:
            rel_txt = str(p)
        try:
            size = p.stat().st_size
        except Exception:
            size = 0
        rows.append(f"{rel_txt} ({size} bytes)")
    return rows


def _friendly_missing_file_error(path: Path, *, search_root: Path) -> int:
    abs_path = path.resolve()
    cwd = Path.cwd().resolve()
    print("[era_extract] ERROR: analyze JSON file not found")
    print(f"[era_extract] attempted_path={abs_path}")
    print(f"[era_extract] cwd={cwd}")
    candidates = _find_analyze_json(search_root)
    if candidates:
        print("[era_extract] candidate JSON files:")
        rows = _format_candidates(candidates, root=search_root.resolve())
        for idx, row in enumerate(rows, start=1):
            print(f"[era_extract] {idx}. {row}")
    else:
        print("[era_extract] candidate JSON files: none found")
    print("[era_extract] Tip: use --find-analyze-json --search-root <path>")
    return 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Parse ERA/billed content from Azure DI JSON or plain text without Azure SDK."
    )

    src = p.add_mutually_exclusive_group(required=False)
    src.add_argument("--analyze-json", dest="analyze_json", help="Path to Azure DI JSON (analyzeResult.content)")
    src.add_argument("--content-txt", dest="content_txt", help="Path to plain text content")

    p.add_argument("--out-xlsx", required=False, help="Output .xlsx path (default: outputs/eras/<label>__content.xlsx)")
    p.add_argument("--doc-type", choices=["era", "billed"], default="era", help="Which parser to use")
    p.add_argument(
        "--billed-track",
        required=False,
        choices=["chpw", "coordinated_care", "wellpoint", "billing"],
        help="Track label used for billed parsing",
    )
    p.add_argument("--search-root", default=".", help="Root to search for analyze JSON when using --find-analyze-json")
    p.add_argument("--find-analyze-json", action="store_true", help="Search for Azure DI JSON under --search-root")
    p.add_argument("--print-cwd", action="store_true", help="Print current working directory and exit")
    p.add_argument("--dry-run", action="store_true", help="Only show candidate files; do not auto-select")
    p.add_argument("--debug", action="store_true", help="Print PHI-safe debug counters only")

    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if args.print_cwd:
        print(Path.cwd().resolve())
        return 0

    if args.find_analyze_json:
        root = Path(args.search_root)
        candidates = _find_analyze_json(root)
        if not candidates:
            print("[era_extract] No analyze JSON candidates found.")
            return 2
        rows = _format_candidates(candidates, root=root.resolve())
        print("[era_extract] Analyze JSON candidates:")
        for idx, row in enumerate(rows, start=1):
            print(f"[era_extract] {idx}. {row}")
        if len(candidates) == 1 and not args.dry_run:
            args.analyze_json = str(candidates[0])
            args.content_txt = None
        else:
            print("[era_extract] If you want to use one, pass --analyze-json with the path above.")
            return 2
    if not args.analyze_json and not args.content_txt:
        print("[era_extract] ERROR: must provide --analyze-json or --content-txt (or use --find-analyze-json).")
        return 2

    content_label = "era"
    try:
        if args.analyze_json:
            path = Path(args.analyze_json)
            if not path.exists():
                return _friendly_missing_file_error(path, search_root=Path(args.search_root))
            content = _load_content_from_analyze_json(path)
            content_label = path.stem
        else:
            path = Path(args.content_txt)
            if not path.exists():
                print("[era_extract] ERROR: content text file not found")
                print(f"[era_extract] attempted_path={path.resolve()}")
                print(f"[era_extract] cwd={Path.cwd().resolve()}")
                return 2
            content = _load_text(path)
            content_label = path.stem
    except Exception as exc:
        print("[era_extract] ERROR: failed to load content")
        print(f"[era_extract] reason={exc}")
        return 2

    rows, counters = _parse_content(
        content=content,
        doc_type=args.doc_type,
        billed_track=args.billed_track,
        debug=args.debug,
    )
    diag = collect_content_diagnostics(content, mode=args.doc_type)
    diag["blocks_with_lines"] = counters.get("blocks_with_lines", 0)
    diag["total_line_rows"] = counters.get("total_line_rows", counters.get("line_rows_extracted", len(rows)))
    diag["distinct_account_ids_count"] = len({row.get("account_id") for row in rows if row.get("account_id")})
    diag["blocks_skipped_missing_account_id"] = diag.pop("skipped_missing_account_id", 0)
    if args.debug:
        diag["blocks_with_patient_name"] = counters.get("blocks_with_patient_name", 0)
        diag["blocks_missing_patient_name"] = counters.get("blocks_missing_patient_name", 0)
        diag["distinct_patient_name_hashes_count"] = counters.get("distinct_patient_name_hashes_count", 0)
        diag["rows_returned_by_parser"] = counters.get("rows_returned_by_parser", len(rows))
        diag["distinct_member_id_count_before"] = counters.get("distinct_member_id_count_before", 0)
        diag["distinct_member_id_count_after"] = counters.get("distinct_member_id_count_after", 0)
        diag["distinct_patient_name_count_before"] = counters.get("distinct_patient_name_count_before", 0)
        diag["distinct_patient_name_count_after"] = counters.get("distinct_patient_name_count_after", 0)
        diag["blocks_with_member_id"] = counters.get("blocks_with_member_id", 0)
        diag["blocks_missing_member_id"] = counters.get("blocks_missing_member_id", 0)
        diag["header_member_id_present"] = bool(counters.get("header_member_id_present", 0))
        diag["member_id_global_suppressed"] = bool(counters.get("member_id_global_suppressed", 0))
        diag["distinct_claim_id_count"] = counters.get("distinct_claim_id_count", 0)
        diag["patient_name_global_suppressed"] = bool(counters.get("patient_name_global_suppressed", 0))

    out_path = Path(args.out_xlsx) if args.out_xlsx else _default_out_for(content_label)
    sheet = "billed_lines" if args.doc_type == "billed" else "era_lines"
    write_recon_lines_xlsx(out_path, rows, sheet_name=sheet)

    label = "billed content" if args.doc_type == "billed" else "era content"
    _print_diag(rows, diag, label=label)
    if args.debug and args.doc_type == "era":
        if diag.get("distinct_account_ids_count", 0) > 1 and diag.get("distinct_patient_name_hashes_count", 0) == 1:
            print(
                "[era_extract] WARNING: patient_name appears constant across multiple account_ids "
                "(possible context leak)"
            )

    print(f"[era_extract] wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
