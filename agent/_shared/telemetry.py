"""
CYMRU Telemetry shim dla cymru-agent (S20, LINEAR-2074).

Pisze do `public.events` (Supabase) zachowując konwencję `surface.action.outcome`
zgodną z cymru-main `src/lib/telemetry/events-allowlist.ts`.

Async, non-blocking — pojedyncze track() nie czeka na HTTP response.
W tle leci background flush worker który batchuje insert'y.

Used by tools, conversation loop, cron, bridges.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Allow-list — mirror src/lib/telemetry/events-allowlist.ts (agent.* prefix)
# ─────────────────────────────────────────────────────────────────────────────

ALLOWED_AGENT_EVENTS: frozenset[str] = frozenset({
    # agent.* (server-side actions)
    "agent.tool.invoked",
    "agent.tool.success",
    "agent.tool.failed",
    "agent.affiliate.routed",
    "agent.skill.invoked",
    "agent.skill.created",
    "agent.cron.tick",
    "agent.proactive.message_sent",
    # spoke.* — Hub-Spoke endpoint events
    "spoke.connected",
    "spoke.disconnected",
    "spoke.audio.captured",
    "spoke.audio.played",
})


def is_allowed_event(event_name: str) -> bool:
    """Validate event_name against allowlist."""
    return event_name in ALLOWED_AGENT_EVENTS


# ─────────────────────────────────────────────────────────────────────────────
# Event payload
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class TelemetryEvent:
    """Mirror of public.events row schema."""
    event_name: str
    surface: str = "agent"
    source: str = "cymru-agent"
    user_id: Optional[str] = None
    device_id: Optional[str] = None
    session_id: Optional[str] = None
    flow_id: Optional[str] = None
    intent: Optional[str] = None
    archetype: Optional[str] = None
    skill_id: Optional[str] = None
    model: Optional[str] = None
    latency_ms: Optional[int] = None
    cost_credits_tchnienie: int = 0
    cost_credits_czyn: int = 0
    cost_usd_micros: int = 0
    pii_redacted: bool = False
    payload: dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Background flush worker
# ─────────────────────────────────────────────────────────────────────────────


_QUEUE: asyncio.Queue[TelemetryEvent] = asyncio.Queue(maxsize=10_000)
_WORKER_TASK: Optional[asyncio.Task] = None
_BATCH_SIZE = 25
_FLUSH_INTERVAL_S = 5.0


def _supabase_url() -> Optional[str]:
    return os.getenv("SUPABASE_URL")


def _supabase_key() -> Optional[str]:
    return os.getenv("SUPABASE_SERVICE_ROLE_KEY")


async def _flush_batch(events: list[TelemetryEvent]) -> None:
    """POST batch to Supabase REST API."""
    url = _supabase_url()
    key = _supabase_key()
    if not url or not key:
        logger.debug("[telemetry] Supabase not configured, dropping %d events", len(events))
        return

    rows = [asdict(ev) for ev in events]
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{url.rstrip('/')}/rest/v1/events",
                json=rows,
                headers={
                    "apikey": key,
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
            )
            if resp.status_code >= 400:
                logger.warning(
                    "[telemetry] flush failed status=%d body=%s",
                    resp.status_code,
                    resp.text[:200],
                )
    except Exception as exc:
        logger.warning("[telemetry] flush exception: %s", exc)


async def _worker() -> None:
    """Background flush worker — drains queue, batches inserts."""
    buf: list[TelemetryEvent] = []
    last_flush = time.time()
    while True:
        try:
            timeout = max(0.1, _FLUSH_INTERVAL_S - (time.time() - last_flush))
            try:
                ev = await asyncio.wait_for(_QUEUE.get(), timeout=timeout)
                buf.append(ev)
            except asyncio.TimeoutError:
                pass

            now = time.time()
            should_flush = (
                len(buf) >= _BATCH_SIZE
                or (buf and now - last_flush >= _FLUSH_INTERVAL_S)
            )
            if should_flush:
                await _flush_batch(buf)
                buf = []
                last_flush = now
        except asyncio.CancelledError:
            if buf:
                await _flush_batch(buf)
            raise
        except Exception as exc:
            logger.error("[telemetry] worker error: %s", exc)
            await asyncio.sleep(1.0)


def _ensure_worker() -> None:
    """Lazy-start the worker on first track() call."""
    global _WORKER_TASK
    if _WORKER_TASK is None or _WORKER_TASK.done():
        try:
            loop = asyncio.get_running_loop()
            _WORKER_TASK = loop.create_task(_worker(), name="cymru-telemetry-flush")
        except RuntimeError:
            # No event loop — caller is sync; defer until async context
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


def track(
    event_name: str,
    *,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    flow_id: Optional[str] = None,
    intent: Optional[str] = None,
    skill_id: Optional[str] = None,
    model: Optional[str] = None,
    latency_ms: Optional[int] = None,
    cost_credits_tchnienie: int = 0,
    cost_credits_czyn: int = 0,
    cost_usd_micros: int = 0,
    pii_redacted: bool = False,
    payload: Optional[dict[str, Any]] = None,
) -> None:
    """Track a telemetry event (non-blocking).

    Example::

        track(
            "agent.tool.invoked",
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            payload={"tool_name": "send_email", "args_hash": h},
        )
    """
    if not is_allowed_event(event_name):
        logger.warning(
            "[telemetry] event_name '%s' NOT in allowlist — drop. "
            "Update agent/_shared/telemetry.py ALLOWED_AGENT_EVENTS and docs/telemetry-events.md.",
            event_name,
        )
        return

    ev = TelemetryEvent(
        event_name=event_name,
        user_id=user_id,
        session_id=session_id,
        flow_id=flow_id,
        intent=intent,
        skill_id=skill_id,
        model=model,
        latency_ms=latency_ms,
        cost_credits_tchnienie=cost_credits_tchnienie,
        cost_credits_czyn=cost_credits_czyn,
        cost_usd_micros=cost_usd_micros,
        pii_redacted=pii_redacted,
        payload=payload or {},
    )

    _ensure_worker()
    try:
        _QUEUE.put_nowait(ev)
    except asyncio.QueueFull:
        logger.warning("[telemetry] queue full, dropping event=%s", event_name)


async def flush_now() -> None:
    """Force-drain remaining events (call on shutdown)."""
    remaining: list[TelemetryEvent] = []
    while not _QUEUE.empty():
        try:
            remaining.append(_QUEUE.get_nowait())
        except asyncio.QueueEmpty:
            break
    if remaining:
        await _flush_batch(remaining)
