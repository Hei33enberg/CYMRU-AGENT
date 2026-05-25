"""7. get_news_radar — top news via Perplexity sonar-pro"""
from __future__ import annotations
import os
import httpx
from dotenv import load_dotenv

load_dotenv()
_PERPLEXITY_KEY = os.getenv("PERPLEXITY_API_KEY", "")


def get_news_radar(topic: str = "world", language: str = "pl") -> str:
    """
    Get top news headlines via Perplexity real-time search.
    Use when user asks about news, events, or 'co się dzieje'.

    Args:
        topic: News topic (e.g. 'world', 'technology', 'Poland', 'crypto').
        language: Response language code (default 'pl' for Polish).

    Returns:
        Summary of top news items.
    """
    if not _PERPLEXITY_KEY:
        return "Aby pobrać newsy, skonfiguruj PERPLEXITY_API_KEY w .env."
    lang_instruction = "Respond in Polish." if language == "pl" else f"Respond in {language}."
    try:
        response = httpx.post(
            "https://api.perplexity.ai/chat/completions",
            headers={"Authorization": f"Bearer {_PERPLEXITY_KEY}"},
            json={
                "model": "sonar-pro",
                "messages": [{"role": "user", "content": f"Top 5 news about {topic} right now. {lang_instruction} Be concise, bullet points."}],
                "max_tokens": 400,
            },
            timeout=15,
        )
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Nie mogłem pobrać newsów: {e}"
