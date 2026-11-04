"""Payable-or-not checks for a supplier bill against its purchase order.

The decision is code, not a model. The same idea as the receipt agent:
a blocking mismatch means INVESTIGATE, and a person decides before money moves.
"""

from __future__ import annotations


def review_bill(*, ordered_qty: float, billed_qty: float, ordered_net: float, billed_net: float) -> tuple[str, list[str]]:
    issues: list[str] = []
    if billed_qty - ordered_qty > 1e-6:
        issues.append("QTY_OVER")
    if billed_net - ordered_net > 0.05:
        issues.append("OVER_PO_VALUE")
    if issues:
        return "INVESTIGATE", issues
    return "APPROVE", []
