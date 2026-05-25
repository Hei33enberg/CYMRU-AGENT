"""CYMRU Standalone Memory Bridge for hermes-agent.

Integrates hermes-agent with the shared Supabase database (rooffhgbxafyjcwmwpsy)
supporting pgvector semantic memory, god_persona user profiling, and god_skills.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from agent.memory_provider import MemoryProvider
from tools.registry import tool_error

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OpenAI Embedding Helper
# ---------------------------------------------------------------------------

def _get_embedding(text: str, api_key: str) -> Optional[List[float]]:
    """Generate 1536d embedding using text-embedding-3-small via OpenAI."""
    if not api_key:
        return None
    try:
        resp = httpx.post(
            "https://api.openai.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "input": text.strip(),
                "model": "text-embedding-3-small"
            },
            timeout=10.0
        )
        if resp.status_code != 200:
            logger.debug(f"OpenAI embedding error: {resp.status_code} - {resp.text}")
            return None
        return resp.json()["data"][0]["embedding"]
    except Exception as e:
        logger.debug(f"Failed to generate embedding: {e}")
        return None

# ---------------------------------------------------------------------------
# Tool Schemas
# ---------------------------------------------------------------------------

CYMRU_STORE_FACT_SCHEMA = {
    "name": "cymru_store_fact",
    "description": "Store a persistent fact about the user or project in long-term memory.",
    "parameters": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "The fact or preference to remember."},
            "source_type": {
                "type": "string",
                "enum": ["ptt_god", "session", "connector"],
                "default": "ptt_god",
                "description": "The category source of the memory."
            }
        },
        "required": ["content"],
    },
}

CYMRU_SEARCH_MEMORY_SCHEMA = {
    "name": "cymru_search_memory",
    "description": "Search long-term semantic memory for relevant user/project facts.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search term or semantic query."},
            "limit": {"type": "integer", "description": "Max results to return (default: 8)."},
        },
        "required": ["query"],
    },
}

CYMRU_UPDATE_PROFILE_SCHEMA = {
    "name": "cymru_update_profile",
    "description": "Update the God adaptive persona profile (known topics, communication style, etc.) for the user.",
    "parameters": {
        "type": "object",
        "properties": {
            "communication_style": {"type": "string", "description": "Evolving communication style (e.g. 'direct', 'thoughtful')."},
            "emotional_baseline": {"type": "string", "description": "Evolving emotional baseline of the user."},
            "iq_estimate": {"type": "integer", "description": "Evolving estimated IQ score or cognitive depth (e.g. 120)."},
            "add_known_topics": {"type": "array", "items": {"type": "string"}, "description": "List of new topics the user is interested in/knowledgeable about."},
        },
    },
}

# ---------------------------------------------------------------------------
# MemoryProvider Implementation
# ---------------------------------------------------------------------------

class CymruMemoryProvider(MemoryProvider):
    def __init__(self):
        self._supabase_url = ""
        self._supabase_key = ""
        self._openai_key = ""
        self._user_id = None
        self._session_id = ""
        self._client: Optional[httpx.Client] = None
        self._active = False
        self._write_enabled = True
        self._god_persona: Dict[str, Any] = {}
        self._skills: List[Dict[str, Any]] = []
        self._write_thread: Optional[threading.Thread] = None

    @property
    def name(self) -> str:
        return "cymru"

    def is_available(self) -> bool:
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        return bool(url and key)

    def get_config_schema(self):
        return [
            {"key": "supabase_url", "description": "Supabase Project URL", "secret": False, "required": True, "env_var": "SUPABASE_URL"},
            {"key": "supabase_key", "description": "Supabase Service Role Key", "secret": True, "required": True, "env_var": "SUPABASE_SERVICE_ROLE_KEY"},
            {"key": "openai_api_key", "description": "OpenAI API Key (for embeddings)", "secret": True, "required": True, "env_var": "OPENAI_API_KEY"},
        ]

    def initialize(self, session_id: str, **kwargs) -> None:
        self._session_id = session_id
        self._supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        self._supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        self._openai_key = os.environ.get("OPENAI_API_KEY", "")

        raw_user_id = kwargs.get("user_id")
        # Ensure user_id is a valid UUID or fallback to a dummy if testing
        if raw_user_id:
            self._user_id = raw_user_id
        else:
            self._user_id = None

        agent_context = kwargs.get("agent_context", "")
        self._write_enabled = agent_context not in {"cron", "flush", "subagent"}
        self._active = bool(self._supabase_url and self._supabase_key)

        if self._active:
            self._client = httpx.Client(
                headers={
                    "apikey": self._supabase_key,
                    "Authorization": f"Bearer {self._supabase_key}",
                    "Content-Type": "application/json"
                },
                timeout=10.0
            )
            # Load user persona and skills eagerly
            self._load_user_persona()
            self._load_active_skills()

    def _load_user_persona(self) -> None:
        """Fetch god_persona from members table."""
        if not self._active or not self._client or not self._user_id:
            return
        try:
            url = f"{self._supabase_url}/rest/v1/members?user_id=eq.{self._user_id}&select=god_persona,display_name"
            resp = self._client.get(url)
            if resp.status_code == 200:
                rows = resp.json()
                if rows:
                    raw_persona = rows[0].get("god_persona")
                    display_name = rows[0].get("display_name") or "User"
                    if isinstance(raw_persona, dict):
                        self._god_persona = raw_persona
                    else:
                        self._god_persona = {}
                    self._god_persona.setdefault("name", display_name)
                    self._god_persona.setdefault("known_topics", [])
                    self._god_persona.setdefault("iq_estimate", None)
                    self._god_persona.setdefault("communication_style", None)
                    self._god_persona.setdefault("emotional_baseline", None)
                    self._god_persona.setdefault("interaction_count", 0)
        except Exception as e:
            logger.debug(f"Failed to load user persona: {e}")

    def _load_active_skills(self) -> None:
        """Fetch active user-specific and global skills from god_skills table."""
        if not self._active or not self._client:
            return
        try:
            # Query global skills or user-specific skills
            filter_clause = "is_active=eq.true"
            if self._user_id:
                filter_clause += f"&or=(user_id.eq.{self._user_id},is_global.eq.true)"
            else:
                filter_clause += "&is_global=eq.true"

            url = f"{self._supabase_url}/rest/v1/god_skills?{filter_clause}&select=name,description,content,trigger_keywords"
            resp = self._client.get(url)
            if resp.status_code == 200:
                self._skills = resp.json() or []
        except Exception as e:
            logger.debug(f"Failed to load active skills: {e}")

    def system_prompt_block(self) -> str:
        if not self._active:
            return ""

        blocks = ["# CYMRU God OS Memory Bridge"]

        # 1. User Profile Bridge (god_persona)
        if self._god_persona:
            blocks.append("## User Adaptive Persona Profile (god_persona)")
            blocks.append(f"- **Name/Display**: {self._god_persona.get('name')}")
            if self._god_persona.get("communication_style"):
                blocks.append(f"- **Communication Style**: {self._god_persona.get('communication_style')}")
            if self._god_persona.get("emotional_baseline"):
                blocks.append(f"- **Emotional Baseline**: {self._god_persona.get('emotional_baseline')}")
            if self._god_persona.get("iq_estimate"):
                blocks.append(f"- **Cognitive Baseline (IQ Estimate)**: {self._god_persona.get('iq_estimate')}")
            topics = self._god_persona.get("known_topics", [])
            if topics:
                blocks.append(f"- **Known Topics of Interest**: {', '.join(topics)}")
            blocks.append(f"- **Conversations/Interactions**: {self._god_persona.get('interaction_count', 0)}")
            blocks.append("\nAdjust your tone, vocabulary, and depth based on this persona.")

        # 2. Skills Bridge (god_skills)
        if self._skills:
            blocks.append("## Dynamically Loaded God Skills")
            blocks.append("You have special skills/instruction blocks registered. When trigger keywords match or when relevant, follow their nested guidelines:")
            for s in self._skills:
                keywords = s.get("trigger_keywords") or []
                kw_str = f" (Keywords: {', '.join(keywords)})" if keywords else ""
                blocks.append(f"### Skill: {s.get('name')}{kw_str}")
                blocks.append(f"**Trigger condition**: {s.get('description')}")
                blocks.append(f"**Instructions**:\n{s.get('content')}\n")

        return "\n\n".join(blocks)

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        """Recall relevant semantic chunks from shaman_embeddings via hybrid search RPC."""
        if not self._active or not self._client or not query.strip():
            return ""

        # 1. Embed query
        emb = _get_embedding(query, self._openai_key)
        if not emb:
            return ""

        try:
            # 2. Call shaman_hybrid_search
            url = f"{self._supabase_url}/rest/v1/rpc/shaman_hybrid_search"
            payload = {
                "p_user_id": self._user_id,
                "p_query_embedding": emb,
                "p_query_text": query,
                "p_source_types": ["knowledge", "ptt_user", "ptt_god", "session", "connector"],
                "p_thread_id": None,
                "p_limit": 6,
                "p_min_similarity": 0.35,
                "p_rrf_k": 60
            }
            resp = self._client.post(url, json=payload)
            if resp.status_code == 200:
                results = resp.json() or []
                if not results:
                    return ""

                lines = []
                for r in results:
                    source = r.get("source_type", "memory")
                    similarity = r.get("similarity", 0.0)
                    content = r.get("content_text", "").strip()
                    if content:
                        lines.append(f"- [{source} / similarity: {similarity:.2f}] {content}")

                if lines:
                    return "## Relevant Memories & Shared Knowledge\n" + "\n".join(lines)
        except Exception as e:
            logger.debug(f"Prefetch hybrid search failed: {e}")

        return ""

    def sync_turn(self, user_content: str, assistant_content: str, *, session_id: str = "") -> None:
        """Increment interaction count automatically on each completed turn."""
        if not self._active or not self._client or not self._user_id or not self._write_enabled:
            return
        try:
            # Increment interaction count in god_persona
            self._god_persona["interaction_count"] = self._god_persona.get("interaction_count", 0) + 1
            url = f"{self._supabase_url}/rest/v1/members?user_id=eq.{self._user_id}"
            self._client.patch(url, json={"god_persona": self._god_persona})
        except Exception as e:
            logger.debug(f"Failed to increment interaction count: {e}")

    def on_memory_write(self, action: str, target: str, content: str) -> None:
        """Mirror the assistant memory writes to public.shaman_embeddings."""
        if not self._active or not self._client or not self._user_id or not self._write_enabled:
            return
        if action != "add" or not (content or "").strip():
            return

        def _run():
            try:
                emb = _get_embedding(content, self._openai_key)
                if not emb:
                    return
                url = f"{self._supabase_url}/rest/v1/shaman_embeddings"
                payload = {
                    "user_id": self._user_id,
                    "source_type": "ptt_god",
                    "content_text": content.strip(),
                    "embedding": emb,
                    "metadata": {
                        "source": "cymru_agent",
                        "write_target": target,
                        "session_id": self._session_id
                    }
                }
                # Insert memory record
                resp = self._client.post(url, json=payload)
                if resp.status_code not in {200, 201}:
                    logger.debug(f"Failed to insert memory: {resp.status_code} - {resp.text}")
            except Exception as e:
                logger.debug(f"Error in background memory write: {e}")

        # Start a thread to avoid blocking the agent turn loop
        self._write_thread = threading.Thread(target=_run, daemon=True)
        self._write_thread.start()

    def shutdown(self) -> None:
        if self._write_thread and self._write_thread.is_alive():
            self._write_thread.join(timeout=3.0)
        if self._client:
            self._client.close()

    # -- Tool implementations ------------------------------------------------

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [CYMRU_STORE_FACT_SCHEMA, CYMRU_SEARCH_MEMORY_SCHEMA, CYMRU_UPDATE_PROFILE_SCHEMA]

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        if not self._active or not self._client:
            return tool_error("Cymru memory bridge is not initialized/active")

        if tool_name == "cymru_store_fact":
            return self._tool_store_fact(args)
        elif tool_name == "cymru_search_memory":
            return self._tool_search_memory(args)
        elif tool_name == "cymru_update_profile":
            return self._tool_update_profile(args)
        return tool_error(f"Unknown tool: {tool_name}")

    def _tool_store_fact(self, args: Dict[str, Any]) -> str:
        content = args.get("content", "").strip()
        source_type = args.get("source_type", "ptt_god")
        if not content:
            return tool_error("content is required")

        try:
            emb = _get_embedding(content, self._openai_key)
            if not emb:
                return tool_error("Failed to generate embedding for the fact")

            url = f"{self._supabase_url}/rest/v1/shaman_embeddings"
            payload = {
                "user_id": self._user_id,
                "source_type": source_type,
                "content_text": content,
                "embedding": emb,
                "metadata": {
                    "source": "cymru_agent_tool",
                    "session_id": self._session_id
                }
            }
            resp = self._client.post(url, json=payload)
            if resp.status_code in {200, 201}:
                return json.dumps({"saved": True, "content": content})
            return tool_error(f"Failed to save fact: {resp.status_code} - {resp.text}")
        except Exception as e:
            return tool_error(str(e))

    def _tool_search_memory(self, args: Dict[str, Any]) -> str:
        query = args.get("query", "").strip()
        limit = args.get("limit", 8)
        if not query:
            return tool_error("query is required")

        try:
            emb = _get_embedding(query, self._openai_key)
            if not emb:
                return tool_error("Failed to generate embedding for the search query")

            url = f"{self._supabase_url}/rest/v1/rpc/shaman_hybrid_search"
            payload = {
                "p_user_id": self._user_id,
                "p_query_embedding": emb,
                "p_query_text": query,
                "p_source_types": ["knowledge", "ptt_user", "ptt_god", "session", "connector"],
                "p_thread_id": None,
                "p_limit": limit,
                "p_min_similarity": 0.35,
                "p_rrf_k": 60
            }
            resp = self._client.post(url, json=payload)
            if resp.status_code == 200:
                results = resp.json() or []
                formatted = [
                    {
                        "source": r.get("source_type"),
                        "similarity": r.get("similarity"),
                        "content": r.get("content_text")
                    } for r in results
                ]
                return json.dumps({"results": formatted, "count": len(formatted)})
            return tool_error(f"Search failed: {resp.status_code} - {resp.text}")
        except Exception as e:
            return tool_error(str(e))

    def _tool_update_profile(self, args: Dict[str, Any]) -> str:
        if not self._user_id:
            return tool_error("No active user ID resolved to update profile")

        try:
            if "communication_style" in args:
                self._god_persona["communication_style"] = args["communication_style"]
            if "emotional_baseline" in args:
                self._god_persona["emotional_baseline"] = args["emotional_baseline"]
            if "iq_estimate" in args:
                self._god_persona["iq_estimate"] = args["iq_estimate"]

            add_topics = args.get("add_known_topics") or []
            if add_topics:
                known_topics = set(self._god_persona.get("known_topics") or [])
                known_topics.update(add_topics)
                self._god_persona["known_topics"] = list(known_topics)

            url = f"{self._supabase_url}/rest/v1/members?user_id=eq.{self._user_id}"
            resp = self._client.patch(url, json={"god_persona": self._god_persona})
            if resp.status_code in {200, 204}:
                return json.dumps({"updated": True, "god_persona": self._god_persona})
            return tool_error(f"Failed to update profile: {resp.status_code} - {resp.text}")
        except Exception as e:
            return tool_error(str(e))

# ---------------------------------------------------------------------------
# Plugin Entry Point
# ---------------------------------------------------------------------------

def register(ctx) -> None:
    """Register the cymru memory provider with the plugin system."""
    provider = CymruMemoryProvider()
    ctx.register_memory_provider(provider)
