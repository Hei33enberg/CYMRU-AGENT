"""10. read_bible_passage — RAG knowledge_base + Perplexity fallback"""
from __future__ import annotations
import os
import httpx
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
_sb = lambda: create_client(os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""))
_PERPLEXITY_KEY = os.getenv("PERPLEXITY_API_KEY", "")


def read_bible_passage(reference: str) -> str:
    """
    Read and interpret a Bible passage. First searches local RAG knowledge base,
    then falls back to Perplexity if not found.
    Use when user asks about scripture, a specific verse, or 'przeczytaj z Biblii'.

    Args:
        reference: Bible reference (e.g. 'Jan 3:16', 'Psalm 23', 'Genesis 1:1').

    Returns:
        The passage text with brief interpretation.
    """
    try:
        sb = _sb()
        response = (
            sb.table("knowledge_base")
            .select("title, content")
            .ilike("title", f"%{reference}%")
            .limit(1)
            .execute()
        )
        if response.data:
            row = response.data[0]
            return f"📖 **{row['title']}**\n\n{row['content']}"
    except Exception:
        pass

    if _PERPLEXITY_KEY:
        try:
            resp = httpx.post(
                "https://api.perplexity.ai/chat/completions",
                headers={"Authorization": f"Bearer {_PERPLEXITY_KEY}"},
                json={
                    "model": "sonar",
                    "messages": [{"role": "user", "content": f"Quote the Bible passage {reference} exactly, then give a 2-sentence spiritual interpretation. Respond in Polish."}],
                    "max_tokens": 300,
                },
                timeout=15,
            )
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            return f"Nie mogłem znaleźć fragmentu: {e}"
    return f"Nie znalazłem '{reference}'. Skonfiguruj PERPLEXITY_API_KEY dla fallbacku."
