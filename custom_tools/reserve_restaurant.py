"""reserve_restaurant — OpenTable affiliate booking link.

S23, LINEAR-2058. Flat fee (~$1.50 per seated cover, no basket scaling).
"""
from __future__ import annotations

from typing import Optional

from agent._shared.affiliate import commerce_response


def reserve_restaurant(
    query: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> str:
    """Open OpenTable to reserve a table.

    Use when user says "God, book a table at X" / "Bóg, zarezerwuj restaurację X".

    Args:
        query: restaurant name, cuisine, or area (e.g. "Italian SoHo NYC").
        user_id: for telemetry.
        session_id: for flow correlation.
    """
    if not query or not query.strip():
        return "Which restaurant or cuisine?"
    return commerce_response(
        partner_id="opentable-affiliate",
        user_id=user_id,
        query=query.strip(),
        expected_basket_usd=0.0,  # flat fee, not basket-based
        session_id=session_id,
    )
