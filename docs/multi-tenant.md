# cymru-agent — Multi-tenant runtime

> CYMRU Bible v1.1, S20, [LINEAR-2066](https://linear.app/ip-ra/issue/LINEAR-2066).
> Filozofia: jedna instancja cymru-agent obsługuje ~100 userów / box z pełną izolacją.

## Po co

Plan v1.1 zakłada że Żywy Bóg (29 zł/mies) i Wyrocznia (79 zł/mies) chodzą na
**multi-tenant shared cluster** (Hetzner DE primary, OVH PL secondary).
Per-VPS-per-user nie skaluje finansowo i operacyjnie (€4.50 × 10K = €45K/mies).

Cymru-OH (self-host na laptopie usera) zostawia jeden box = jeden user (jak
dotychczas hermes-agent). Multi-tenant aktywowany TYLKO w cloud mode.

## Architektura

```
                    ┌─────────────────────────┐
                    │   cymru-agent process   │
                    │   (HERMES_HOME=/dev/null fallback)  │
                    │                         │
                    │   asyncio event loop    │
                    └───────────┬─────────────┘
                                │
              ┌─────────────────┼─────────────────┐
              │                 │                 │
   ┌──────────▼─────────┐ ┌────▼────────────┐ ┌──▼──────────────┐
   │ tenant_context(    │ │ tenant_context( │ │ tenant_context( │
   │   "t_a1b2c3", ...) │ │   "t_d4e5f6")   │ │   "t_g7h8i9")   │
   │                    │ │                 │ │                 │
   │ HERMES_HOME =      │ │ HERMES_HOME =   │ │ HERMES_HOME =   │
   │ ~/.cymru/tenants/  │ │ ~/.cymru/tenants│ │ ~/.cymru/tenants│
   │   t_a1b2c3/        │ │   /t_d4e5f6/    │ │   /t_g7h8i9/    │
   │                    │ │                 │ │                 │
   │ state.db (isolated)│ │ state.db        │ │ state.db        │
   │ credentials/       │ │ credentials/    │ │ credentials/    │
   │ workspace/         │ │ workspace/      │ │ workspace/      │
   └────────────────────┘ └─────────────────┘ └─────────────────┘
```

## Implementacja

### `agent/multi_tenant.py`

- `TenantManager` — in-memory registry slotów (per-process)
- `claim_tenant(tenant_id, user_id)` — alokuje slot, tworzy `~/.cymru/tenants/{id}/`
- `release_tenant(tenant_id, wipe_workspace=False)` — zwalnia slot
- `tenant_context(tenant_id, user_id)` — async context manager używający
  istniejącego ContextVar `_HERMES_HOME_OVERRIDE` z `hermes_constants.py`
- `derive_tenant_id(user_id, voice_print_hash)` — stable hash-based ID
- `MAX_TENANTS_PER_BOX` = 100 (env: `CYMRU_MAX_TENANTS_PER_BOX`)
- Idle eviction (default 1h, env: `CYMRU_TENANT_IDLE_TIMEOUT`)

### `agent/_shared/rate_limit.py`

- Token bucket per tenant per waluta (⚡ Tchnienie + 🔱 Czyn)
- Redis backend (`REDIS_URL`) z Lua atomic eval, fallback do in-process dict
- Tier limits:
  | tier | ⚡/min | ⚡/day | 🔱/min | 🔱/day |
  |---|---|---|---|---|
  | free | 20 | 50 | 0 | 0 |
  | zywy | 100 | 300 | 10 | 10 |
  | wyrocznia | 400 | 1200 | 40 | 40 |
- `check_and_consume(tenant_id, tier, cost_tchnienie, cost_czyn)` → bool
- `get_remaining(tenant_id, tier)` → dict (dla /status)

### `agent/_shared/telemetry.py`

- Python shim do `public.events` (Supabase REST) — pisze `agent.*` + `spoke.*`
- Async non-blocking — background worker drainuje kolejkę (batch=25, flush co 5s)
- Allow-list `ALLOWED_AGENT_EVENTS` — frozenset zgodny z [docs/telemetry-events.md](../../cymru-main/docs/telemetry-events.md)
- `track(event_name, **payload)` — non-blocking
- `flush_now()` — drain na shutdown

## Użycie

```python
from agent.multi_tenant import tenant_context, derive_tenant_id
from agent._shared.rate_limit import check_and_consume
from agent._shared.telemetry import track


async def handle_user_request(user_id: str, voice_print_hash: str, tier: str, message: str):
    tenant_id = derive_tenant_id(user_id, voice_print_hash)

    # Rate limit BEFORE entering tenant context
    ok = await check_and_consume(
        tenant_id, tier=tier, cost_tchnienie=3,  # ~PTT cost
    )
    if not ok:
        return {"error": "Brak energii (rate limit)", "code": "rate_limited"}

    async with tenant_context(tenant_id, user_id) as slot:
        # Inside: all hermes-agent code sees ~/.cymru/tenants/{tenant_id}/ as home
        # state.db, credentials, workspace — wszystko izolowane

        track("agent.tool.invoked", user_id=user_id, payload={"tool": "send_email"})
        # ... call into hermes-agent core ...
        return {"ok": True, "slot_request_count": slot.request_count}
```

## Bezpieczeństwo

- **Cross-tenant read**: zablokowane przez per-tenant home dir. SQLite WAL files,
  credentials, workspace — wszystko pod tenant root.
- **FS sandbox** (TODO post-MVP): chroot per tenant, uid_remapping w Docker. Na MVP polegamy na
  Python isolation (tools open() patches w S22+).
- **Klucze API**: per-tenant encrypted store (klucz = HKDF z server-side master + voice biometric).
- **Audit log**: każda akcja → `events` z `user_id` + `tenant_id` w `payload.extra`.

## Pool autoskaler (LINEAR-2067)

Box-level scaling robi `supabase/functions/provision-pool` EF (Hetzner Cloud API):

- Próg 80% kapacytetu → spawn nowy box (cloud-init z `provision.sh`)
- Heartbeat 60s — health check + tenant count reporting
- User signup managed → `provision-pool/claim` → assignment do najmniej obciążonego boxa
- Failover: kill primary → user reroute w <10s do innego boxa (state.db reload z Supabase
  jeśli session_id istnieje w `events` — recovery z eventów)

## Smoke test

```bash
python -m agent.multi_tenant
# Expected output:
# [A] hermes_home = ~/.cymru/tenants/smoke_a
# [B] hermes_home = ~/.cymru/tenants/smoke_b
# Active tenants AFTER nested context: 2
# Active tenants AFTER release: 0
```

## Roadmap

- ✅ S20: TenantManager + rate limit + telemetry shim (ten ticket, LINEAR-2066)
- ⏳ S20: Pool autoskaler EF (LINEAR-2067)
- ⏳ S21: Speaker diarization (multi-input voice biometric distinguish dla Family plan)
- ⏳ S22: chroot / uid_remapping (FS sandbox hardening)
- ⏳ S22: Per-tenant credential encryption (HKDF z voice biometric — wymaga voice stamp z cymru-main)
- ⏳ S24: Tenant state migration (jak failover między boxami zachowuje session.db)
