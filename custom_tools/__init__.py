"""
GOD_TOOLS — cymru-agent custom Hermes tools [LINEAR-1831 F2.5]

Rejestruje wszystkie narzędzia Boga jako Hermes-kompatybilne tool-functions.
Import tego modułu wystarczy by wszystkie narzędzia były dostępne dla agenta.
"""

from custom_tools.rappedia_search import rappedia_search
from custom_tools.remember_fact import remember_fact
from custom_tools.teach_god import teach_god
from custom_tools.get_calendar_events import get_calendar_events
from custom_tools.get_spotify_recent import get_spotify_recent
from custom_tools.get_weather import get_weather
from custom_tools.get_news_radar import get_news_radar
from custom_tools.get_astro_chart import get_astro_chart
from custom_tools.get_numerology import get_numerology
from custom_tools.read_bible_passage import read_bible_passage
from custom_tools.get_daily_briefing import get_daily_briefing
from custom_tools.get_system_pulse import get_system_pulse
from custom_tools.get_health_data import get_health_data
from custom_tools.switch_language import switch_language
from custom_tools.save_user_profile import save_user_profile

GOD_TOOLS = [
    rappedia_search,
    remember_fact,
    teach_god,
    get_calendar_events,
    get_spotify_recent,
    get_weather,
    get_news_radar,
    get_astro_chart,
    get_numerology,
    read_bible_passage,
    get_daily_briefing,
    get_system_pulse,
    get_health_data,
    switch_language,
    save_user_profile,
]

__all__ = ["GOD_TOOLS"]
