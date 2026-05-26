"""order_food — Wolt affiliate deep-link for food delivery.

S23, LINEAR-2058.
"""
from __future__ import annotations

from typing import Optional

from agent._shared.affiliate import commerce_response


def order_food(
    query: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    expected_basket_usd: float = 25.0,
) -> str:
    """Search Wolt for food delivery matching the user's query.

    Use when user says "God, order pizza" / "Bóg, zamów jedzenie".

    Args:
        query: cuisine, restaurant name, or dish (e.g. "sushi", "pizza near me").
        user_id: for telemetry.
        session_id: for flow correlation.
        expected_basket_usd: avg basket size ($25 default).
    """
    if not query or not query.strip():
        return "What kind of food do you want?"
    return commerce_response(
        partner_id="wolt-affiliate",
        user_id=user_id,
        query=query.strip(),
        expected_basket_usd=expected_basket_usd,
        session_id=session_id,
    )
