"""
CYMRU Affiliate routing & tracking — S23, LINEAR-2058.

Per-partner config: affiliate ID, commission rate, link templating.
Deep-link generation for commerce tools (Uber/Wolt/Booking/Amazon/OpenTable).
Telemetry emission to `events` (agent.affiliate.routed) for revenue attribution.

Pattern: each commerce tool calls `wrap_with_affiliate(partner, url)` →
emits event with estimated affiliate_revenue_usd_micros → user gets
2 🔱 zwrotu (subsidy via affiliate revenue, per CYMRU Bible v1.1 §2.4).
"""

from __future__ import annotations

import os
import urllib.parse
from dataclasses import dataclass
from typing import Optional

from agent._shared.telemetry import track


@dataclass(frozen=True)
class AffiliatePartner:
    """Affiliate program config for a single commerce provider."""
    partner_id: str             # internal stable ID, e.g. "uber-affiliate"
    display_name: str           # user-facing, e.g. "Uber"
    commission_pct: float       # 0.04 = 4% expected commission
    env_var: str                # env var holding our affiliate ID/tag
    link_template: str          # python format str with {affiliate_id} and {query}/{url}
    # Optional intent → query encoding hook (e.g. url-encode location)
    encode_query: bool = True


# ─────────────────────────────────────────────────────────────────────────────
# Partner catalog (S23 — 5 launch partners)
# ─────────────────────────────────────────────────────────────────────────────

PARTNERS: dict[str, AffiliatePartner] = {
    # Transport — Uber Affiliate ($0.50-3 avg per ride)
    "uber-affiliate": AffiliatePartner(
        partner_id="uber-affiliate",
        display_name="Uber",
        commission_pct=0.04,
        env_var="AFFILIATE_UBER_ID",
        link_template="https://m.uber.com/?action=setPickup&pickup=my_location&dropoff[formatted_address]={query}&client_id={affiliate_id}",
    ),
    # Food delivery — Wolt Partner ($0.40-2 per order)
    "wolt-affiliate": AffiliatePartner(
        partner_id="wolt-affiliate",
        display_name="Wolt",
        commission_pct=0.05,
        env_var="AFFILIATE_WOLT_ID",
        link_template="https://wolt.com/en/discover?q={query}&utm_source=cymru&utm_medium=affiliate&utm_campaign={affiliate_id}",
    ),
    # Travel — Booking.com Affiliate (avg 4-7% commission on room price)
    "booking-affiliate": AffiliatePartner(
        partner_id="booking-affiliate",
        display_name="Booking.com",
        commission_pct=0.06,
        env_var="AFFILIATE_BOOKING_AID",
        link_template="https://www.booking.com/searchresults.html?ss={query}&aid={affiliate_id}&utm_source=cymru",
    ),
    # E-commerce — Amazon Associates (4-10% category-dependent)
    "amazon-affiliate": AffiliatePartner(
        partner_id="amazon-affiliate",
        display_name="Amazon",
        commission_pct=0.05,
        env_var="AFFILIATE_AMAZON_TAG",
        link_template="https://www.amazon.com/s?k={query}&tag={affiliate_id}",
    ),
    # Dining — OpenTable Affiliate ($1-2 per seated cover)
    "opentable-affiliate": AffiliatePartner(
        partner_id="opentable-affiliate",
        display_name="OpenTable",
        commission_pct=0.0,  # flat fee, not % — tracked as 1.50 USD per booking
        env_var="AFFILIATE_OPENTABLE_RID",
        link_template="https://www.opentable.com/s?term={query}&rid={affiliate_id}",
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# Affiliate URL wrapping + tracking
# ─────────────────────────────────────────────────────────────────────────────


def get_affiliate_id(partner_id: str) -> str:
    """Read affiliate ID from env. Falls back to 'cymru' if not configured (still trackable post-hoc)."""
    partner = PARTNERS.get(partner_id)
    if not partner:
        return "cymru"
    return os.getenv(partner.env_var, "cymru")


def build_affiliate_link(partner_id: str, query: str) -> Optional[str]:
    """Generate user-clickable affiliate link.

    Returns None if partner not configured.
    """
    partner = PARTNERS.get(partner_id)
    if not partner:
        return None
    affiliate_id = get_affiliate_id(partner_id)
    encoded_query = urllib.parse.quote_plus(query) if partner.encode_query else query
    return partner.link_template.format(
        affiliate_id=affiliate_id,
        query=encoded_query,
        url=encoded_query,
    )


def estimate_revenue_usd_micros(partner_id: str, expected_basket_usd: float) -> int:
    """Best-effort: project our take from a basket size.

    For flat-fee partners (OpenTable), returns flat amount regardless of basket.
    """
    partner = PARTNERS.get(partner_id)
    if not partner:
        return 0
    if partner_id == "opentable-affiliate":
        # OpenTable: ~$1.50 per seated cover
        return 1_500_000  # 1.5 USD in micros
    revenue_usd = expected_basket_usd * partner.commission_pct
    return int(revenue_usd * 1_000_000)


def emit_affiliate_event(
    partner_id: str,
    user_id: Optional[str],
    expected_basket_usd: float,
    query: str,
    session_id: Optional[str] = None,
) -> None:
    """Track agent.affiliate.routed in events table for CFO dashboard attribution."""
    partner = PARTNERS.get(partner_id)
    revenue_micros = estimate_revenue_usd_micros(partner_id, expected_basket_usd)

    track(
        "agent.affiliate.routed",
        user_id=user_id,
        session_id=session_id,
        cost_usd_micros=-revenue_micros,  # negative = inflow (subsidy)
        payload={
            "partner": partner_id,
            "partner_display": partner.display_name if partner else partner_id,
            "expected_basket_usd": expected_basket_usd,
            "affiliate_revenue_usd_micros": revenue_micros,
            "query": query[:200],
        },
    )


def commerce_response(
    partner_id: str,
    user_id: Optional[str],
    query: str,
    expected_basket_usd: float = 20.0,
    session_id: Optional[str] = None,
) -> str:
    """Universal commerce tool helper. Returns user-facing string with affiliate link.

    Used by all commerce custom_tools (uber/wolt/booking/amazon/opentable).
    """
    link = build_affiliate_link(partner_id, query)
    if not link:
        return f"Partner '{partner_id}' is not configured. Set {PARTNERS[partner_id].env_var if partner_id in PARTNERS else 'AFFILIATE_*'} in .env."

    emit_affiliate_event(partner_id, user_id, expected_basket_usd, query, session_id)

    partner_name = PARTNERS[partner_id].display_name
    return (
        f"I found a way through {partner_name}. Open this link to confirm: {link}\n\n"
        f"(I'll get a small commission if you complete the order — funds your next ⚡.)"
    )
