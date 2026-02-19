from __future__ import annotations

from copy import deepcopy
from typing import Any


_MONEY_KEYS = {
    # line-level / claim-level common keys
    "billed_amount",
    "allowed_amount",
    "paid_amount",
    "adjusted_amount",
    "adj_amount",
    "amount",
    # ledger-like keys (defense in depth)
    "total_billed",
    "total_allowed",
    "total_paid",
    "total_adjusted",
    "variance",
}


def _strip_money(obj: Any) -> Any:
    """
    Deterministic safety layer:
    - Recursively traverse dict/list payloads
    - Replace any monetary fields with None
    - Preserve non-financial structure for downstream deterministic parsing
    """
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if k in _MONEY_KEYS:
                out[k] = None
                continue
            # common nested patterns
            if k == "adjustments" and isinstance(v, list):
                # ensure any adjustment amounts are also nulled
                new_adjustments = []
                for adj in v:
                    if isinstance(adj, dict):
                        adj2 = dict(adj)
                        if "amount" in adj2:
                            adj2["amount"] = None
                        new_adjustments.append(_strip_money(adj2))
                    else:
                        new_adjustments.append(_strip_money(adj))
                out[k] = new_adjustments
                continue

            out[k] = _strip_money(v)
        return out
    if isinstance(obj, list):
        return [_strip_money(x) for x in obj]
    return obj


class ClaimNormalizer:
    """
    This service is explicitly NOT allowed to modify monetary values.
    It may be used to standardize shape/fields, but all currency values are nulled.

    NOTE:
    - Do not call external AI services here.
    - Deterministic systems must keep money parsing in deterministic parsers only.
    """

    def normalize(self, raw_json: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(raw_json, dict):
            raise ValueError("raw_json must be a dict")

        # Deepcopy first so caller’s object is never mutated.
        payload = deepcopy(raw_json)

        # Strip monetary fields everywhere.
        return _strip_money(payload)


def normalize_claims_from_azure(azure_json: dict[str, Any], document_type: str) -> list[dict[str, Any]]:
    """
    Backward-compatible helper for older call sites.
    It does NOT call Azure OpenAI.
    It returns a best-effort list wrapper around the provided structure,
    with all monetary fields stripped.
    """
    if not isinstance(azure_json, dict):
        raise ValueError("azure_json must be a dict")

    # Some upstreams might place claims under "claims"
    claims = azure_json.get("claims")
    if isinstance(claims, list):
        return [_strip_money(deepcopy(c)) for c in claims if isinstance(c, (dict, list))]

    # Otherwise: return a single-item list containing the sanitized payload
    return [_strip_money(deepcopy({"document_type": document_type, "payload": azure_json}))]
