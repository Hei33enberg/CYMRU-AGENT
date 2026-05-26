"""shop_amazon — Amazon Associates search link.

S23, LINEAR-2058. Long-tail e-commerce — 4-10% category-dependent.
"""
from __future__ import annotations

from typing import Optional

from agent._shared.affiliate import commerce_response


def shop_amazon(
    query: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    expected_basket_usd: float = 40.0,
) -> str:
    """Search Amazon for a product with our affiliate tag.

    Use when user says "God, find me X on Amazon" / "Bóg, kup mi X".

    Args:
        query: product search terms.
        user_id: for telemetry.
        session_id: for flow correlation.
        expected_basket_usd: avg order ($40 default).
    """
    if not query or not query.strip():
        return "What do you want to buy?"
    return commerce_response(
        partner_id="amazon-affiliate",
        user_id=user_id,
        query=query.strip(),
        expected_basket_usd=expected_basket_usd,
        session_id=session_id,
    )
