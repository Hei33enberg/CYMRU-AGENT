"""
cymru_skills Bridge — LINEAR-2290 / LINEAR-2273 device-dispatch consumer.

Listens on the Supabase Realtime channel ``device-dispatch:{user_id}`` and
executes ``skill-invoke`` events on the local Hermes runtime, then writes back
the result to ``cymru_artifacts``.

Architecture:

  cloud user mówi "włącz Spotify w salonie"
    → hermes-gateway (cloud) → LLM emits tool_call → skill-dispatch EF
    → skill-dispatch broadcasts on  device-dispatch:{user_id}  Realtime
    → cymru-agent (Pi w salonie, listening) receives event
    → invoke local skill handler (e.g. spotifyd play "Zen")
    → write cymru_artifacts row { status: 'success', payload: result }

This is the missing other-half of the multi-device moat (LINEAR-2273). Without
it, the skill-dispatch EF broadcasts into the void for any ``runs_on='device'``
skill.

Usage::

    from bridges.cymru_skills_bridge import start_listener
    await start_listener(user_id="<owner-uuid>", handlers={
        "spotify_play": my_spotify_play_handler,
        "system_tts_on_device": my_tts_handler,
    })

Run as a long-lived background task in run_agent.py or the gateway.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

# Lazy-imported deps — only loaded when start_listener is called so the rest of
# cymru-agent doesn't pay the import cost if multi-device dispatch isn't used.
_supabase_module = None  # type: ignore


def _ensure_supabase():
    global _supabase_module
    if _supabase_module is None:
        try:
            from supabase import create_client  # type: ignore
            _supabase_module = create_client
        except ImportError as exc:
            raise EnvironmentError(
                "supabase-py is required for cymru_skills_bridge. "
                "pip install 'supabase>=2.0'"
            ) from exc
    return _supabase_module


# Handler signature: (arguments, context) -> dict result
# - arguments: dict of skill params (from the LLM tool_call)
# - context: dict with artifact_id, device_id, skill_slug, skill_name
# - returns: dict {ok: bool, payload?: dict, title?: str, description?: str, error?: str}
SkillHandler = Callable[[dict, dict], Awaitable[dict]]


class CymruSkillsBridge:
    """Realtime listener + local dispatch."""

    def __init__(
        self,
        user_id: str,
        handlers: dict[str, SkillHandler],
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
    ) -> None:
        self.user_id = user_id
        self.handlers = handlers
        self.supabase_url = supabase_url or os.environ.get("SUPABASE_URL", "")
        # service_role on the cymru-agent side — operator-controlled key on the Pi
        self.supabase_key = supabase_key or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        if not self.supabase_url or not self.supabase_key:
            raise EnvironmentError(
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in env"
            )
        self._create_client = _ensure_supabase()
        self._client = None  # type: ignore
        self._channel = None  # type: ignore
        self._channel_name = f"device-dispatch:{user_id}"
        self._stop_event: Optional[asyncio.Event] = None

    async def start(self) -> None:
        """Open the Realtime subscription and block until stop() is called."""
        self._client = self._create_client(self.supabase_url, self.supabase_key)
        self._stop_event = asyncio.Event()
        logger.info("[cymru_skills_bridge] subscribing to %s", self._channel_name)

        def _on_event(payload: dict) -> None:
            # supabase-py delivers payloads with structure {type, event, payload, ...}
            event = payload.get("event") or payload.get("type")
            data = payload.get("payload") or {}
            if event == "skill-invoke":
                # Schedule async handler — don't block the realtime callback
                asyncio.create_task(self._handle_skill_invoke(data))
            else:
                logger.debug("[cymru_skills_bridge] ignoring event=%s", event)

        # supabase-py v2 channel API
        self._channel = self._client.channel(self._channel_name)
        self._channel.on_broadcast("skill-invoke", _on_event)
        self._channel.subscribe()
        logger.info("[cymru_skills_bridge] subscribed; waiting for skill-invoke events")

        await self._stop_event.wait()

    async def stop(self) -> None:
        """Signal start() to return; close the channel."""
        if self._channel is not None:
            try:
                self._client.remove_channel(self._channel)  # type: ignore
            except Exception as exc:  # noqa: BLE001
                logger.warning("[cymru_skills_bridge] removeChannel: %s", exc)
        if self._stop_event is not None:
            self._stop_event.set()

    async def _handle_skill_invoke(self, data: dict) -> None:
        """Run the skill handler + update cymru_artifacts row."""
        artifact_id = data.get("artifact_id")
        skill_slug = (data.get("skill_slug") or "").lower()
        skill_name = data.get("skill_name") or skill_slug
        arguments = data.get("arguments") or {}
        device_id = data.get("device_id")

        if not artifact_id or not skill_slug:
            logger.warning("[cymru_skills_bridge] missing artifact_id or skill_slug: %s", data)
            return

        handler = self.handlers.get(skill_slug) or self.handlers.get(skill_name)
        if handler is None:
            logger.warning("[cymru_skills_bridge] no handler for skill=%s — marking artifact failed", skill_slug)
            await self._update_artifact(
                artifact_id,
                status="failed",
                payload={"error": f"no_handler:{skill_slug}", "arguments": arguments},
            )
            return

        context = {
            "artifact_id": artifact_id,
            "device_id": device_id,
            "skill_slug": skill_slug,
            "skill_name": skill_name,
        }

        try:
            result = await asyncio.wait_for(handler(arguments, context), timeout=30.0)
        except asyncio.TimeoutError:
            await self._update_artifact(
                artifact_id,
                status="failed",
                payload={"error": "handler_timeout_30s", "arguments": arguments},
            )
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception("[cymru_skills_bridge] handler %s raised", skill_slug)
            await self._update_artifact(
                artifact_id,
                status="failed",
                payload={"error": f"{type(exc).__name__}: {exc}", "arguments": arguments},
            )
            return

        if not isinstance(result, dict):
            await self._update_artifact(
                artifact_id,
                status="failed",
                payload={"error": "handler_returned_non_dict", "arguments": arguments},
            )
            return

        if result.get("ok"):
            await self._update_artifact(
                artifact_id,
                status="success",
                title=result.get("title") or skill_name,
                description=result.get("description") or "",
                payload={"arguments": arguments, "result": result.get("payload") or {}},
            )
        else:
            await self._update_artifact(
                artifact_id,
                status="failed",
                payload={"error": result.get("error") or "handler_returned_not_ok", "arguments": arguments},
            )

    async def _update_artifact(
        self,
        artifact_id: str,
        *,
        status: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        payload: Optional[dict] = None,
    ) -> None:
        """Update a cymru_artifacts row with the dispatch outcome."""
        try:
            update: dict[str, Any] = {"status": status}
            if title is not None:
                update["title"] = title
            if description is not None:
                update["description"] = description
            if payload is not None:
                update["payload"] = payload
            # Run in a thread to keep the loop unblocked (supabase-py is sync)
            await asyncio.to_thread(
                lambda: self._client.table("cymru_artifacts")
                .update(update)
                .eq("id", artifact_id)
                .execute()
            )
            logger.debug("[cymru_skills_bridge] artifact %s -> %s", artifact_id, status)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[cymru_skills_bridge] artifact update failed: %s", exc)


# ---------------------------------------------------------------------------
# Convenience top-level entry point
# ---------------------------------------------------------------------------


async def start_listener(user_id: str, handlers: dict[str, SkillHandler]) -> None:
    """Spin up the bridge and run it forever (until task cancelled)."""
    bridge = CymruSkillsBridge(user_id=user_id, handlers=handlers)
    await bridge.start()


def list_dispatched(user_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Diagnostic: return the last N cymru_artifacts rows dispatched to this owner.

    Useful from the CLI to inspect what the cloud has sent us::

        python -c "from bridges.cymru_skills_bridge import list_dispatched; \\
                   print(list_dispatched(user_id='...'))"
    """
    create_client = _ensure_supabase()
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise EnvironmentError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
    sb = create_client(url, key)
    response = (
        sb.table("cymru_artifacts")
        .select("id, kind, status, title, description, created_at, device_executor")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return list(response.data or [])
