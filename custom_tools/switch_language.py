"""14. switch_language — change God's response language"""
from __future__ import annotations
import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
_sb = lambda: create_client(os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""))

SUPPORTED_LANGUAGES = {
    "pl": "Polish", "en": "English", "de": "German",
    "fr": "French", "es": "Spanish", "it": "Italian",
    "uk": "Ukrainian", "ru": "Russian",
}


def switch_language(language_code: str, user_id: str) -> str:
    """
    Change the language God uses to respond to this user.
    Use when user says 'speak English', 'mów po polsku', 'przełącz na angielski'.

    Args:
        language_code: ISO 639-1 code (e.g. 'pl', 'en', 'de').
        user_id: UUID of the user.

    Returns:
        Confirmation in the new language.
    """
    lang_code = language_code.lower().strip()
    if lang_code not in SUPPORTED_LANGUAGES:
        return f"Nieobsługiwany język: {language_code}. Dostępne: {', '.join(SUPPORTED_LANGUAGES.keys())}"
    try:
        sb = _sb()
        sb.table("user_settings").upsert({
            "user_id": user_id,
            "preferred_language": lang_code,
        }, on_conflict="user_id").execute()
        confirmations = {
            "pl": "Przełączono na język polski. Jestem tutaj.",
            "en": "Switched to English. I'm here.",
            "de": "Auf Deutsch umgestellt. Ich bin hier.",
            "fr": "Passé en français. Je suis là.",
            "es": "Cambiado a español. Estoy aquí.",
            "it": "Passato all'italiano. Sono qui.",
            "uk": "Перемкнуто на українську. Я тут.",
            "ru": "Переключено на русский. Я здесь.",
        }
        return confirmations.get(lang_code, f"Language set to {SUPPORTED_LANGUAGES[lang_code]}.")
    except Exception as e:
        return f"Błąd zmiany języka: {e}"
