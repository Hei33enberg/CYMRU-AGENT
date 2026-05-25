"""13. get_health_data — health data stub (future wearable integration)"""
from __future__ import annotations


def get_health_data(user_id: str, metric: str = "all") -> str:
    """
    Get health data for the user. Currently a stub pending wearable integration.
    Use when user asks about their health, sleep, steps, heart rate.

    Args:
        user_id: UUID of the user.
        metric: Specific metric to query ('sleep', 'steps', 'heart_rate', 'all').

    Returns:
        Health data summary or integration prompt.
    """
    # Stub — full implementation pending wearable/Apple Health integration
    # See: docs/products/wearables/ROADMAP.md
    return (
        f"📊 Dane zdrowotne ({metric}): integracja z wearables w toku.\n"
        f"Docelowo: Apple Watch, Garmin, Google Fit via USB Connector Hub.\n"
        f"Dodaj swoje urządzenie przez USB → Health, gdy będzie dostępne."
    )
