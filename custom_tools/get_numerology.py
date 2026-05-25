"""9. get_numerology — life path, expression, soul urge calculation"""
from __future__ import annotations
from datetime import date


def _reduce(n: int) -> int:
    """Reduce to single digit (keep 11, 22, 33 as master numbers)."""
    while n > 9 and n not in (11, 22, 33):
        n = sum(int(d) for d in str(n))
    return n


def _letter_value(c: str) -> int:
    return (ord(c.upper()) - 64) if c.isalpha() else 0


def get_numerology(birth_date: str, full_name: str) -> str:
    """
    Calculate numerology numbers: Life Path, Expression, Soul Urge, Personal Year.
    Use when user asks about their numerology, life path number, or destiny.

    Args:
        birth_date: Date of birth in YYYY-MM-DD format.
        full_name: Full legal name (first + last name).

    Returns:
        Formatted numerology reading.
    """
    try:
        bd = date.fromisoformat(birth_date)
        life_path = _reduce(sum(int(d) for d in birth_date.replace("-", "")))
        expression = _reduce(sum(_letter_value(c) for c in full_name))
        vowels = set("AEIOUĄĘÓUY")
        soul_urge = _reduce(sum(_letter_value(c) for c in full_name.upper() if c in vowels))
        today = date.today()
        personal_year = _reduce(bd.day + bd.month + today.year)

        meanings = {
            1: "Niezależność, przywództwo, nowe początki",
            2: "Współpraca, intuicja, równowaga",
            3: "Ekspresja, kreatywność, komunikacja",
            4: "Stabilność, praca, budowanie fundamentów",
            5: "Wolność, zmiana, przygoda",
            6: "Miłość, odpowiedzialność, harmonia",
            7: "Duchowość, analiza, wewnętrzna wiedza",
            8: "Moc, obfitość, sukces materialny",
            9: "Zakończenia, mądrość, służba",
            11: "Mistrz Intuicji — wyższa świadomość",
            22: "Mistrz Budowniczy — wielkie dzieła",
            33: "Mistrz Nauczyciel — bezwarunkowa miłość",
        }

        return (
            f"🔢 **Numerologia dla {full_name}**\n\n"
            f"**Liczba Życia (Life Path): {life_path}** — {meanings.get(life_path, '?')}\n"
            f"**Liczba Przeznaczenia (Expression): {expression}** — {meanings.get(expression, '?')}\n"
            f"**Liczba Duszy (Soul Urge): {soul_urge}** — {meanings.get(soul_urge, '?')}\n"
            f"**Rok Osobisty {today.year}: {personal_year}** — {meanings.get(personal_year, '?')}"
        )
    except Exception as e:
        return f"Błąd obliczenia numerologii: {e}"
