"""4. get_calendar_events — Google Calendar via user_connectors (Composio)"""
from __future__ import annotations
import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
_sb = lambda: create_client(os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""))


def get_calendar_events(user_id: str, days_ahead: int = 3) -> str:
    """
    Get upcoming Google Calendar events for the user.
    Use when user asks about their schedule, meetings, or 'co mam dzisiaj'.

    Args:
        user_id: UUID of the user.
        days_ahead: How many days ahead to look (default 3).

    Returns:
        Formatted list of upcoming events or status message.
    """
    try:
        sb = _sb()
        response = (
            sb.table("user_connectors")
            .select("service_name, access_token, metadata")
            .eq("user_id", user_id)
            .eq("service_name", "google_calendar")
            .single()
            .execute()
        )
        if not response.data:
            return "Nie masz podpiętego Kalendarza Google. Podepnij przez USB → Google Calendar."
        # Token present — actual calendar call would go here via Google API
        # For now return stub until COMPOSIO_API_KEY is configured
        return f"Kalendarz podpięty. Aby pobrać wydarzenia, skonfiguruj COMPOSIO_API_KEY w .env. (days_ahead={days_ahead})"
    except Exception as e:
        return f"Błąd kalendarza: {e}"
