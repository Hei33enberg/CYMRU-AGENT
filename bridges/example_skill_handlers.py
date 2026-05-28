"""Example skill handlers wired into the cymru_skills_bridge.

These are minimal reference implementations matching the 10 starter skills
seeded in ``cymru_skills`` table (migration 20260528100000). Operators replace
or extend them per device — a Pi in the salon might wire ``spotify_play`` to
``spotifyd``, while a Pi in the kitchen might leave it unimplemented.

Wire it in your entry point::

    from bridges.cymru_skills_bridge import start_listener
    from bridges.example_skill_handlers import HANDLERS

    asyncio.create_task(start_listener(user_id=OWNER_ID, handlers=HANDLERS))
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
from typing import Any

logger = logging.getLogger(__name__)


async def spotify_play(arguments: dict, context: dict) -> dict:
    """Play music on the local device. Wire to ``spotifyd`` / ``mpd`` / etc.

    Reference impl: best-effort ``playerctl`` (Linux MPRIS). Real install would
    replace this with the user's preferred player.
    """
    query = str(arguments.get("query") or "")
    if not query:
        return {"ok": False, "error": "empty_query"}
    try:
        # Naive impl: just unpause whatever's loaded. Real impl would search
        # via spotify-cli or pass the URI to spotifyd.
        await asyncio.to_thread(
            subprocess.run,
            ["playerctl", "play"],
            check=False,
            capture_output=True,
            timeout=5,
        )
        return {
            "ok": True,
            "title": f"Spotify: {query}",
            "description": "Played via local MPRIS",
            "payload": {"query": query, "player": "playerctl"},
        }
    except FileNotFoundError:
        return {"ok": False, "error": "playerctl_not_installed"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


async def system_tts_on_device(arguments: dict, context: dict) -> dict:
    """Speak a message on this device via local TTS.

    Reference impl: ``espeak``. Real install would route to the cymru-agent
    Coqui XTTS endpoint for the cloned-voice path.
    """
    text = str(arguments.get("text") or "").strip()
    if not text:
        return {"ok": False, "error": "empty_text"}
    try:
        await asyncio.to_thread(
            subprocess.run,
            ["espeak", text[:500]],
            check=False,
            capture_output=True,
            timeout=15,
        )
        return {
            "ok": True,
            "title": "Powiedziałem na urządzeniu",
            "description": text[:120],
            "payload": {"text": text, "engine": "espeak"},
        }
    except FileNotFoundError:
        return {"ok": False, "error": "espeak_not_installed"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


async def shell_exec(arguments: dict, context: dict) -> dict:
    """Run a shell command. Admin-only on the cloud side (tier_required=cymru_oh).

    Returns stdout (truncated 500 chars). Stderr / non-zero exit → ok=False.
    """
    command = str(arguments.get("command") or "").strip()
    if not command:
        return {"ok": False, "error": "empty_command"}
    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            command,
            shell=True,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        if proc.returncode != 0:
            return {
                "ok": False,
                "error": f"exit_{proc.returncode}",
                "payload": {"stderr": (proc.stderr or "")[:500]},
            }
        return {
            "ok": True,
            "title": f"$ {command[:60]}",
            "description": (proc.stdout or "").strip()[:120],
            "payload": {"stdout": (proc.stdout or "")[:500]},
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout_20s"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


# Map skill slug → handler. Add/remove based on the device's capabilities.
HANDLERS: dict[str, Any] = {
    "spotify-play": spotify_play,
    "spotify_play": spotify_play,  # alias for the OpenAI function name
    "system-tts-on-device": system_tts_on_device,
    "system_tts_on_device": system_tts_on_device,
    "shell-exec": shell_exec,
    "shell_exec": shell_exec,
}
