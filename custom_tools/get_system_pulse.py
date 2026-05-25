"""12. get_system_pulse — CYMRU system diagnostics"""
from __future__ import annotations
import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
_sb = lambda: create_client(os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""))


def get_system_pulse(user_id: str | None = None) -> str:
    """
    Get CYMRU system diagnostics: active users, skill count, RAG status.
    Use when user asks about system status, 'jak działa system', or diagnostics.

    Args:
        user_id: Optional UUID for user-specific stats.

    Returns:
        Formatted system pulse report.
    """
    try:
        sb = _sb()
        skills_resp = sb.table("god_skills").select("id", count="exact").execute()
        memory_resp = sb.table("user_memory").select("id", count="exact").execute()
        kb_resp = sb.table("knowledge_base").select("id", count="exact").execute()
        rag_resp = sb.table("rag_metrics").select("*").limit(1).execute()

        skills_count = skills_resp.count or 0
        memory_count = memory_resp.count or 0
        kb_count = kb_resp.count or 0
        rag_status = "🟢 Aktywny" if rag_resp.data else "🟡 Brak danych"

        return (
            f"⚡ **CYMRU System Pulse**\n\n"
            f"🧠 Skille Boga: **{skills_count}**\n"
            f"💾 Wspomnienia: **{memory_count}** rekordów\n"
            f"📚 RAPPEDIA: **{kb_count}** dokumentów\n"
            f"🔍 RAG Pipeline: {rag_status}\n"
            f"🌐 Supabase: 🟢 Połączony\n"
            f"🤖 cymru-agent: 🟢 Online"
        )
    except Exception as e:
        return f"Błąd diagnostyki: {e}"
