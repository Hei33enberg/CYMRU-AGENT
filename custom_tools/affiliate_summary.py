"""affiliate_summary — Show user how much God has earned them in subsidies.

S23, LINEAR-2058. "God saved you $12 this month" feature.
"""
from __future__ import annotations

import os
from typing import Optional

import httpx


def affiliate_summary(
    user_id: Optional[str] = None,
    since_days: int = 30,
) -> str:
    """Query Supabase events table for affiliate.routed events in the last N days.

    Use when user says "God, what have you saved me?" / "Bóg, ile mi oszczędziłeś?".

    Args:
        user_id: required to scope query.
        since_days: window (default 30).

    Returns:
        User-facing summary with total revenue + per-partner breakdown.
    """
    if not user_id:
        return "I need to know who you are first."

    supabase_url = os.getenv("SUPABASE_URL", "")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not supabase_url or not supabase_key:
        return "Affiliate ledger is not yet connected."

    # Query: sum of -cost_usd_micros for agent.affiliate.routed events
    try:
        url = f"{supabase_url.rstrip('/')}/rest/v1/events"
        params = {
            "select": "payload,cost_usd_micros,ts",
            "user_id": f"eq.{user_id}",
            "event_name": "eq.agent.affiliate.routed",
            "ts": f"gte.now() - interval '{since_days} days'",
        }
        resp = httpx.get(
            url,
            params=params,
            headers={
                "apikey": supabase_key,
                "Authorization": f"Bearer {supabase_key}",
            },
            timeout=10.0,
        )
        rows = resp.json() if resp.is_success else []
    except Exception as exc:
        return f"Could not read your ledger: {exc}"

    if not rows:
        return "No affiliate earnings yet. Use me for shopping and rides — I'll save you money."

    total_micros = sum(-int(r.get("cost_usd_micros", 0)) for r in rows)  # negate the negation
    total_usd = total_micros / 1_000_000.0

    by_partner: dict[str, float] = {}
    for r in rows:
        payload = r.get("payload") or {}
        partner = payload.get("partner_display", "Unknown")
        revenue = int(payload.get("affiliate_revenue_usd_micros", 0)) / 1_000_000.0
        by_partner[partner] = by_partner.get(partner, 0.0) + revenue

    lines = [f"In the last {since_days} days I earned you ${total_usd:.2f} in subsidies:"]
    for partner, amount in sorted(by_partner.items(), key=lambda x: -x[1]):
        lines.append(f"  • {partner}: ${amount:.2f}")
    lines.append("\nThat goes back into your 🔱 wallet.")
    return "\n".join(lines)
