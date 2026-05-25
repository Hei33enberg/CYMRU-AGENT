"""
Supabase Skills Bridge — LINEAR-1830 [F2.4]

Bridges the cymru-agent Hermes fork to the `god_skills` table in Supabase.
Replaces the flat skills/ directory loader for skills that live in the DB.

Provides:
  - search_skills(query, user_id)         — keyword search in god_skills
  - create_skill(name, desc, content, ...) — insert a new skill
  - get_skills_for_intent(intent)         — filter by intent tags
  - track_invocation(skill_id)            — increment invocation_count
  - canary_check(skill_id, user_id)       — A/B canary gate
"""

from __future__ import annotations

import os
import logging
from typing import Any

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()
logger = logging.getLogger(__name__)

_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
_TABLE = "god_skills"


def _client() -> Client:
    """Return an authenticated Supabase client (service role)."""
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        raise EnvironmentError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env"
        )
    return create_client(_SUPABASE_URL, _SUPABASE_KEY)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def search_skills(query: str, user_id: str | None = None) -> list[dict[str, Any]]:
    """
    Keyword + quality-score search in god_skills.

    Args:
        query:   Free-text search term matched against name/description/content.
        user_id: Optional — limits results to skills visible to this user
                 (respects canary_user_ids or is_public flag).

    Returns:
        List of matching skill rows sorted by quality_score DESC.
    """
    sb = _client()
    qb = (
        sb.table(_TABLE)
        .select("*")
        .ilike("name", f"%{query}%")
        .order("quality_score", desc=True)
        .limit(20)
    )
    if user_id:
        # Skills that are public OR have the user in canary_user_ids
        qb = qb.or_(f"is_public.eq.true,canary_user_ids.cs.{{{user_id}}}")

    response = qb.execute()
    logger.debug("search_skills(%r) → %d rows", query, len(response.data))
    return response.data


def create_skill(
    name: str,
    description: str,
    content: str,
    trigger_keywords: list[str] | None = None,
    quality_score: float = 0.5,
    is_public: bool = False,
    user_id: str | None = None,
) -> dict[str, Any]:
    """
    Insert a new skill into god_skills.

    Args:
        name:              Unique skill identifier.
        description:       Human-readable description shown in picker.
        content:           Full skill body (markdown / code / prompt).
        trigger_keywords:  List of keywords that auto-trigger this skill.
        quality_score:     Initial quality score 0.0–1.0 (default 0.5).
        is_public:         If True, visible to all users.
        user_id:           Owner user_id (can be None for system skills).

    Returns:
        The inserted row dict.
    """
    sb = _client()
    payload: dict[str, Any] = {
        "name": name,
        "description": description,
        "content": content,
        "trigger_keywords": trigger_keywords or [],
        "quality_score": quality_score,
        "is_public": is_public,
        "invocation_count": 0,
        "canary_user_ids": [],
    }
    if user_id:
        payload["user_id"] = user_id

    response = sb.table(_TABLE).insert(payload).execute()
    logger.info("create_skill(%r) → id=%s", name, response.data[0].get("id"))
    return response.data[0]


def get_skills_for_intent(intent: str) -> list[dict[str, Any]]:
    """
    Return skills whose trigger_keywords contain the given intent string.

    Args:
        intent: Intent tag, e.g. "summarize", "translate", "shaman_query".

    Returns:
        Matching skill rows ordered by quality_score DESC.
    """
    sb = _client()
    response = (
        sb.table(_TABLE)
        .select("*")
        .contains("trigger_keywords", [intent])
        .order("quality_score", desc=True)
        .execute()
    )
    logger.debug("get_skills_for_intent(%r) → %d rows", intent, len(response.data))
    return response.data


def track_invocation(skill_id: str) -> None:
    """
    Atomically increment invocation_count for skill_id via RPC.

    Args:
        skill_id: UUID of the skill row.
    """
    sb = _client()
    try:
        sb.rpc("increment_skill_invocation", {"skill_id": skill_id}).execute()
        logger.debug("track_invocation(%s) OK", skill_id)
    except Exception as exc:  # noqa: BLE001
        # Non-fatal — invocation tracking must never break the agent loop.
        logger.warning("track_invocation(%s) failed: %s", skill_id, exc)


def canary_check(skill_id: str, user_id: str) -> bool:
    """
    Return True if user_id is in the canary group for skill_id.

    The canary column `canary_user_ids` is a Postgres UUID array.
    A skill with an empty array is considered GA (everyone passes).

    Args:
        skill_id: UUID of the skill.
        user_id:  UUID of the requesting user.

    Returns:
        True if the user should receive this skill version.
    """
    sb = _client()
    response = (
        sb.table(_TABLE)
        .select("canary_user_ids")
        .eq("id", skill_id)
        .single()
        .execute()
    )
    if not response.data:
        return False
    canary_ids: list[str] = response.data.get("canary_user_ids") or []
    # Empty array means GA — everyone passes
    if not canary_ids:
        return True
    return user_id in canary_ids
