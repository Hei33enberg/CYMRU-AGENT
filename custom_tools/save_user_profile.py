"""15. save_user_profile — onboarding profile save"""
from __future__ import annotations
import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
_sb = lambda: create_client(os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""))


def save_user_profile(
    user_id: str,
    display_name: str | None = None,
    birth_date: str | None = None,
    birth_place: str | None = None,
    human_design_type: str | None = None,
    sun_sign: str | None = None,
    moon_sign: str | None = None,
    goals: list[str] | None = None,
) -> str:
    """
    Save or update the user's onboarding profile data.
    Use when user shares personal information during onboarding or says
    'mam na imię', 'urodziłem się', 'jestem z', 'mój typ HD to'.

    Args:
        user_id: UUID of the user.
        display_name: User's preferred name.
        birth_date: Date of birth YYYY-MM-DD.
        birth_place: City of birth.
        human_design_type: HD type (Generator, Projector, Manifestor, etc.).
        sun_sign: Zodiac sun sign.
        moon_sign: Zodiac moon sign.
        goals: List of user's stated goals.

    Returns:
        Confirmation message.
    """
    try:
        sb = _sb()
        profile_data: dict = {"user_id": user_id}
        if display_name:
            profile_data["display_name"] = display_name
        if goals:
            profile_data["goals"] = goals

        sb.table("profiles").upsert(profile_data, on_conflict="id").execute()

        birth_data: dict = {"user_id": user_id}
        if birth_date:
            birth_data["birth_date"] = birth_date
        if birth_place:
            birth_data["birth_place"] = birth_place
        if human_design_type:
            birth_data["human_design_type"] = human_design_type
        if sun_sign:
            birth_data["sun_sign"] = sun_sign
        if moon_sign:
            birth_data["moon_sign"] = moon_sign

        if len(birth_data) > 1:  # has more than just user_id
            sb.table("user_birth_data").upsert(birth_data, on_conflict="user_id").execute()

        saved = [k for k in profile_data if k != "user_id"] + [k for k in birth_data if k != "user_id"]
        return f"Zapisałem Twój profil. Zapamiętałem: {', '.join(saved)}."
    except Exception as e:
        return f"Błąd zapisu profilu: {e}"
