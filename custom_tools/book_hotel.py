"""book_hotel — Booking.com affiliate link for hotel/stay search.

S23, LINEAR-2058. Highest-margin commerce tool (~6% on $100-500 basket).
"""
from __future__ import annotations

from typing import Optional

from agent._shared.affiliate import commerce_response


def book_hotel(
    destination: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    expected_total_usd: float = 200.0,
) -> str:
    """Open Booking.com search for a destination.

    Use when user says "God, find me a hotel in X" / "Bóg, zarezerwuj nocleg w X".

    Args:
        destination: city / area / hotel name.
        user_id: for telemetry.
        session_id: for flow correlation.
        expected_total_usd: avg stay total ($200 default).
    """
    if not destination or not destination.strip():
        return "Where are you going?"
    return commerce_response(
        partner_id="booking-affiliate",
        user_id=user_id,
        query=destination.strip(),
        expected_basket_usd=expected_total_usd,
        session_id=session_id,
    )
