"""8. get_astro_chart — ephemeris / astro chart data via esoteric_mappings"""
from __future__ import annotations
import os
from datetime import date
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
_sb = lambda: create_client(os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""))


def get_astro_chart(user_id: str) -> str:
    """
    Get the user's astrological chart data from their birth data.
    Use when user asks about their chart, planets, signs, or 'mój horoskop'.

    Args:
        user_id: UUID of the user.

    Returns:
        Summary of user's astrological chart.
    """
    try:
        sb = _sb()
        response = (
            sb.table("user_birth_data")
            .select("sun_sign, moon_sign, rising_sign, venus_sign, mars_sign, birth_date, birth_place")
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        if not response.data:
            return "Nie mam Twoich danych urodzeniowych. Podaj datę, godzinę i miejsce urodzenia."
        d = response.data
        today = date.today()
        lines = [
            f"🌟 **Horoskop natywny** (data: {d.get('birth_date', '?')}, miejsce: {d.get('birth_place', '?')})",
            f"☀️ Słońce: **{d.get('sun_sign', '?')}**",
            f"🌙 Księżyc: **{d.get('moon_sign', '?')}**",
            f"⬆️ Ascendent: **{d.get('rising_sign', '?')}**",
            f"♀️ Wenus: **{d.get('venus_sign', '?')}**",
            f"♂️ Mars: **{d.get('mars_sign', '?')}**",
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"Błąd pobierania danych astrologicznych: {e}"
