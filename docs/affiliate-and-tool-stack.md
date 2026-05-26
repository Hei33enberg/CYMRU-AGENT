# Own tool stack + affiliate routing

> CYMRU Bible v1.1, S23, [LINEAR-2058](https://linear.app/ip-ra/issue/LINEAR-2058).
> Goal: kill Composio dependency for high-value commerce actions. Capture affiliate revenue. Subsidize user's 🔱 wallet via partner commissions.

## Why

Per CYMRU Bible v1.1 §2.6 (revenue streams):
- Hot commerce intents (Uber/Wolt/Booking/Amazon/OpenTable) generate **$0.50–2/active user/month** in affiliate.
- Composio takes a cut + adds $0.099/call latency. Our own deep-link tools cost ~$0.001/call and pocket 100% of commission.
- "God saved you $12 this month" = visible value, retention driver.

## Architecture

```
User: "God, get me an Uber to Mokotów"
   │
   ▼
intent_class → 'commerce_transport'
   │
   ▼
provider_routing.lookup('uber') → priority=200, own_tool='tools.commerce.uber'
   │
   ▼
custom_tools.order_uber(destination="Mokotów", user_id=…)
   │
   ▼
agent._shared.affiliate.commerce_response()
   ├─ build_affiliate_link("uber-affiliate", "Mokotów")
   │     → https://m.uber.com/?...&client_id={AFFILIATE_UBER_ID}
   ├─ emit_affiliate_event() → events.insert agent.affiliate.routed
   │     (cost_usd_micros: -600_000  // -$0.60 = inflow)
   ▼
God speaks: "Open this link to confirm: <affiliate-link>.
              I'll get a small commission — funds your next ⚡."
```

## Files

| Path | Purpose |
|---|---|
| `agent/_shared/affiliate.py` | Partner catalog + URL building + tracking |
| `custom_tools/order_uber.py` | Uber deep-link |
| `custom_tools/order_food.py` | Wolt search |
| `custom_tools/book_hotel.py` | Booking.com search |
| `custom_tools/shop_amazon.py` | Amazon Associates search |
| `custom_tools/reserve_restaurant.py` | OpenTable search |
| `custom_tools/affiliate_summary.py` | "God saved you $X this month" feature |

## Partner catalog

5 launch partners (S23):

| partner_id | display | commission | env var (affiliate ID) |
|---|---|---|---|
| `uber-affiliate` | Uber | 4% | `AFFILIATE_UBER_ID` |
| `wolt-affiliate` | Wolt | 5% | `AFFILIATE_WOLT_ID` |
| `booking-affiliate` | Booking.com | 6% | `AFFILIATE_BOOKING_AID` |
| `amazon-affiliate` | Amazon | 5% (cat-dependent) | `AFFILIATE_AMAZON_TAG` |
| `opentable-affiliate` | OpenTable | flat $1.50/cover | `AFFILIATE_OPENTABLE_RID` |

Set these in cymru-agent `.env` (per box) and in Supabase secrets (if EF will ever wrap links server-side).

## Telemetry

Every commerce tool call → `agent.affiliate.routed` event with:
- `partner` + `partner_display`
- `expected_basket_usd`
- `affiliate_revenue_usd_micros` (negative cost = our inflow)
- `query` (truncated to 200 chars, no PII)
- `user_id` + `session_id` for attribution

CFO dashboard rollup query:
```sql
SELECT
  payload->>'partner_display' AS partner,
  count(*) AS routed_calls,
  sum(-cost_usd_micros) / 1e6 AS gross_revenue_usd
FROM public.events
WHERE event_name = 'agent.affiliate.routed'
  AND ts > now() - interval '30 days'
GROUP BY partner
ORDER BY gross_revenue_usd DESC;
```

## Cost vs Composio

Per-action cost comparison:
- **Composio**: ~$0.099/action (Composio Cloud plan ~$99/mo per 1000 actions)
- **Own deep-link tools**: ~$0.001/action (just LLM tokens to generate URL + log event)
- **Net savings at 10K MAU × 5 commerce actions/mo**: ($0.099 - $0.001) × 50K = **$4900/mo**

Plus we capture ~$0.50–2/active user affiliate revenue that Composio kept.

## What's NOT implemented (S23 vs future)

- ❌ Direct API integration (Uber Trips API, Booking Demand API) — requires per-partner B2B contracts, weeks of legal. Deep-links are 80% of value for 5% of effort.
- ❌ In-app webview wrapping (the affiliate link opens externally; future S24+ could embed)
- ❌ Order confirmation callbacks — affiliate revenue is **estimated** at routing time, not at conversion (real revenue lands ~30 days later from each partner's portal). Reconciliation pipeline = S26 B2B intelligence dashboard.
- ❌ Provider_routing table lookup (the dispatcher is conceptual — `shaman-ai-chat` will route to these tools in S24 once the call-with-tools surface is updated).

## How shaman-ai-chat picks the right tool (S24 work)

```ts
// pseudo-code, S24 implementation
const intent = await classifyIntent(message);
const provider = await supabase
  .from('provider_routing')
  .select('own_tool_path, priority')
  .contains('intent_classes', [intent])
  .eq('active', true)
  .order('priority', { ascending: false })
  .limit(1)
  .single();

if (provider?.own_tool_path) {
  const result = await invokeAgentTool(provider.own_tool_path, { query, user_id });
  // ...
}
```

S23 lays the foundation — S24 wires it up.
