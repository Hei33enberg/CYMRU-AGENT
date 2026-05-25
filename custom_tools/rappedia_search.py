"""1. rappedia_search — RAG search in knowledge_base (72k+ docs)"""
from __future__ import annotations
import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
_sb = lambda: create_client(os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""))


def rappedia_search(query: str, limit: int = 5) -> str:
    """
    Search the RAPPEDIA knowledge base (72k+ documents) for information.
    Use this when the user asks about minerals, elements, esoteric topics,
    or any factual question that may be in the knowledge base.

    Args:
        query: The search query string.
        limit: Maximum number of results to return (default 5).

    Returns:
        Formatted string with search results from the knowledge base.
    """
    try:
        sb = _sb()
        response = (
            sb.table("knowledge_base")
            .select("title, content, source_url")
            .ilike("content", f"%{query}%")
            .limit(limit)
            .execute()
        )
        if not response.data:
            return f"Nie znalazłem nic o '{query}' w RAPPEDII. Spróbuję odpowiedzieć z własnej wiedzy."
        results = []
        for i, row in enumerate(response.data, 1):
            results.append(f"[{i}] **{row.get('title', 'Bez tytułu')}**\n{row.get('content', '')[:500]}...")
        return "\n\n".join(results)
    except Exception as e:
        return f"RAPPEDIA tymczasowo niedostępna: {e}"
