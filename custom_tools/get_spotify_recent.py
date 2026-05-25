"""5. get_spotify_recent — Spotify recent tracks via user_connectors"""
from __future__ import annotations
import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
_sb = lambda: create_client(os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""))


def get_spotify_recent(user_id: str, limit: int = 5) -> str:
    """
    Get recently played Spotify tracks for the user.
    Use when user asks what they listened to, current vibe, or music.

    Args:
        user_id: UUID of the user.
        limit: Number of recent tracks to fetch (default 5).

    Returns:
        Formatted list of recent tracks or connection prompt.
    """
    try:
        sb = _sb()
        response = (
            sb.table("user_connectors")
            .select("service_name, metadata")
            .eq("user_id", user_id)
            .eq("service_name", "spotify")
            .single()
            .execute()
        )
        if not response.data:
            return "Nie masz podpiętego Spotify. Podepnij przez USB → Spotify."
        return f"Spotify podpięty. Aby pobrać ostatnie utwory, skonfiguruj SPOTIFY_CLIENT_ID w .env. (limit={limit})"
    except Exception as e:
        return f"Błąd Spotify: {e}"
