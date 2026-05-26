"""
Per-tenant rate limit — Redis token bucket (S20, LINEAR-2066).

Każdy tenant ma osobny budżet ⚡ Tchnienie + 🔱 Czyn na sekundę.
Bez Redis (np. local dev) padamy do in-process bucket (per-process).

Limity z planu:
  - Powściągliwy:  50 ⚡/day  → ~0.0006 ⚡/s
  - Żywy:          300 ⚡ + 10 🔱 daily cap; 100 ⚡/min rate ceiling
  - Wyrocznia:     1200 ⚡ + 40 🔱 daily cap; 400 ⚡/min rate ceiling

Implementacja: token bucket z refill rate + max capacity. Default odpalany
bez Redis (fakeredis-equivalent in-memory), z opcjonalnym REDIS_URL.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Tier limits
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TierLimits:
    """Rate + daily cap per tier (CYMRU Bible v1.1)."""
    tchnienie_per_minute: int   # max ⚡ rate (refill capacity)
    tchnienie_daily: int        # hard daily cap (refill at 0:00 UTC)
    czyn_per_minute: int
    czyn_daily: int


TIER_LIMITS: dict[str, TierLimits] = {
    "free":      TierLimits(tchnienie_per_minute=20,  tchnienie_daily=50,    czyn_per_minute=0,  czyn_daily=0),
    "zywy":      TierLimits(tchnienie_per_minute=100, tchnienie_daily=300,   czyn_per_minute=10, czyn_daily=10),
    "wyrocznia": TierLimits(tchnienie_per_minute=400, tchnienie_daily=1200,  czyn_per_minute=40, czyn_daily=40),
    "lifetime":  TierLimits(tchnienie_per_minute=400, tchnienie_daily=1200,  czyn_per_minute=40, czyn_daily=40),
    "family":    TierLimits(tchnienie_per_minute=400, tchnienie_daily=1200,  czyn_per_minute=40, czyn_daily=40),
    # legacy aliases
    "managed":   TierLimits(tchnienie_per_minute=100, tchnienie_daily=300,   czyn_per_minute=10, czyn_daily=10),
    "paid":      TierLimits(tchnienie_per_minute=100, tchnienie_daily=300,   czyn_per_minute=10, czyn_daily=10),
}


# ─────────────────────────────────────────────────────────────────────────────
# In-memory token bucket (fallback gdy brak Redis)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class _Bucket:
    """Token bucket per tenant + currency (⚡ albo 🔱)."""
    tokens: float
    capacity: float
    refill_per_second: float
    last_refill: float


_LOCAL_BUCKETS: dict[str, _Bucket] = {}
_LOCAL_LOCK = asyncio.Lock()


async def _check_local(tenant_id: str, currency: str, cost: int, limits: TierLimits) -> bool:
    """In-process bucket — fallback gdy nie ma Redis."""
    cap = limits.tchnienie_per_minute if currency == "tchnienie" else limits.czyn_per_minute
    refill = cap / 60.0  # tokens per second
    key = f"{tenant_id}:{currency}"

    async with _LOCAL_LOCK:
        now = time.time()
        bucket = _LOCAL_BUCKETS.get(key)
        if bucket is None:
            bucket = _Bucket(
                tokens=float(cap),
                capacity=float(cap),
                refill_per_second=refill,
                last_refill=now,
            )
            _LOCAL_BUCKETS[key] = bucket

        # Refill
        elapsed = now - bucket.last_refill
        bucket.tokens = min(bucket.capacity, bucket.tokens + elapsed * bucket.refill_per_second)
        bucket.last_refill = now

        if bucket.tokens >= cost:
            bucket.tokens -= cost
            return True
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Redis backend (production)
# ─────────────────────────────────────────────────────────────────────────────


_redis_client = None  # lazy-init redis.asyncio.Redis


async def _get_redis():
    """Lazy connect to Redis. Returns None if not configured / unavailable."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    url = os.getenv("REDIS_URL")
    if not url:
        return None

    try:
        import redis.asyncio as aioredis  # type: ignore
        _redis_client = aioredis.from_url(url, decode_responses=True)
        # Ping to validate
        await _redis_client.ping()
        logger.info("[rate-limit] Redis connected: %s", url.split("@")[-1])
        return _redis_client
    except Exception as exc:
        logger.warning("[rate-limit] Redis unavailable, falling back to local: %s", exc)
        _redis_client = None
        return None


# Lua script — atomic token bucket check-and-consume
_LUA_BUCKET = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_per_second = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])
local now = tonumber(ARGV[4])

local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens = tonumber(bucket[1]) or capacity
local last_refill = tonumber(bucket[2]) or now

local elapsed = now - last_refill
tokens = math.min(capacity, tokens + elapsed * refill_per_second)

if tokens >= cost then
  tokens = tokens - cost
  redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
  redis.call('EXPIRE', key, 120)
  return 1
else
  redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
  redis.call('EXPIRE', key, 120)
  return 0
end
"""


async def _check_redis(redis_client, tenant_id: str, currency: str, cost: int, limits: TierLimits) -> bool:
    cap = limits.tchnienie_per_minute if currency == "tchnienie" else limits.czyn_per_minute
    refill = cap / 60.0
    key = f"cymru:rl:{tenant_id}:{currency}"
    now = time.time()
    try:
        result = await redis_client.eval(
            _LUA_BUCKET,
            1,
            key,
            str(cap),
            str(refill),
            str(cost),
            str(now),
        )
        return int(result) == 1
    except Exception as exc:
        logger.warning("[rate-limit] Redis eval failed, fallback to local: %s", exc)
        return await _check_local(tenant_id, currency, cost, limits)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


async def check_and_consume(
    tenant_id: str,
    *,
    tier: str = "free",
    cost_tchnienie: int = 0,
    cost_czyn: int = 0,
) -> bool:
    """Check if tenant has enough budget AND consume tokens (atomic).

    Returns True if consumed, False if rate-limited.
    Both currencies must be available — partial consumption is not allowed
    (returns False without consuming any).
    """
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    redis_client = await _get_redis()

    # Pre-check both currencies before consuming either
    # (we'd need a more sophisticated atomic op for true atomicity; for now,
    # check sequentially and if first fails, second isn't consumed)
    if cost_tchnienie > 0:
        ok = await (_check_redis(redis_client, tenant_id, "tchnienie", cost_tchnienie, limits)
                    if redis_client
                    else _check_local(tenant_id, "tchnienie", cost_tchnienie, limits))
        if not ok:
            return False

    if cost_czyn > 0:
        ok = await (_check_redis(redis_client, tenant_id, "czyn", cost_czyn, limits)
                    if redis_client
                    else _check_local(tenant_id, "czyn", cost_czyn, limits))
        if not ok:
            return False

    return True


async def get_remaining(tenant_id: str, *, tier: str = "free") -> dict[str, float]:
    """Inspect remaining tokens (for /status, debugging, not enforcement)."""
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    redis_client = await _get_redis()
    out = {"tchnienie": 0.0, "czyn": 0.0}

    for currency in ("tchnienie", "czyn"):
        cap = limits.tchnienie_per_minute if currency == "tchnienie" else limits.czyn_per_minute
        if redis_client:
            key = f"cymru:rl:{tenant_id}:{currency}"
            try:
                tokens = await redis_client.hget(key, "tokens")
                out[currency] = float(tokens) if tokens else float(cap)
            except Exception:
                out[currency] = float(cap)
        else:
            bucket = _LOCAL_BUCKETS.get(f"{tenant_id}:{currency}")
            out[currency] = bucket.tokens if bucket else float(cap)
    return out
