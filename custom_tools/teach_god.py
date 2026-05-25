"""3. teach_god — create a new skill from voice instruction"""
from __future__ import annotations
from bridges.supabase_skills import create_skill


def teach_god(name: str, description: str, content: str, trigger_keywords: list[str], user_id: str | None = None) -> str:
    """
    Create a new persistent skill that God will use automatically.
    Use this when the user says 'naucz się że', 'zapamiętaj że gdy',
    'od teraz gdy ktoś pyta', or 'zrób skill'.

    Args:
        name: Short snake_case skill name (max 30 chars).
        description: When to use this skill (for LLM routing, in English).
        content: Full markdown instructions for God.
        trigger_keywords: 3-5 keywords that trigger this skill.
        user_id: Optional UUID of the user who created the skill.

    Returns:
        Confirmation message with skill name.
    """
    try:
        result = create_skill(
            name=name,
            description=description,
            content=content,
            trigger_keywords=trigger_keywords,
            quality_score=0.7,
            is_public=False,
            user_id=user_id,
        )
        return f"Zapamiętałem. Skill **{name}** jest aktywny. ID: {result.get('id')}"
    except Exception as e:
        return f"Nie mogłem stworzyć skilla: {e}"
