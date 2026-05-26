"""order_uber — Open an Uber affiliate deep-link for a destination.

S23, LINEAR-2058. Affiliate revenue funds user's 🔱 Czyn wallet.
"""
from __future__ import annotations

from typing import Optional

from agent._shared.affiliate import commerce_response


def order_uber(
    destination: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    expected_fare_usd: float = 15.0,
) -> str:
    """Open the Uber app with a pre-filled destination for the user to confirm.

    Use when user says "God, get me an Uber to X" / "Bóg, zamów Ubera do X".

    Args:
        destination: drop-off location (address or place name).
        user_id: for telemetry attribution.
        session_id: for flow correlation.
        expected_fare_usd: rough basket estimate ($15 default, used for affiliate revenue projection).

    Returns:
        User-facing message containing the affiliate deep-link.
    """
    if not destination or not destination.strip():
        return "Tell me where you want to go."
    return commerce_response(
        partner_id="uber-affiliate",
        user_id=user_id,
        query=destination.strip(),
        expected_basket_usd=expected_fare_usd,
        session_id=session_id,
    )
