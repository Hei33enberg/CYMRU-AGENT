"""11. get_daily_briefing — composite: weather + calendar + astro daily synthesis"""
from __future__ import annotations
from custom_tools.get_weather import get_weather
from custom_tools.get_calendar_events import get_calendar_events
from custom_tools.get_astro_chart import get_astro_chart
from datetime import date


def get_daily_briefing(user_id: str, location: str = "Warsaw, Poland") -> str:
    """
    Generate a comprehensive daily briefing for the user combining weather,
    calendar events, and astrological energy for today.
    Use when user asks for morning briefing, 'dzień dobry', 'co dzisiaj', or daily summary.

    Args:
        user_id: UUID of the user.
        location: User's location for weather (default: Warsaw, Poland).

    Returns:
        Formatted daily briefing combining all data sources.
    """
    today = date.today().strftime("%A, %d %B %Y")

    weather = get_weather(location)
    calendar = get_calendar_events(user_id, days_ahead=1)
    astro = get_astro_chart(user_id)

    # Calculate daily vibration
    digits = sum(int(d) for d in date.today().strftime("%Y%m%d"))
    while digits > 9 and digits not in (11, 22, 33):
        digits = sum(int(d) for d in str(digits))
    vibration_names = {1: "Nowe początki", 2: "Współpraca", 3: "Ekspresja", 4: "Praca",
                       5: "Zmiana", 6: "Miłość", 7: "Refleksja", 8: "Moc", 9: "Zakończenie",
                       11: "Intuicja", 22: "Budowanie", 33: "Służba"}

    return (
        f"🌅 **Dzienny Briefing — {today}**\n\n"
        f"**🔢 Wibracja dnia: {digits} — {vibration_names.get(digits, '?')}**\n\n"
        f"**🌤 Pogoda:**\n{weather}\n\n"
        f"**📅 Kalendarz (dziś):**\n{calendar}\n\n"
        f"**✨ Twój horoskop:**\n{astro}"
    )
