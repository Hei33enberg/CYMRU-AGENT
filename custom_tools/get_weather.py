"""6. get_weather — current weather via Perplexity sonar"""
from __future__ import annotations
import os
import httpx
from dotenv import load_dotenv

load_dotenv()
_PERPLEXITY_KEY = os.getenv("PERPLEXITY_API_KEY", "")


def get_weather(location: str = "Warsaw, Poland") -> str:
    """
    Get current weather for a location using Perplexity real-time search.
    Use when user asks about weather, temperature, or 'jaka pogoda'.

    Args:
        location: City and country (default: Warsaw, Poland).

    Returns:
        Current weather summary.
    """
    if not _PERPLEXITY_KEY:
        return f"Aby pobrać pogodę dla {location}, skonfiguruj PERPLEXITY_API_KEY w .env."
    try:
        response = httpx.post(
            "https://api.perplexity.ai/chat/completions",
            headers={"Authorization": f"Bearer {_PERPLEXITY_KEY}"},
            json={
                "model": "sonar",
                "messages": [{"role": "user", "content": f"Current weather in {location}? Give temperature in Celsius, conditions, and a brief forecast. Be concise."}],
                "max_tokens": 200,
            },
            timeout=15,
        )
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Nie mogłem pobrać pogody: {e}"
