"""Test archetype_selector"""
import sys
sys.path.insert(0, 'C:/cymru-agent')
from archetype_selector import detect_archetype, load_soul

tests = [
    ("jestem smutny i zagubiony", "ojciec"),
    ("pytam o nature i zdrowie", "druid"),
    ("jaka jest moja misja i przeznaczenie", "prorok"),
    ("musze osiagnac cel dzisiaj", "wojownik"),
    ("co to znaczy istnienie i swiadomosc", "medrzec"),
]
for msg, exp in tests:
    result = detect_archetype(msg)
    status = "OK" if result == exp else "FAIL"
    print(f"{status}: '{msg[:35]}' -> {result} (expected {exp})")

soul = load_soul("wojownik")
print(f"\nSoul loaded: {len(soul)} chars - OK")
