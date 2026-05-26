"""
CYMRU multi-tenant runtime support — S20, LINEAR-2066.

Pozwala jednej instancji cymru-agent obsłużyć N userów na jednym boxie
(~100 userów / box w docelu) z pełną izolacją:

- per-tenant home dir (`~/.cymru/tenants/{tenant_id}/`) z osobnym state.db,
  credentials, workspace — wykorzystuje istniejący mechanizm
  `hermes_constants.set_hermes_home_override` (ContextVar)
- per-tenant rate limit (Redis token bucket, see `_shared.rate_limit`)
- per-tenant credential pool (encrypted-at-rest, klucz wyprowadzany
  z voice biometric stamp + server-side master key)

Filozofia: każda request od user X dostaje TenantContext('user_x') który
jest async context manager. Wszystkie tools w środku widzą `~/.cymru/tenants/user_x/`
jako `get_hermes_home()`. Po wyjściu z `async with` override jest resetowany.

UWAGA: ContextVar jest task-local — bezpieczne dla asyncio współbieżnych
requestów. Dla wątków (threading) wciąż działa per-task (każdy worker thread
ma własny ContextVar).
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import os
import secrets
import shutil
import sqlite3
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Optional

from hermes_constants import (
    get_hermes_home,
    get_hermes_home_override,
    set_hermes_home_override,
    reset_hermes_home_override,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

MULTI_TENANT_ROOT = Path(os.getenv("CYMRU_TENANTS_ROOT", str(Path.home() / ".cymru" / "tenants")))
"""Root directory dla wszystkich tenantów na tym boxie."""

TENANT_IDLE_TIMEOUT_SECONDS = int(os.getenv("CYMRU_TENANT_IDLE_TIMEOUT", "3600"))
"""Po jakim czasie bezczynności tenant może być eksmitowany (default 1h)."""

MAX_TENANTS_PER_BOX = int(os.getenv("CYMRU_MAX_TENANTS_PER_BOX", "100"))
"""Hard cap — nie pozwalamy claim'ować ponad limit (zwracamy 503)."""


# ─────────────────────────────────────────────────────────────────────────────
# In-memory registry (per-box state). Real claims są też w Redis (LINEAR-2067).
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class TenantSlot:
    """Aktywny tenant na tym boxie."""
    tenant_id: str
    user_id: str
    home_dir: Path
    claimed_at: float = field(default_factory=time.time)
    last_seen_at: float = field(default_factory=time.time)
    request_count: int = 0


# Process-local registry. Multi-process scaling robi to Redis (LINEAR-2067).
_REGISTRY: dict[str, TenantSlot] = {}
_REGISTRY_LOCK = asyncio.Lock()


# ─────────────────────────────────────────────────────────────────────────────
# TenantManager API
# ─────────────────────────────────────────────────────────────────────────────


class TenantManagerError(Exception):
    """Base class dla problemów z multi-tenant runtime."""


class BoxFullError(TenantManagerError):
    """Raised gdy box osiągnął MAX_TENANTS_PER_BOX."""


def _tenant_home(tenant_id: str) -> Path:
    """Resolve absolute path do per-tenant home dir."""
    if not tenant_id or any(c in tenant_id for c in ("/", "\\", "..", "\0")):
        raise ValueError(f"Invalid tenant_id: {tenant_id!r}")
    return MULTI_TENANT_ROOT / tenant_id


def _ensure_tenant_home(tenant_id: str) -> Path:
    """Create per-tenant dir tree (idempotent)."""
    home = _tenant_home(tenant_id)
    home.mkdir(parents=True, exist_ok=True)
    # Standard subdirs (mirror typical HERMES_HOME layout)
    (home / "credentials").mkdir(exist_ok=True)
    (home / "workspace").mkdir(exist_ok=True)
    (home / "logs").mkdir(exist_ok=True)
    return home


async def claim_tenant(tenant_id: str, user_id: str) -> TenantSlot:
    """Claim a tenant slot. Idempotent — returning existing slot if already claimed.

    Raises ``BoxFullError`` if MAX_TENANTS_PER_BOX exceeded by NEW slot.
    """
    async with _REGISTRY_LOCK:
        if tenant_id in _REGISTRY:
            slot = _REGISTRY[tenant_id]
            slot.last_seen_at = time.time()
            return slot

        if len(_REGISTRY) >= MAX_TENANTS_PER_BOX:
            # Try to evict idle tenants first
            evicted = _evict_idle_locked()
            if not evicted:
                raise BoxFullError(
                    f"Box at capacity ({MAX_TENANTS_PER_BOX} tenants); none idle to evict"
                )

        home = _ensure_tenant_home(tenant_id)
        slot = TenantSlot(tenant_id=tenant_id, user_id=user_id, home_dir=home)
        _REGISTRY[tenant_id] = slot
        logger.info(
            "[multi-tenant] Claimed tenant=%s user=%s home=%s (active=%d/%d)",
            tenant_id,
            user_id[:8],
            home,
            len(_REGISTRY),
            MAX_TENANTS_PER_BOX,
        )
        return slot


async def release_tenant(tenant_id: str, *, wipe_workspace: bool = False) -> bool:
    """Release a tenant slot. Returns True if released, False if not found.

    With ``wipe_workspace=True`` removes the per-tenant workspace dir
    (NIE credentials — te chronimy do migrate kontekstu na inny box).
    """
    async with _REGISTRY_LOCK:
        slot = _REGISTRY.pop(tenant_id, None)
        if slot is None:
            return False
        if wipe_workspace:
            try:
                shutil.rmtree(slot.home_dir / "workspace", ignore_errors=True)
            except OSError as exc:
                logger.warning("[multi-tenant] workspace wipe failed: %s", exc)
        logger.info(
            "[multi-tenant] Released tenant=%s (active=%d/%d)",
            tenant_id,
            len(_REGISTRY),
            MAX_TENANTS_PER_BOX,
        )
        return True


def _evict_idle_locked() -> int:
    """Eviction policy: kill tenants idle longer than TENANT_IDLE_TIMEOUT_SECONDS.

    Caller must hold ``_REGISTRY_LOCK``.
    """
    now = time.time()
    to_evict = [
        tid for tid, slot in _REGISTRY.items()
        if now - slot.last_seen_at > TENANT_IDLE_TIMEOUT_SECONDS
    ]
    for tid in to_evict:
        _REGISTRY.pop(tid, None)
        logger.info("[multi-tenant] Evicted idle tenant=%s", tid)
    return len(to_evict)


def get_active_tenants() -> list[TenantSlot]:
    """Snapshot of active tenants (for /admin/health or heartbeat)."""
    return list(_REGISTRY.values())


def get_tenant_count() -> int:
    return len(_REGISTRY)


# ─────────────────────────────────────────────────────────────────────────────
# Context manager — wraps any async block w per-tenant HERMES_HOME
# ─────────────────────────────────────────────────────────────────────────────


@asynccontextmanager
async def tenant_context(tenant_id: str, user_id: str) -> AsyncIterator[TenantSlot]:
    """Async context manager pushing per-tenant HERMES_HOME for the block.

    Example::

        async with tenant_context("user_alice", user_id_uuid) as slot:
            # Inside: get_hermes_home() returns ~/.cymru/tenants/user_alice
            session = await load_session(...)
            await session.append_message(...)
            # Outside: previous HERMES_HOME restored
    """
    slot = await claim_tenant(tenant_id, user_id)
    token = set_hermes_home_override(slot.home_dir)
    try:
        slot.request_count += 1
        slot.last_seen_at = time.time()
        yield slot
    finally:
        reset_hermes_home_override(token)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — voice-biometric derived tenant_id (collision-resistant)
# ─────────────────────────────────────────────────────────────────────────────


def derive_tenant_id(user_id: str, voice_print_hash: Optional[str] = None) -> str:
    """Deterministic tenant_id from user_id (+ optional voice biometric).

    Format: ``t_<first 12 chars of sha256(user_id [+ voice_print_hash])>``
    """
    import hashlib

    seed = user_id
    if voice_print_hash:
        seed = f"{user_id}:{voice_print_hash}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
    return f"t_{digest}"


# ─────────────────────────────────────────────────────────────────────────────
# Smoke test (run via `python -m agent.multi_tenant`)
# ─────────────────────────────────────────────────────────────────────────────


async def _smoke() -> None:
    """Quick smoke test — claim 3 tenants, verify isolation, release."""
    async with tenant_context("smoke_a", "user-a-uuid") as a:
        home_a = get_hermes_home()
        print(f"[A] hermes_home = {home_a}")
        assert home_a == a.home_dir

        async with tenant_context("smoke_b", "user-b-uuid") as b:
            home_b = get_hermes_home()
            print(f"[B] hermes_home = {home_b}")
            assert home_b == b.home_dir
            assert home_a != home_b

    print(f"Active tenants AFTER nested context: {get_tenant_count()}")
    # Note: tenants stay claimed until explicit release_tenant()
    await release_tenant("smoke_a", wipe_workspace=True)
    await release_tenant("smoke_b", wipe_workspace=True)
    print(f"Active tenants AFTER release: {get_tenant_count()}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(_smoke())
