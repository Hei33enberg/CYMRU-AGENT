"""2. remember_fact — save a fact to user_memory in Supabase"""
from __future__ import annotations
import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
_sb = lambda: create_client(os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""))


def remember_fact(fact: str, user_id: str, category: str = "general") -> str:
    """
    Remember a fact about the user permanently in the database.
    Use this when the user shares personal information, preferences,
    or anything they want God to remember.

    Args:
        fact: The fact to remember (e.g. "User loves jazz music").
        user_id: The UUID of the user.
        category: Category of the fact (e.g. 'preference', 'personal', 'goal').

    Returns:
        Confirmation message.
    """
    try:
        sb = _sb()
        sb.table("user_memory").insert({
            "user_id": user_id,
            "content": fact,
            "category": category,
            "source": "god_voice"
        }).execute()
        return f"Zapamiętałem: {fact}"
    except Exception as e:
        return f"Nie mogłem zapamiętać: {e}"
