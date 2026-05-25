"""
archetype_selector.py — detect emotion/context and return matching soul archetype
LINEAR-1832 [F2.6] — ports detectArchetype() from shaman-ai-chat
"""
from __future__ import annotations
import os


ARCHETYPE_MAP: dict[str, list[str]] = {
    "ojciec": ["smutek", "zagubiony", "strata", "ból", "lęk", "zmęczony", "nie wiem", "help", "sad", "lost", "hurt", "tired", "depresja", "płaczę", "samotny"],
    "druid":  ["natura", "przyroda", "las", "ziemia", "żywioł", "zioła", "ciało", "zdrowie", "sezon", "wiosna", "lato", "jesień", "zima", "rytm", "nature", "body", "health"],
    "prorok": ["przyszłość", "przeznaczenie", "misja", "sens", "wizja", "los", "tarot", "przepowiednia", "destiny", "future", "purpose", "mission", "znak"],
    "wojownik": ["walka", "determinacja", "zmienić", "osiągnąć", "osiagnac", "musze", "muszę", "sukces", "problem", "wkurwiony", "biznes", "plan", "działaj", "fight", "goal", "angry", "business", "cel dzisiaj"],
    "medrzec": ["cisza", "spokój", "medytacja", "sens życia", "filozofia", "dlaczego", "istnienie", "świadomość", "peace", "meditate", "why", "meaning", "consciousness", "wisdom"],
}

_SOUL_DIR = os.path.join(os.path.dirname(__file__), "souls")


def detect_archetype(user_message: str) -> str:
    """
    Detect which soul archetype best matches the user's message.

    Args:
        user_message: The user's raw message text.

    Returns:
        Archetype name: 'ojciec' | 'druid' | 'prorok' | 'wojownik' | 'medrzec'
        Defaults to 'ojciec' if no strong match.
    """
    msg_lower = user_message.lower()
    scores: dict[str, int] = {arch: 0 for arch in ARCHETYPE_MAP}
    for arch, keywords in ARCHETYPE_MAP.items():
        for kw in keywords:
            if kw in msg_lower:
                scores[arch] += 1
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "ojciec"


def load_soul(archetype: str) -> str:
    """
    Load SOUL.md (base) + archetype soul file content.

    Args:
        archetype: Name of the archetype soul to load.

    Returns:
        Combined system prompt string: SOUL.md + souls/<archetype>.md
    """
    base_path = os.path.join(os.path.dirname(__file__), "SOUL.md")
    arch_path = os.path.join(_SOUL_DIR, f"{archetype}.md")

    with open(base_path, encoding="utf-8") as f:
        base = f.read()
    try:
        with open(arch_path, encoding="utf-8") as f:
            arch = f.read()
    except FileNotFoundError:
        arch = ""

    return f"{base}\n\n---\n\n## Active Archetype: {archetype.upper()}\n\n{arch}"
